"""Plaka doğruluğu — TRASSIR'ın kendi okumaları yer gerçeği.

`scripts/fire_eval.py` ile aynı ilke, farklı yer gerçeği kaynağı: burada
sentetik veri seti yok, TRASSIR'ın aynı kameradan (kamera-204 / `tN9q9YqX`)
ürettiği okumalar kullanılıyor. TRASSIR'ın kendisi de hatasız değil — bu yüzden
yer gerçeği İKİ süzgeçten geçirilir:

  1. `plaka_sablonu` `tr/` ile başlamalı (TRASSIR'ın kendi format doğrulaması
     geçmiş olmalı; `plaka_sablonu="/"` olanlar TRASSIR'ın kendi hatalarıdır —
     bkz. LAAC413 vakası, 2026-09-02).
  2. Aynı plaka en az 2 kez okunmuş olmalı (tek okumaya güvenilmez).

Her "geçiş" (birbirine 90 sn'den yakın okumalar) TEK arşiv segmentine denk
düşer; o segment üretim hattıyla (`run_plate`, store=None) taranır ve oylanan
plaka TRASSIR'ın okumasıyla karşılaştırılır — hem tam eşleşme hem karakter
mesafesi (Levenshtein) ölçülür, çünkü "yakın ama yanlış" okuma da bilgi verir.

Ayrıca TRASSIR olayı OLMAYAN rastgele segmentler taranır: AurasVision orada
plaka üretirse bu bir ADAY yanlış pozitiftir (TRASSIR'ın kaçırmış olması da
mümkündür — bu yüzden "aday", kesin değil).

Kullanım:
  python scripts/plate_eval_gt.py --camera kamera-204 \\
      --gt data/gt-lpr-events.json --db output/aurasvision.db \\
      --sessiz-ornek 15
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KUMELEME_SN = 90     # bu araya yakın okumalar AYNI geçiş sayılır
TEKRAR_ESIGI = 2     # bir plaka en az bu kadar okunmuşsa yer gerçeği adayı


def levenshtein(a: str, b: str) -> int:
    """Düzenleme mesafesi — 'yakın ama yanlış' okumaları sıfır/tam ayrımından çıkarır."""
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        yeni = [i]
        for j, cb in enumerate(b, 1):
            yeni.append(min(dp[j] + 1, yeni[j - 1] + 1, dp[j - 1] + (ca != cb)))
        dp = yeni
    return dp[-1]


def gt_gecisleri(yol: str) -> list[dict]:
    """TRASSIR JSON'ından güvenilir geçişleri çıkarır: tr/ şablonlu + 2+ tekrar."""
    veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    veri = [x for x in veri if (x.get("plaka_sablonu") or "").startswith("tr/")]
    tekrar: dict[str, int] = {}
    for x in veri:
        tekrar[x["plaka"]] = tekrar.get(x["plaka"], 0) + 1
    veri = [x for x in veri if tekrar[x["plaka"]] >= TEKRAR_ESIGI]
    veri.sort(key=lambda x: x["okuma_zamani"])
    gecisler: list[dict] = []
    for x in veri:
        t = datetime.fromisoformat(x["okuma_zamani"].replace("Z", "+00:00"))
        if gecisler and (t - gecisler[-1]["son"]).total_seconds() <= KUMELEME_SN:
            gecisler[-1]["son"] = t
            gecisler[-1]["okumalar"].append(x["plaka"])
        else:
            gecisler.append({"ilk": t, "son": t, "okumalar": [x["plaka"]]})
    for g in gecisler:
        g["plaka"] = max(set(g["okumalar"]), key=g["okumalar"].count)
        g["orta"] = g["ilk"] + (g["son"] - g["ilk"]) / 2
    return gecisler


def segment_bul(db_yolu: str, camera_id: str, an: datetime) -> tuple[str, datetime] | None:
    """`an`'ı kapsayan kayıt segmentinin (mutlak yol, başlangıç) çifti; yoksa None."""
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
    for p, st, d in rows:
        b = datetime.fromisoformat(st)
        s = b + timedelta(seconds=float(d or 60))
        if b <= an <= s:
            return str(kok / p), b
    return None


