"""RF-DETR-Small ile yangın/duman dedektörü eğitimi (D-Fire, COCO biçimi).

Motor seçimi bir LİSANS kararıdır, performans tercihi değil: Ultralytics YOLO
AGPL-3.0'dır ve modeli sunucu arkasında sunmak da dağıtım sayılır. Bu script
`ultralytics` import ETMEZ; gerekçe docs/yangin-modeli.md.

Ölçülmüş kısıtlar (bu makine, 2026-09-02):

* **Çözünürlük 512.** RF-DETR-Small'un pretrain çözünürlüğü 512'dir ve
  konumsal kodlama ondan türer (PE = 512/16 = 32). 640'a çıkmak PE'yi de
  değiştirir; ayrıca bu makinede VRAM buna elvermiyor (aşağı bakın). Küçük
  nesne (erken duman) recall'ı çözünürlükle iyileşir — daha büyük GPU'da 640
  denemeye değer, ölçüm belgesinde açık uç olarak duruyor.
* **VRAM 6 GB ve analiz worker'ı çalışmaya devam ediyor** (operatör kararı),
  yani eğitime ~3,4 GB kalıyor. Bu yüzden batch küçük, gradyan biriktirme ile
  efektif batch korunuyor: `batch_size * grad_accum_steps` sabit tutulur.

Kullanım:
  python scripts/fire_train.py --coco C:/AurasVision/datasets/dfire-coco \\
      --epochs 10 --out output/fire_train
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# RF-DETR-Small kısıtı: çözünürlük patch_size(16) * num_windows(2) = 32'ye
# bölünebilmeli. Bölünmezse paket ValueError atar; erken ve anlaşılır hata
# vermek için burada da denetlenir.
COZUNURLUK_BOLEN = 32
VARSAYILAN_COZUNURLUK = 512

# D-Fire sınıf sırası — dönüştürücüyle (scripts/dfire_to_coco.py) aynı olmalı.
SINIF_ADLARI = ["smoke", "fire"]


class EgitimAyarHatasi(ValueError):
    """Eğitim ayarı geçersiz — koşmadan önce yakalanır."""


def cozunurluk_dogrula(deger: int) -> int:
    """Çözünürlüğü doğrular; saatler süren koşu geçersiz ayarla başlamasın."""
    if deger <= 0 or deger % COZUNURLUK_BOLEN:
        raise EgitimAyarHatasi(
            f"Çözünürlük {COZUNURLUK_BOLEN}'ye bölünebilmeli (RF-DETR-Small "
            f"patch 16 × 2 pencere); verilen: {deger}")
    return deger


def veri_seti_dogrula(kok: Path) -> Path:
    """train/valid/test ve COCO json'larının varlığını koşmadan önce doğrular."""
    eksik = [ad for ad in ("train", "valid")
             if not (kok / ad / "_annotations.coco.json").is_file()]
    if eksik:
        raise EgitimAyarHatasi(
            f"COCO veri seti eksik: {', '.join(eksik)} altında "
            "_annotations.coco.json yok. Önce scripts/dfire_to_coco.py koşun.")
    return kok


def efektif_batch(batch: int, biriktirme: int) -> int:
    """Gradyan biriktirmeli efektif batch — VRAM küçüldükçe korunan büyüklük."""
    if batch <= 0 or biriktirme <= 0:
        raise EgitimAyarHatasi("batch ve biriktirme pozitif olmalı")
    return batch * biriktirme


def en_iyi_agirlik(cikti: Path) -> Path | None:
    """Eğitim çıktısındaki en iyi checkpoint — ad kalıbı sürümle değişebilir."""
    adaylar = [p for ad in ("checkpoint_best_ema.pth", "checkpoint_best.pth",
                            "checkpoint_best_regular.pth")
               for p in cikti.rglob(ad)]
    if not adaylar:
        adaylar = sorted(cikti.rglob("*.pth"))
    return adaylar[-1] if adaylar else None


def egit(a) -> int:
    """Eğitimi koşar; ağırlığı models/fire.pt'ye kopyalar (repoya COMMIT EDİLMEZ)."""
    from rfdetr import RFDETRSmall

    kok = veri_seti_dogrula(Path(a.coco))
    cozunurluk = cozunurluk_dogrula(a.resolution)
    cikti = Path(a.out)
    cikti.mkdir(parents=True, exist_ok=True)
    print(f"veri={kok} çözünürlük={cozunurluk} epoch={a.epochs} "
          f"batch={a.batch}×{a.grad_accum} (efektif "
          f"{efektif_batch(a.batch, a.grad_accum)})", flush=True)
    model = RFDETRSmall()
    model.train(dataset_dir=str(kok), epochs=a.epochs, batch_size=a.batch,
                grad_accum_steps=a.grad_accum, resolution=cozunurluk,
                output_dir=str(cikti), device=a.device,
                num_workers=a.workers, class_names=SINIF_ADLARI,
                early_stopping=a.early_stopping, tensorboard=False)
    kaynak = en_iyi_agirlik(cikti)
    if kaynak is None:
        print("UYARI: eğitim çıktısında ağırlık bulunamadı", file=sys.stderr)
        return 1
    hedef = ROOT / a.model_out
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kaynak, hedef)
    print(f"ağırlık: {kaynak} → {hedef}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coco", required=True, help="COCO kökü (train/valid/test)")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=2, help="VRAM'e göre küçük tut")
    ap.add_argument("--grad-accum", type=int, default=8,
                    help="efektif batch = batch × bu")
    ap.add_argument("--resolution", type=int, default=VARSAYILAN_COZUNURLUK)
    ap.add_argument("--out", default="output/fire_train")
    ap.add_argument("--model-out", default="models/fire.pt")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--early-stopping", action="store_true")
    return egit(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
