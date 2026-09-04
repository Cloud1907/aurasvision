"""D-Fire (YOLO biçimi) → COCO dönüştürücü — RF-DETR eğitimi için.

RF-DETR COCO ister, D-Fire ise YOLO biçiminde dağıtılır. Dönüşümün iki yerinde
sessiz veri kaybı riski vardır ve ikisi de burada bilinçle ele alınıyor:

1. **Negatif kareler.** D-Fire'ın en değerli parçası, içinde yangın/duman
   OLMAYAN karelerdir (boş `.txt`). Yanlış alarmı bastıran şey pozitif örnek
   değil negatiftir. Etiketsiz görüntüyü atlayan naif dönüştürücü bu karelerin
   tamamını siler ve model sahada her buharı duman sanır — bu yüzden negatif
   görüntü COCO'ya `annotations` olmadan MUTLAKA yazılır.
2. **Koordinat tabanı.** YOLO normalize merkez+boyut (`cx cy w h`), COCO ise
   piksel sol-üst+boyut (`x y w h`) kullanır. Dönüşüm görüntü boyutunu ister;
   boyut dosyadan okunur, varsayılmaz.

Sınıf sırası D-Fire'ın kendi sırasıdır: `0=smoke, 1=fire`. COCO kategori
kimlikleri 1'den başlar (Roboflow/RF-DETR düzeni), yani `smoke=1, fire=2`.

Kullanım:
  python scripts/dfire_to_coco.py --kaynak C:/AurasVision/datasets/dfire \\
                                  --hedef  C:/AurasVision/datasets/dfire-coco \\
                                  --valid-orani 0.1
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# D-Fire'ın kendi sınıf sırası. Değiştirme: config.yaml `fire.classes` ve
# src/fire.py:SINIF_ADLARI bu sıraya bağlı.
SINIFLAR = ("smoke", "fire")

# Bozuk kutuların sessizce geçmemesi için asgari ölçü (normalize birimde).
# Sıfır alanlı kutu COCO'da geçerlidir ama eğitimde NaN kaybına yol açar.
EN_KUCUK_KENAR = 1e-6

# Kenar uzunluğu 1.0'ı AŞABİLİR: kadrajı dolduran nesnenin kutusu görüntü
# sınırından taşar. Ölçüm (D-Fire, 2026-09-02): 26.557 kutunun 8'i bu durumda,
# görülen en büyük değer 1.0563. Bu kutular geçerlidir ve yolo_kutu_coco()
# içinde kırpılır. Tavan yine de konur: 2.0'ı aşan değer taşma değil BOZUK
# etikettir ve sessizce kırpılırsa eğitime yanlış kutu girer.
EN_BUYUK_KENAR = 2.0


class DonusumHatasi(ValueError):
    """Etiket dosyası D-Fire sözleşmesine uymuyor."""


def yolo_kutu_coco(pay: list[float], genislik: int, yukseklik: int) -> list[float]:
    """Normalize `cx cy w h` → piksel `x y w h` (sol-üst köşe).

    Kutu kare dışına taşarsa kırpılır: D-Fire'da sınırda birkaç kutu var ve
    negatif koordinat COCO doğrulayıcılarını patlatır.
    """
    cx, cy, g, y = pay
    x1 = (cx - g / 2.0) * genislik
    y1 = (cy - y / 2.0) * yukseklik
    kg = g * genislik
    ky = y * yukseklik
    x1 = max(0.0, min(x1, float(genislik)))
    y1 = max(0.0, min(y1, float(yukseklik)))
    kg = max(0.0, min(kg, genislik - x1))
    ky = max(0.0, min(ky, yukseklik - y1))
    return [round(x1, 2), round(y1, 2), round(kg, 2), round(ky, 2)]


def etiket_satiri_ayristir(satir: str) -> tuple[int, list[float]] | None:
    """`sinif cx cy w h` → (sinif, [cx,cy,w,h]); boş satır None döner."""
    parca = satir.split()
    if not parca:
        return None
    if len(parca) != 5:
        raise DonusumHatasi(f"5 alan bekleniyordu, {len(parca)} geldi: {satir!r}")
    sinif = int(parca[0])
    if sinif not in range(len(SINIFLAR)):
        raise DonusumHatasi(f"Bilinmeyen sınıf id: {sinif} (beklenen 0..{len(SINIFLAR)-1})")
    cx, cy, kg, ky = (float(v) for v in parca[1:])
    if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
        raise DonusumHatasi(f"Kutu merkezi kare dışında: cx={cx} cy={cy}")
    if kg < 0.0 or ky < 0.0 or kg > EN_BUYUK_KENAR or ky > EN_BUYUK_KENAR:
        raise DonusumHatasi(f"Kenar uzunluğu geçersiz: w={kg} h={ky}")
    # Sıfır kenar BİÇİM hatası değil, bozuk ETİKETtir (nokta işaretlenmiş).
    # Ayrıştırma kabul eder; coco_uret() eler ve SAYAR — sessizce düşmez.
    return sinif, [cx, cy, kg, ky]


def etiket_oku(yol: Path) -> list[tuple[int, list[float]]]:
    """Bir YOLO etiket dosyasını okur. Dosya yoksa/boşsa NEGATİF kare = []."""
    if not yol.is_file():
        return []
    cikti = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        ayri = etiket_satiri_ayristir(satir)
        if ayri is not None:
            cikti.append(ayri)
    return cikti


def goruntu_boyutu(yol: Path) -> tuple[int, int]:
    """(genişlik, yükseklik) — yalnız başlık okunur, piksel çözülmez."""
    from PIL import Image

    with Image.open(yol) as im:
        return int(im.width), int(im.height)


def _kategoriler() -> list[dict]:
    return [{"id": i + 1, "name": ad, "supercategory": "none"}
            for i, ad in enumerate(SINIFLAR)]


def coco_uret(ciftler: list[tuple[Path, Path]]) -> tuple[dict, dict]:
    """(görüntü, etiket) çiftlerinden COCO sözlüğü + sayım özeti üretir.

    Negatif kareler `images` listesine girer, `annotations`a girmez — kasıtlı.
    """
    images, annotations = [], []
    negatif = 0
    dusen = 0          # sıfır/alanısız kutu — atılır ama GÖRÜNÜR kalır
    kutu_sinif: dict[str, int] = {ad: 0 for ad in SINIFLAR}
    for img_id, (img, lbl) in enumerate(sorted(ciftler), start=1):
        genislik, yukseklik = goruntu_boyutu(img)
        images.append({"id": img_id, "file_name": img.name,
                       "width": genislik, "height": yukseklik})
        kutular = etiket_oku(lbl)
        if not kutular:
            negatif += 1
            continue
        for sinif, pay in kutular:
            kutu = yolo_kutu_coco(pay, genislik, yukseklik)
            if kutu[2] <= EN_KUCUK_KENAR or kutu[3] <= EN_KUCUK_KENAR:
                dusen += 1
                continue
            annotations.append({
                "id": len(annotations) + 1, "image_id": img_id,
                "category_id": sinif + 1, "bbox": kutu,
                "area": round(kutu[2] * kutu[3], 2), "iscrowd": 0,
            })
            kutu_sinif[SINIFLAR[sinif]] += 1
    coco = {"images": images, "annotations": annotations,
            "categories": _kategoriler()}
    ozet = {"goruntu": len(images), "negatif": negatif,
            "pozitif": len(images) - negatif, "kutu": len(annotations),
            "dusen_kutu": dusen, **kutu_sinif}
    return coco, ozet


def ciftle(images_dir: Path, labels_dir: Path) -> list[tuple[Path, Path]]:
    """Görüntü ↔ etiket eşleştirmesi. Etiketi olmayan görüntü NEGATİF sayılır."""
    uzanti = {".jpg", ".jpeg", ".png"}
    return [(p, labels_dir / f"{p.stem}.txt")
            for p in sorted(images_dir.iterdir())
            if p.suffix.lower() in uzanti]


def _yaz(hedef: Path, ad: str, ciftler: list[tuple[Path, Path]],
         kopyala: bool) -> dict:
    """Bir split'i COCO olarak yazar; RF-DETR görüntüleri split klasöründe bekler."""
    dizin = hedef / ad
    dizin.mkdir(parents=True, exist_ok=True)
    coco, ozet = coco_uret(ciftler)
    if kopyala:
        for img, _ in ciftler:
            kopya = dizin / img.name
            if not kopya.exists():
                shutil.copy2(img, kopya)
    (dizin / "_annotations.coco.json").write_text(
        json.dumps(coco), encoding="utf-8")
    return ozet