def sessiz_segment_sec(db_yolu: str, camera_id: str, gecisler: list[dict],
                       adet: int, tohum: int = 0) -> list[tuple[str, datetime]]:
    """Hiçbir TRASSIR geçişine ±5 dk yakın olmayan, rastgele arşiv segmentleri."""
    from src.recorder import kayit_kok
    from src.config import load_config
    kok = kayit_kok(load_config(None))
    c = sqlite3.connect(db_yolu)
    try:
        rows = c.execute(
            "SELECT path, start_time FROM recordings WHERE camera_id=?", (camera_id,)
        ).fetchall()
    finally:
        c.close()
    tampon = timedelta(minutes=5)
    aday = []
    for p, st in rows:
        b = datetime.fromisoformat(st)
        if not any(g["ilk"] - tampon <= b <= g["son"] + tampon for g in gecisler):
            aday.append((str(kok / p), b))
    random.Random(tohum).shuffle(aday)
    return aday[:adet]


def _cfg(ocr: str | None = None):
    """Yapılandırmayı yükler; `ocr` verilirse yalnız BELLEKTEKİ kopyada override
    eder — config.yaml diskte değişmez, A/B testleri kalıcı yan etki bırakmaz."""
    from src.config import load_config
    cfg = load_config(None)
    if ocr:
        cfg._data["plate"]["ocr"] = ocr
    return cfg


def gecisi_degerlendir(db_yolu: str, camera_id: str, gecis: dict, ocr: str | None = None) -> dict:
    """Bir geçişin segmentini tarar, TRASSIR okumasıyla karşılaştırır.

    Segment DB'de görünse bile dosya diskte OLMAYABİLİR: arşiv kotası
    (`record.max_size_gb`) arka planda budama yapıyor ve uzun süren bir A/B
    koşusu (model başına ~1 saat) bu budamayla yarışır — ölçüldü 2026-09-04:
    test başında seçilen bir segment 52 dk sonra silinmişti. `run_plate`'in
    fırlattığı FileNotFoundError burada YUTULMAZ, "segment yok" ile AYNI
    sonuca (None) düşürülür — böylece tek eksik dosya tüm A/B koşusunu
    (ve o modelin diske hiç yazılmamış sonuçlarını) çökertmez.
    """
    from src.plate import run_plate
    bulunan = segment_bul(db_yolu, camera_id, gecis["orta"])
    if bulunan is None:
        return {**gecis, "segment": None, "voted": [], "en_yakin": None, "mesafe": None}
    yol, _bas = bulunan
    try:
        r = run_plate(yol, _cfg(ocr), store=None, camera_id="plate-eval")
    except FileNotFoundError:
        return {**gecis, "segment": None, "voted": [], "en_yakin": None, "mesafe": None}
    voted = [v["plate"] for v in r.voted]
    if voted:
        en_yakin = min(voted, key=lambda p: levenshtein(p, gecis["plaka"]))
        mesafe = levenshtein(en_yakin, gecis["plaka"])
    else:
        en_yakin, mesafe = None, None
    return {"plaka": gecis["plaka"], "segment": Path(yol).name, "voted": voted,
            "en_yakin": en_yakin, "mesafe": mesafe, "tam_isabet": en_yakin == gecis["plaka"]}


def _gecis_satiri(r: dict) -> str:
    if not r["segment"]:
        return f"{r['plaka']:10} (arşivde segment yok)"
    return (f"{r['plaka']:10} {r['segment']:22} {str(r['en_yakin']):10} "
            f"{str(r['mesafe']):7} {'EVET' if r['tam_isabet'] else 'hayır'}")


