"""Sayım doğruluğu — TRASSIR'ın kendi geçiş kayıtları (border_events) yer gerçeği.

`docs/olcumler-yangin-modeli.md` çalışmasıyla aynı ilke: hiç doğruluk ölçümü
olmayan bir modülü "çalışıyor" sanmak, hatayı sahada buldurur. `kamera-201`
TRASSIR tarafında da sayılıyor (`GE1eca7u` / PeopleZone `T0SQ7tTN`); o akış
bu betiğin yer gerçeğidir.

**Olay-eşleştirme YAPILMAZ, kova (bucket) karşılaştırması yapılır.** TRASSIR'ın
ham `border_events`'i saatte ~1000 olay üretiyor (ölçüldü: 2026-09-03 13:00-14:00
UTC penceresinde 992 olay, ~3,6 sn'de bir) — bu, AurasVision'ın 2 sn cooldown'lu
track sayımından çok daha hassas bir eşik kullandığını gösterir. İki farklı
debounce mantığını olay olay eşleştirmek adil değildir; bunun yerine N dakikalık
kovalara toplanmış TOPLAM trafik korelasyonu ölçülür.

Kullanım:
  python scripts/count_eval.py --camera kamera-201 \\
      --start "2026-09-03T13:00:00+00:00" --end "2026-09-03T14:00:00+00:00" \\
      --gt data/gt-border-events.json --bucket-sn 300
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def segmentleri_bul(db_yolu: str, camera_id: str, bas: datetime,
                    son: datetime) -> list[tuple[str, datetime, float]]:
    """(mutlak yol, başlangıç, süre) — verilen pencereyle kesişen kayıt segmentleri."""
    from src.recorder import kayit_kok
    from src.config import load_config
    kok = kayit_kok(load_config(None))
    c = sqlite3.connect(db_yolu)
    try:
        rows = c.execute(
            "SELECT path, start_time, duration FROM recordings WHERE camera_id=?"
            " ORDER BY start_time", (camera_id,)).fetchall()
    finally:
        c.close()
    cikti = []
    for p, st, d in rows:
        b = datetime.fromisoformat(st)
        s = b + timedelta(seconds=float(d or 60))
        if s >= bas and b <= son:
            cikti.append((str(kok / p), b, float(d or 60)))
    return cikti


def av_olaylari_topla(segmentler: list[tuple[str, datetime, float]],
                      ilerleme=None) -> list[tuple[datetime, str]]:
    """Her segmenti üretim hattıyla (run_count, store=None) tarar → (mutlak_zaman, yon)."""
    from src.config import load_config
    from src.count import run_count
    cfg = load_config(None)
    cikti = []
    for i, (yol, bas, _sure) in enumerate(segmentler, 1):
        r = run_count(yol, cfg, store=None, camera_id="count-eval")
        for e in r.events:
            cikti.append((bas + timedelta(seconds=e["ts_seconds"]), e["direction"]))
        if ilerleme:
            ilerleme(i, len(segmentler), len(r.events))
    return cikti


def gt_oku(yol: str) -> list[tuple[datetime, str]]:
    """TRASSIR `border_events` JSON'ı → (zaman, yon). `yon`: Giris|Cikis."""
    veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    return [(datetime.fromisoformat(x["gecis_zamani"].replace("Z", "+00:00")),
             x["yon"]) for x in veri]


def kova_say(olaylar: list[tuple[datetime, str]], bas: datetime,
            bucket_sn: int, adet: int) -> list[int]:
    """Zaman damgalarını `adet` adet `bucket_sn` saniyelik kovaya toplar (yön ayrımsız)."""
    kovalar = [0] * adet
    for t, _yon in olaylar:
        idx = int((t - bas).total_seconds() // bucket_sn)
        if 0 <= idx < adet:
            kovalar[idx] += 1
    return kovalar


def korelasyon(a: list[int], b: list[int]) -> float | None:
    """Pearson korelasyonu; sabit dizide (varyans=0) tanımsızdır → None."""
    if len(a) < 2 or len(set(a)) < 2 or len(set(b)) < 2:
        return None
    return round(statistics.correlation(a, b), 4)


def _yazdir(av_kova: list[int], gt_kova: list[int], bucket_sn: int) -> None:
    print(f"{'kova':>5} {'AV':>6} {'TRASSIR':>8} {'oran':>7}")
    for i, (a, g) in enumerate(zip(av_kova, gt_kova)):
        oran = f"{a/g:.2f}" if g else ("—" if not a else "∞")
        print(f"{i*bucket_sn//60:>4}dk {a:>6} {g:>8} {oran:>7}")
    print(f"\nTOPLAM   AV={sum(av_kova)}  TRASSIR={sum(gt_kova)}  "
          f"oran={sum(av_kova)/sum(gt_kova):.3f}" if sum(gt_kova) else "TRASSIR verisi yok")
    kor = korelasyon(av_kova, gt_kova)
    print(f"kova-bazlı korelasyon: {kor if kor is not None else 'tanımsız (sabit seri)'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--start", required=True, help="ISO, tz'li")
    ap.add_argument("--end", required=True, help="ISO, tz'li")
    ap.add_argument("--gt", required=True, help="TRASSIR border_events JSON dökümü")
    ap.add_argument("--db", default="output/aurasvision.db")
    ap.add_argument("--bucket-sn", type=int, default=300)
    ap.add_argument("--out", default="output/count_eval/count_eval.json")
    a = ap.parse_args(argv)
    bas, son = datetime.fromisoformat(a.start), datetime.fromisoformat(a.end)
    adet = max(1, int((son - bas).total_seconds() // a.bucket_sn))

    segmentler = segmentleri_bul(a.db, a.camera, bas, son)
    print(f"{len(segmentler)} segment · pencere {bas} → {son}")
    av = av_olaylari_topla(
        segmentler, lambda i, n, k: print(f"  [{i}/{n}] {k} olay", flush=True))
    gt = gt_oku(a.gt)

    av_kova = kova_say(av, bas, a.bucket_sn, adet)
    gt_kova = kova_say(gt, bas, a.bucket_sn, adet)
    _yazdir(av_kova, gt_kova, a.bucket_sn)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "camera": a.camera, "start": a.start, "end": a.end,
        "bucket_sn": a.bucket_sn, "av_kova": av_kova, "gt_kova": gt_kova,
        "av_toplam": sum(av_kova), "gt_toplam": sum(gt_kova),
        "korelasyon": korelasyon(av_kova, gt_kova),
        "segment": len(segmentler),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