def bol(ciftler: list[tuple[Path, Path]], oran: float) -> tuple[list, list]:
    """Deterministik train/valid ayrımı — dosya adına göre, rastgelelik YOK.

    Rastgele tohum kullanmıyoruz: aynı komut aynı bölünmeyi vermeli, yoksa iki
    eğitim koşusunun sonucu karşılaştırılamaz hale gelir.
    """
    if oran <= 0:
        return ciftler, []
    adim = max(2, int(round(1.0 / oran)))
    train = [c for i, c in enumerate(sorted(ciftler)) if i % adim]
    valid = [c for i, c in enumerate(sorted(ciftler)) if not i % adim]
    return train, valid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kaynak", required=True, help="D-Fire kökü (train/, test/)")
    ap.add_argument("--hedef", required=True, help="COCO çıktı kökü")
    ap.add_argument("--valid-orani", type=float, default=0.1,
                    help="train'den ayrılacak doğrulama oranı (0 = ayırma)")
    ap.add_argument("--kopyalama", action="store_true",
                    help="görüntüleri kopyalama (yalnız JSON üret)")
    a = ap.parse_args(argv)
    kaynak, hedef = Path(a.kaynak), Path(a.hedef)
    tum = ciftle(kaynak / "train" / "images", kaynak / "train" / "labels")
    train, valid = bol(tum, a.valid_orani)
    test = ciftle(kaynak / "test" / "images", kaynak / "test" / "labels")
    ozetler = {}
    for ad, c in (("train", train), ("valid", valid), ("test", test)):
        if c:
            ozetler[ad] = _yaz(hedef, ad, c, not a.kopyalama)
    for ad, o in ozetler.items():
        print(f"{ad:6} görüntü={o['goruntu']:6} negatif={o['negatif']:6} "
              f"kutu={o['kutu']:6} (smoke={o['smoke']} fire={o['fire']}) "
              f"düşen={o['dusen_kutu']}")
    t = {k: sum(o[k] for o in ozetler.values())
         for k in ("goruntu", "negatif", "kutu", "smoke", "fire", "dusen_kutu")}
    print(f"TOPLAM görüntü={t['goruntu']} negatif={t['negatif']} "
          f"kutu={t['kutu']} (smoke={t['smoke']} fire={t['fire']}) "
          f"düşen={t['dusen_kutu']}")
    (hedef / "ozet.json").write_text(json.dumps(ozetler, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