def _ozet_yazdir(bulunan: list[dict], toplam: int) -> None:
    tam = sum(1 for r in bulunan if r["tam_isabet"])
    print(f"\ngeçiş: {toplam}  arşivde bulunan: {len(bulunan)}  tam isabet: {tam}")
    if not bulunan:
        return
    print(f"tam isabet oranı: {tam/len(bulunan):.2%}")
    mesafeler = [r["mesafe"] for r in bulunan if r["mesafe"] is not None]
    if mesafeler:
        print(f"ortalama karakter mesafesi: {sum(mesafeler)/len(mesafeler):.2f}")


def _yazdir(sonuclar: list[dict], sessiz: list[dict]) -> None:
    print(f"\n{'plaka':10} {'segment':22} {'en_yakin':10} {'mesafe':7} {'tam?'}")
    for r in sonuclar:
        print(_gecis_satiri(r))
    _ozet_yazdir([r for r in sonuclar if r["segment"]], len(sonuclar))
    yp = sum(1 for r in sessiz if r["voted"])
    print(f"\nsessiz segment: {len(sessiz)}  plaka üreten: {yp}  "
          f"(TRASSIR referansı yok, ADAY yanlış pozitif)")


def gecisleri_degerlendir(db_yolu: str, camera_id: str, gecisler: list[dict],
                          ocr: str | None = None) -> list[dict]:
    sonuclar = []
    for i, g in enumerate(gecisler, 1):
        r = gecisi_degerlendir(db_yolu, camera_id, g, ocr)
        sonuclar.append(r)
        print(f"  [{i}/{len(gecisler)}] {g['plaka']} -> "
              f"{r.get('en_yakin')} (mesafe {r.get('mesafe')})", flush=True)
    return sonuclar


def sessizleri_degerlendir(db_yolu: str, camera_id: str, gecisler: list[dict],
                           adet: int, ocr: str | None = None) -> list[dict]:
    """TRASSIR olayı olmayan segmentlerde ADAY yanlış pozitif taraması.

    Segment listesi koşu BAŞINDA sabitlenir ama arşiv budaması koşu SÜRERKEN
    de çalışır (bkz. `gecisi_degerlendir` docstring) — dosya silinmişse
    atlanır, tüm modelin sonucu kaybolmaz.
    """
    from src.plate import run_plate
    yerler = sessiz_segment_sec(db_yolu, camera_id, gecisler, adet)
    sessiz = []
    for i, (yol, _bas) in enumerate(yerler, 1):
        try:
            r = run_plate(yol, _cfg(ocr), store=None, camera_id="plate-eval-sessiz")
        except FileNotFoundError:
            print(f"  [sessiz {i}/{len(yerler)}] {Path(yol).name} -> "
                  "(budanmış, atlandı)", flush=True)
            continue
        sessiz.append({"segment": Path(yol).name, "voted": [v["plate"] for v in r.voted]})
        print(f"  [sessiz {i}/{len(yerler)}] {Path(yol).name} -> "
              f"{sessiz[-1]['voted'] or '-'}", flush=True)
    return sessiz


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--db", default="output/aurasvision.db")
    ap.add_argument("--sessiz-ornek", type=int, default=15)
    ap.add_argument("--ocr", default=None,
                    help="fast-plate-ocr modeli (vars: config.yaml plate.ocr) — "
                         "yalnız bu koşu için, diske yazmaz (A/B testi için)")
    ap.add_argument("--out", default="output/plate_eval_gt/plate_eval_gt.json")
    a = ap.parse_args(argv)
    gecisler = gt_gecisleri(a.gt)
    print(f"{len(gecisler)} güvenilir geçiş (tr/ şablonlu + 2+ tekrar) · ocr={a.ocr or '(config varsayılanı)'}")
    sonuclar = gecisleri_degerlendir(a.db, a.camera, gecisler, a.ocr)
    sessiz = sessizleri_degerlendir(a.db, a.camera, gecisler, a.sessiz_ornek, a.ocr)
    _yazdir(sonuclar, sessiz)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"gecisler": sonuclar, "sessiz": sessiz}, indent=2,
                              default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
