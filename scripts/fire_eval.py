"""Yangın modeli değerlendirmesi — ÜRÜN ölçütüyle, mAP ile değil.

`docs/yangin-modeli.md`'deki kabul ölçütü şudur: hat 6 sn penceresinde 4 kare
onay ister, `src/fire_metrik.gereken_recall(50, 4, 0.95)` = 0.15. Yani
kare-başına recall %15'in üstündeyse ÜRÜN yeterlidir ve fazlası katkı vermez —
buna karşılık kare-başına YANLIŞ POZİTİF doğrudan yanlış alarma dönüşür.
Bu yüzden burada mAP hesaplanmaz; hesaplanan dört şey şudur:

  1. Güven eşiği taraması: her eşikte kare-başına recall ve precision
  2. NEGATİF karelerde "en az bir tespit üreten kare" oranı — nuisance alarmın
     gerçek sürücüsü budur; D-Fire'ın negatif blokları tam bunun için var
  3. Nesne boyutuna göre recall — küçük nesne = erken duman, en kritik dilim
  4. Öneri: recall'ı eşiğin ÜSTÜNDE tutan EN YÜKSEK güven değeri
     (recall'dan feragat edip precision satın alıyoruz — bilinçli)

Tasarım notu: çıkarım TEK kez, en düşük eşikte koşar; tarama bu ham tespitler
üzerinde yapılır. Eşik başına yeniden çıkarım koşmak aynı sonucu verir ama
9 kat pahalıdır ve bu iş zaten saatler sürüyor.

Uyarı (docs/yangin-modeli.md'den): %15 hesabı kareleri BAĞIMSIZ varsayar,
gerçekte ardışık kareler ilintilidir. Yani hafif iyimser bir alt sınırdır;
öneri üretilirken marj bırakılır (`--marj`).

Kullanım:
  python scripts/fire_eval.py --model models/fire.pt \\
      --coco C:/AurasVision/datasets/dfire-coco/test --out output/fire_eval
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dedektor import yukle                      # noqa: E402
from src.fire_metrik import gereken_recall, pencere_kare   # noqa: E402

# COCO'nun boyut dilimleri (piksel²). Erken duman küçük dilimde görünür;
# ürün için en kritik satır odur, ortalama recall onu gizler.
DILIM = (("kucuk", 0, 32 * 32), ("orta", 32 * 32, 96 * 96),
         ("buyuk", 96 * 96, float("inf")))
IOU_ESIGI = 0.5


def iou(a: list[float], b: list[float]) -> float:
    """İki COCO kutusu (x, y, w, h) arasında IoU."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    kesisim = ix * iy
    birlesim = a[2] * a[3] + b[2] * b[3] - kesisim
    return kesisim / birlesim if birlesim > 0 else 0.0


def coco_oku(dizin: Path) -> tuple[list[dict], dict[int, list[dict]]]:
    """(görüntüler, görüntü_id → gerçek kutular)."""
    veri = json.loads((dizin / "_annotations.coco.json").read_text(encoding="utf-8"))
    gercek: dict[int, list[dict]] = {i["id"]: [] for i in veri["images"]}
    for a in veri["annotations"]:
        gercek[a["image_id"]].append(a)
    return veri["images"], gercek


def _dilim_adi(alan: float) -> str:
    for ad, alt, ust in DILIM:
        if alt <= alan < ust:
            return ad
    return DILIM[-1][0]


def tespitleri_topla(model: str, dizin: Path, images: list[dict],
                     taban_esik: float, ilerleme=None) -> dict[int, list[dict]]:
    """Her görüntü için `taban_esik` üstündeki HAM tespitler (tek geçiş)."""
    import cv2

    det = yukle(motor="rfdetr", model=model,
                adlar={0: "smoke", 1: "fire"}, esik=taban_esik)
    cikti: dict[int, list[dict]] = {}
    for sira, im in enumerate(images, 1):
        kare = cv2.imread(str(dizin / im["file_name"]))
        if kare is None:
            cikti[im["id"]] = []
            continue
        cikti[im["id"]] = [{"sinif": s, "kutu": [x1, y1, x2 - x1, y2 - y1],
                            "conf": c}
                           for s, x1, y1, x2, y2, c in det.tespit(kare)]
        if ilerleme and sira % 200 == 0:
            ilerleme(sira, len(images))
    return cikti


def kare_sonucu(tespitler: list[dict], gercekler: list[dict],
                esik: float) -> tuple[bool, bool]:
    """(kare yakalandı mı, kare yanlış tespit üretti mi) — verilen eşikte.

    Eşleştirme SINIF-BAĞIMSIZDIR: alev de duman da aynı alarmı üretir, bu
    yüzden ürün açısından "duman yerine alev dedi" bir kaçırma değildir.
    """
    aktif = [d for d in tespitler if d["conf"] >= esik]
    if not aktif:
        return False, False
    if not gercekler:
        return False, True          # negatif karede tespit = nuisance
    eslesen = any(iou(d["kutu"], g["bbox"]) >= IOU_ESIGI
                  for d in aktif for g in gercekler)
    return eslesen, not eslesen


