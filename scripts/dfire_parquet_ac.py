"""D-Fire parquet arşivini YOLO klasör düzenine açar.

Neden gerekli: D-Fire'ın HuggingFace aynasında (`badsaarow/d-fire`) ham
`train/images` ağacı EKSİKTİR — 2026-09-02 ölçümü: ağaçta 7.222 train
görüntüsü var, oysa veri seti 21.527 görüntüdür. Tam veri yalnız `data/*.parquet`
içindedir ve orada etiket, satırın `label` alanında YOLO METNİ olarak durur
(negatif kare = boş dize). Bu script parquet'i diske açar; sonrasında
`scripts/dfire_to_coco.py` hiç değişmeden çalışır.

Ölçüm (test-00000-of-00003.parquet): 1.436 satır, 444'ü kutulu, 992 negatif —
yani negatifler parquet'te de korunuyor.

Kullanım:
  python scripts/dfire_parquet_ac.py --parquet <dfire-parquet>/data \\
                                     --hedef   <dfire>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Parquet satırındaki sütun adları — ayna şeması değişirse burada patlasın,
# sessizce boş veri seti üretmesin.
SUTUNLAR = ("image", "label", "filename")


class ParquetHatasi(ValueError):
    """Parquet şeması beklenen D-Fire düzeninde değil."""


def sutunlari_dogrula(mevcut) -> None:
    """Beklenen sütunlar yoksa AÇIK hata ver — boş çıktıdan iyidir."""
    eksik = [s for s in SUTUNLAR if s not in set(mevcut)]
    if eksik:
        raise ParquetHatasi(
            f"Parquet şeması uyumsuz, eksik sütun: {', '.join(eksik)}. "
            f"Bulunan: {sorted(mevcut)}")


def goruntu_baytlari(deger) -> bytes:
    """HF `Image` sütunu {'bytes':..., 'path':...} sözlüğü olarak gelir."""
    if isinstance(deger, dict):
        ham = deger.get("bytes")
        if ham:
            return ham
        yol = deger.get("path")
        if yol and Path(yol).is_file():
            return Path(yol).read_bytes()
        raise ParquetHatasi("Görüntü satırında ne bytes ne okunabilir path var")
    if isinstance(deger, (bytes, bytearray)):
        return bytes(deger)
    raise ParquetHatasi(f"Beklenmeyen görüntü tipi: {type(deger).__name__}")


def etiket_metni(deger) -> str:
    """`label` alanı YOLO metnidir; None/boş = negatif kare (geçerli durum)."""
    return (deger or "").strip()


def split_yaz(dosyalar: list[Path], hedef: Path) -> dict:
    """Bir split'in parquet parçalarını images/ + labels/ olarak diske açar."""
    import pyarrow.parquet as pq

    img_dir, lbl_dir = hedef / "images", hedef / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    sayac = {"goruntu": 0, "negatif": 0, "kutu": 0}
    for parca in sorted(dosyalar):
        tablo = pq.read_table(parca)
        sutunlari_dogrula(tablo.column_names)
        for satir in tablo.to_pylist():
            ad = Path(str(satir["filename"])).name
            (img_dir / ad).write_bytes(goruntu_baytlari(satir["image"]))
            metin = etiket_metni(satir["label"])
            (lbl_dir / f"{Path(ad).stem}.txt").write_text(
                (metin + "\n") if metin else "", encoding="utf-8")
            sayac["goruntu"] += 1
            if metin:
                sayac["kutu"] += len(metin.splitlines())
            else:
                sayac["negatif"] += 1
    return sayac


def parcalari_bul(dizin: Path, split: str) -> list[Path]:
    """`train-00000-of-00009.parquet` gibi parçaları split adına göre toplar."""
    return sorted(p for p in dizin.glob("*.parquet")
                  if p.name.startswith(f"{split}-"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", required=True, help="data/ klasörü (*.parquet)")
    ap.add_argument("--hedef", required=True, help="YOLO düzeni çıktı kökü")
    a = ap.parse_args(argv)
    kaynak, hedef = Path(a.parquet), Path(a.hedef)
    toplam = {"goruntu": 0, "negatif": 0, "kutu": 0}
    for split in ("train", "test"):
        parcalar = parcalari_bul(kaynak, split)
        if not parcalar:
            print(f"UYARI: {split} için parquet bulunamadı", file=sys.stderr)
            continue
        s = split_yaz(parcalar, hedef / split)
        print(f"{split:6} görüntü={s['goruntu']:6} negatif={s['negatif']:6} "
              f"kutu={s['kutu']:6}  ({len(parcalar)} parça)")
        for k in toplam:
            toplam[k] += s[k]
    print(f"TOPLAM görüntü={toplam['goruntu']} negatif={toplam['negatif']} "
          f"kutu={toplam['kutu']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