def _esik_satiri(tespitler: dict, gercek: dict, poz: list, neg: list,
                 e: float) -> dict:
    """Tek eşikteki kare-başına sayılar. `tarama` bunu her eşik için çağırır."""
    yakalanan = sum(kare_sonucu(tespitler.get(i, []), gercek[i], e)[0]
                    for i in poz)
    alarmli_neg = sum(1 for i in neg
                      if any(d["conf"] >= e for d in tespitler.get(i, [])))
    yanlis_poz = sum(kare_sonucu(tespitler.get(i, []), gercek[i], e)[1]
                     for i in poz)
    tespitli = yakalanan + yanlis_poz + alarmli_neg
    return {
        "esik": round(e, 2),
        "kare_recall": round(yakalanan / len(poz), 4) if poz else 0.0,
        "kare_precision": round(yakalanan / tespitli, 4) if tespitli else 0.0,
        "negatif_alarm_orani": round(alarmli_neg / len(neg), 4) if neg else 0.0,
        "negatif_alarmli_kare": alarmli_neg,
    }


def tarama(tespitler: dict, gercek: dict, esikler: list[float]) -> list[dict]:
    """Her eşikte kare-başına recall / precision + negatif kare alarm oranı."""
    poz = [i for i, g in gercek.items() if g]
    neg = [i for i, g in gercek.items() if not g]
    return [_esik_satiri(tespitler, gercek, poz, neg, e) for e in esikler]


def dilim_recall(tespitler: dict, gercek: dict, esik: float) -> dict[str, dict]:
    """Nesne boyutuna göre recall — küçük dilim erken dumanı temsil eder."""
    sayac = {ad: {"gercek": 0, "yakalanan": 0} for ad, _, _ in DILIM}
    for img_id, gs in gercek.items():
        aktif = [d for d in tespitler.get(img_id, []) if d["conf"] >= esik]
        for g in gs:
            ad = _dilim_adi(float(g.get("area") or 0.0))
            sayac[ad]["gercek"] += 1
            if any(iou(d["kutu"], g["bbox"]) >= IOU_ESIGI for d in aktif):
                sayac[ad]["yakalanan"] += 1
    for v in sayac.values():
        v["recall"] = round(v["yakalanan"] / v["gercek"], 4) if v["gercek"] else 0.0
    return sayac


def oneri(satirlar: list[dict], taban_recall: float, marj: float) -> dict:
    """Recall'ı (taban + marj) ÜSTÜNDE tutan EN YÜKSEK eşik.

    Marj, `gereken_recall`'ın bağımsız-kare varsayımının iyimserliğini telafi
    eder: ardışık kareler ilintilidir, yani gerçek onay olasılığı hesaptan
    düşüktür. Marjsız seçim tam sınırda durur ve sahada altına düşer.
    """
    hedef = taban_recall + marj
    uygun = [s for s in satirlar if s["kare_recall"] >= hedef]
    if not uygun:
        return {"esik": None, "gerekce": f"hiçbir eşikte recall ≥ {hedef:.2f} değil"}
    en_iyi = max(uygun, key=lambda s: s["esik"])
    return {"esik": en_iyi["esik"], "hedef_recall": round(hedef, 4),
            "kare_recall": en_iyi["kare_recall"],
            "negatif_alarm_orani": en_iyi["negatif_alarm_orani"],
            "gerekce": "recall hedefin üstünde kalan en yüksek eşik; "
                       "fazla recall ürüne katkı vermez, precision verir"}


def _yazdir(satirlar: list[dict], dilimler: dict, sec: dict, taban: float) -> None:
    print(f"\nkabul tabanı (gereken_recall): {taban:.2f}")
    print(f"{'eşik':>6} {'kare_recall':>12} {'precision':>10} "
          f"{'negatif_alarm':>14} {'alarmlı_neg_kare':>17}")
    for s in satirlar:
        print(f"{s['esik']:>6.2f} {s['kare_recall']:>12.4f} "
              f"{s['kare_precision']:>10.4f} {s['negatif_alarm_orani']:>14.4f} "
              f"{s['negatif_alarmli_kare']:>17}")
    print("\nboyut dilimine göre recall (önerilen eşikte):")
    for ad, v in dilimler.items():
        print(f"  {ad:>6}: {v['recall']:.4f}  ({v['yakalanan']}/{v['gercek']})")
    print(f"\nÖNERİ fire.conf = {sec.get('esik')}  ({sec.get('gerekce')})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--coco", required=True, help="COCO split klasörü")
    ap.add_argument("--out", default="output/fire_eval")
    ap.add_argument("--taban-esik", type=float, default=0.10)
    ap.add_argument("--marj", type=float, default=0.05,
                    help="bağımsız-kare varsayımının iyimserliğine karşı pay")
    ap.add_argument("--fps", type=float, default=25.0)
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--pencere", type=float, default=6.0)
    ap.add_argument("--onay", type=int, default=4)
    a = ap.parse_args(argv)
    dizin = Path(a.coco)
    images, gercek = coco_oku(dizin)
    kare = pencere_kare(a.fps, a.stride, a.pencere)
    taban = gereken_recall(kare, a.onay, 0.95)
    print(f"{len(images)} görüntü · pencere {kare} kare · taban recall {taban:.2f}")
    tespitler = tespitleri_topla(
        a.model, dizin, images, a.taban_esik,
        lambda i, n: print(f"  {i}/{n}", flush=True))
    esikler = [round(0.1 + 0.05 * i, 2) for i in range(17)]
    satirlar = tarama(tespitler, gercek, esikler)
    sec = oneri(satirlar, taban, a.marj)
    dilimler = dilim_recall(tespitler, gercek, sec.get("esik") or a.taban_esik)
    _yazdir(satirlar, dilimler, sec, taban)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fire_eval.json").write_text(json.dumps(
        {"taban_recall": taban, "pencere_kare": kare, "tarama": satirlar,
         "dilim_recall": dilimler, "oneri": sec}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
