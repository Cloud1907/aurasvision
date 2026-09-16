"""Canlı plaka olayları kıyası — AurasVision `plate_events` vs TRASSIR `lpr.jsonl`.

`scripts/plate_eval_gt.py` arşiv segmentlerini yeniden tarar (model A/B için
doğru yol). Bu betik ise ÜRETİMDE zaten yazılmış iki olay akışını yan yana
koyar: AurasVision'ın canlı hattının DB'ye yazdığı `plate_events` ile
connector'ın TRASSIR'dan düz JSON'a döktüğü
``C:\\ProgramData\\OneGateData\\daily\\<gün>\\lpr.jsonl``. Model çalıştırmaz,
saniyeler içinde biter, günler boyu biriken veriyle çalışır.

Yöntem:
  * Her iki tarafta birbirine `--kume-sn`'den yakın okumalar TEK geçiş sayılır
    (aynı araç birden çok kez okunur; AurasVision `reads` ile oy verir,
    TRASSIR girişten çıkışa birden çok kayıt üretebilir).
  * TRASSIR geçişi ile ±`--pencere-sn` içinde en yakın AurasVision geçişi
    eşlenir (her geçiş en çok bir kez). Eşleşende tam isabet + Levenshtein.
  * Eşleşmeyen TRASSIR geçişi → AurasVision KAÇIRDI (TRASSIR'ın da hatalı
    olabileceği not edilir; `tr/` şablonlu olanlar güvenilir sayılır).
  * Eşleşmeyen AurasVision geçişi → ADAY fazla okuma (TRASSIR'ın kaçırmış
    olması da mümkündür).
  * TEKRAR süzgeci (`--tekrar-dk`, vars. 30): görüş alanında PARK ETMİŞ araç
    her iki motorda da gün boyu yeniden okunuyor (ölçüldü 2026-09-16: aynı
    araç AurasVision'da 107, TRASSIR'da 3 günde 61 olay; okumalar
    `34NRL083/34NR4083/34NRL063...` gibi 1-2 karakter oynuyor). Son
    `--tekrar-dk` dakika içinde aynı tarafta ≤`--tekrar-mesafe` karakter
    mesafeli bir geçiş varsa yeni geçiş "tekrar" işaretlenir. İşaret
    EŞLEŞTİRMEYİ DEĞİŞTİRMEZ (denendi 2026-09-16: tekrarları eşleştirmeden
    çıkarmak iki tarafta asimetrik budayıp "kaçırdı"yı şişirdi); yalnız
    eşleşmeyen geçişleri ikiye ayırır — `fazla_tekrar` / `kacirdi_tekrar`
    park etmiş aracın yeniden okuması, `fazla` / `kacirdi` gerçek ayrışma.
    Saatler arayla dönen servis aracı (34BT7027) bu süzgece takılmaz.

Saat: `plate_events.ts_seconds` epoch UTC, TRASSIR `okuma_zamani` ISO UTC.
`time` sütunu ts'ten birkaç sn geç (DB yazım anı) — ts_seconds kullanılır.

Kullanım:
  python scripts/plate_live_kiyas.py --gun 2026-09-15 --gun 2026-09-16
  python scripts/plate_live_kiyas.py --bastan 2026-09-05 --sona 2026-09-16
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.plate_eval_gt import levenshtein  # noqa: E402

TRASSIR_GUNLUK = Path(r"C:\ProgramData\OneGateData\daily")
KAMERA_ESLEME = {"tN9q9YqX": "kamera-204"}   # TRASSIR kanal guid -> AurasVision kamera


def _t(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def trassir_oku(gunler: list[date], guid: str) -> list[dict]:
    out = []
    for g in gunler:
        yol = TRASSIR_GUNLUK / g.isoformat() / "lpr.jsonl"
        if not yol.exists():
            continue
        for satir in yol.read_text(encoding="utf-8").splitlines():
            if not satir.strip():
                continue
            x = json.loads(satir)
            if x.get("kamera_guid") != guid or not x.get("plaka"):
                continue
            out.append({"t": _t(x["okuma_zamani"]), "plaka": x["plaka"].upper(),
                        "guvenilir": (x.get("plaka_sablonu") or "").startswith("tr/"),
                        "kalite": x.get("kalite")})
    out.sort(key=lambda r: r["t"])
    return out


def auras_oku(db: str, camera_id: str, bas: datetime, son: datetime) -> list[dict]:
    c = sqlite3.connect(db)
    try:
        rows = c.execute(
            "SELECT ts_seconds, plate, conf, reads FROM plate_events"
            " WHERE camera_id=? AND ts_seconds BETWEEN ? AND ? ORDER BY ts_seconds",
            (camera_id, bas.timestamp(), son.timestamp())).fetchall()
    finally:
        c.close()
    return [{"t": datetime.fromtimestamp(ts, timezone.utc), "plaka": p.upper(),
             "conf": cf, "reads": rd} for ts, p, cf, rd in rows]


def kumele(okumalar: list[dict], kume_sn: float) -> list[dict]:
    """Zamanca yakın okumaları geçişe toplar; geçişin plakası oy çokluğu.

    AurasVision tarafında oy ağırlığı `reads` (kaç karede okunduğu), TRASSIR
    tarafında her kayıt 1 oy. Tüm farklı okumalar `adaylar`da saklanır — bir
    tarafın "yakın ama yanlış" ikinci okuması da mesafe hesabında görülsün.
    """
    gecisler: list[dict] = []
    for r in okumalar:
        if gecisler and (r["t"] - gecisler[-1]["son"]).total_seconds() <= kume_sn:
            g = gecisler[-1]
            g["son"] = r["t"]
            g["okumalar"].append(r)
        else:
            gecisler.append({"ilk": r["t"], "son": r["t"], "okumalar": [r]})
    for g in gecisler:
        oy: Counter = Counter()
        for r in g["okumalar"]:
            oy[r["plaka"]] += max(1, r.get("reads") or 1)
        g["plaka"] = oy.most_common(1)[0][0]
        g["adaylar"] = sorted(oy, key=lambda p: -oy[p])
        g["orta"] = g["ilk"] + (g["son"] - g["ilk"]) / 2
        g["guvenilir"] = any(r.get("guvenilir") for r in g["okumalar"])
    return gecisler


def tekrar_isaretle(gecisler: list[dict], tekrar_dk: float, max_mesafe: int = 1) -> None:
    """Park etmiş aracın yeniden okumalarını işaretler (bkz. modül docstring).

    Karar yalnız KENDİ tarafındaki önceki geçişlere bakar; tekrar sayılan
    geçiş de sonraki karşılaştırmada referans olur (araç saatlerce dururken
    zincir kopmaz).
    """
    if tekrar_dk <= 0:
        for g in gecisler:
            g["tekrar"] = False
        return
    pencere = timedelta(minutes=tekrar_dk)
    for i, g in enumerate(gecisler):
        g["tekrar"] = False
        for o in reversed(gecisler[:i]):
            if g["ilk"] - o["son"] > pencere:
                break
            if any(levenshtein(a, b) <= max_mesafe for a in g["adaylar"] for b in o["adaylar"]):
                g["tekrar"] = True
                break


def esle(tr: list[dict], av: list[dict], pencere_sn: float) -> list[dict]:
    """Her TRASSIR geçişine en yakın, henüz kullanılmamış AurasVision geçişi.

    Önce zamanca en yakın çiftler eşlenir (açgözlü, mesafeye göre sıralı) —
    yoğun trafikte iki aracın art arda geçtiği durumda yanlış çaprazlamayı
    azaltır.
    """
    ciftler = []
    for i, g in enumerate(tr):
        for j, a in enumerate(av):
            d = abs((a["orta"] - g["orta"]).total_seconds())
            if d <= pencere_sn:
                ciftler.append((d, i, j))
    ciftler.sort()
    tr_es: dict[int, int] = {}
    av_kul: set[int] = set()
    for d, i, j in ciftler:
        if i in tr_es or j in av_kul:
            continue
        tr_es[i] = j
        av_kul.add(j)
    sonuc = []
    for i, g in enumerate(tr):
        j = tr_es.get(i)
        if j is None:
            sonuc.append({"tur": "kacirdi_tekrar" if g.get("tekrar") else "kacirdi",
                          "t": g["orta"], "trassir": g["plaka"],
                          "guvenilir": g["guvenilir"], "auras": None, "mesafe": None})
            continue
        a = av[j]
        en_yakin = min(a["adaylar"], key=lambda p: levenshtein(p, g["plaka"]))
        sonuc.append({"tur": "eslesti", "t": g["orta"], "trassir": g["plaka"],
                      "guvenilir": g["guvenilir"], "auras": a["plaka"],
                      "auras_en_yakin": en_yakin,
                      "mesafe": levenshtein(a["plaka"], g["plaka"]),
                      "mesafe_en_yakin": levenshtein(en_yakin, g["plaka"]),
                      "fark_sn": round((a["orta"] - g["orta"]).total_seconds(), 1)})
    for j, a in enumerate(av):
        if j not in av_kul:
            sonuc.append({"tur": "fazla_tekrar" if a.get("tekrar") else "fazla", "t": a["orta"], "trassir": None, "guvenilir": None,
                          "auras": a["plaka"], "mesafe": None,
                          "reads": sum(r.get("reads") or 0 for r in a["okumalar"])})
    sonuc.sort(key=lambda r: r["t"])
    return sonuc


def ozet(sonuc: list[dict]) -> dict:
    es = [r for r in sonuc if r["tur"] == "eslesti"]
    kac = [r for r in sonuc if r["tur"].startswith("kacirdi")]
    faz = [r for r in sonuc if r["tur"].startswith("fazla")]
    guv = [r for r in es + kac if r["guvenilir"]]
    guv_es = [r for r in es if r["guvenilir"]]
    o = {
        "trassir_gecis": len(es) + len(kac),
        "auras_gecis": len(es) + len(faz),
        "eslesen": len(es),
        "auras_kacirdi": len(kac),
        "auras_fazla": len(faz),
        "tam_isabet": sum(1 for r in es if r["mesafe"] == 0),
        "isabet_1_karakter": sum(1 for r in es if r["mesafe"] == 1),
        "aday_ile_tam": sum(1 for r in es if r["mesafe_en_yakin"] == 0),
        "ort_mesafe": round(sum(r["mesafe"] for r in es) / len(es), 2) if es else None,
        "guvenilir_trassir_gecis": len(guv),
        "guvenilir_eslesen": len(guv_es),
        "guvenilir_tam_isabet": sum(1 for r in guv_es if r["mesafe"] == 0),
        "guvenilir_kacirdi": sum(1 for r in kac if r["guvenilir"]),
        "fazla_tek_okuma": sum(1 for r in faz if (r.get("reads") or 0) <= 1),
        "kacirdi_tekrar": sum(1 for r in kac if r["tur"] == "kacirdi_tekrar"),
        "fazla_tekrar": sum(1 for r in faz if r["tur"] == "fazla_tekrar"),
    }
    if es:
        o["ort_fark_sn"] = round(sum(r["fark_sn"] for r in es) / len(es), 1)
    return o


def _yazdir(sonuc: list[dict], o: dict, ayrinti: bool) -> None:
    if ayrinti:
        print(f"\n{'zaman (UTC)':20} {'tür':8} {'TRASSIR':10} {'AurasVision':11} {'mesafe':6} not")
        for r in sonuc:
            nott = ""
            if r["tur"] == "eslesti":
                nott = "TAM" if r["mesafe"] == 0 else (
                    f"aday tam: {r['auras_en_yakin']}" if r["mesafe_en_yakin"] == 0 else "")
                if not r["guvenilir"]:
                    nott += " (TRASSIR şablon dışı)"
            elif r["tur"].startswith("kacirdi"):
                nott = "güvenilir" if r["guvenilir"] else "TRASSIR şablon dışı"
            else:
                nott = f"reads={r.get('reads')}"
            if r["tur"].endswith("_tekrar"):
                nott += " · park etmiş araç yeniden okundu"
            print(f"{r['t'].strftime('%Y-%m-%d %H:%M:%S'):20} {r['tur']:8} "
                  f"{str(r['trassir'] or '-'):10} {str(r['auras'] or '-'):11} "
                  f"{str(r['mesafe'] if r['mesafe'] is not None else ''):6} {nott}")
    print("\n--- ÖZET ---")
    print(f"TRASSIR geçişi: {o['trassir_gecis']}   AurasVision geçişi: {o['auras_gecis']}")
    print(f"eşleşen: {o['eslesen']}   AurasVision kaçırdı: {o['auras_kacirdi']} "
          f"(park tekrarı: {o['kacirdi_tekrar']})   AurasVision fazla: {o['auras_fazla']} "
          f"(park tekrarı: {o['fazla_tekrar']}, tek karelik: {o['fazla_tek_okuma']})")
    if o["eslesen"]:
        print(f"eşleşende tam isabet: {o['tam_isabet']}/{o['eslesen']} "
              f"({o['tam_isabet']/o['eslesen']:.1%})   1 karakter: {o['isabet_1_karakter']}   "
              f"adaylardan biri tam: {o['aday_ile_tam']}   ort. mesafe: {o['ort_mesafe']}   "
              f"ort. zaman farkı: {o.get('ort_fark_sn')} sn")
    if o["guvenilir_trassir_gecis"]:
        g = o["guvenilir_trassir_gecis"]
        print(f"güvenilir (tr/ şablonlu) TRASSIR geçişi: {g}   eşleşen: {o['guvenilir_eslesen']} "
              f"({o['guvenilir_eslesen']/g:.1%})   tam isabet: {o['guvenilir_tam_isabet']} "
              f"({o['guvenilir_tam_isabet']/g:.1%} tüm güvenilir geçişlere göre)   "
              f"kaçırılan: {o['guvenilir_kacirdi']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gun", action="append", type=date.fromisoformat,
                    help="YYYY-MM-DD (tekrarlanabilir)")
    ap.add_argument("--bastan", type=date.fromisoformat)
    ap.add_argument("--sona", type=date.fromisoformat)
    ap.add_argument("--camera", default="kamera-204")
    ap.add_argument("--guid", default=None, help="TRASSIR kanal guid (vars: kameraya göre)")
    ap.add_argument("--db", default="output/aurasvision.db")
    ap.add_argument("--kume-sn", type=float, default=90)
    ap.add_argument("--pencere-sn", type=float, default=60)
    ap.add_argument("--tekrar-dk", type=float, default=30,
                    help="park etmiş araç tekrar süzgeci penceresi, 0 kapatır")
    ap.add_argument("--tekrar-mesafe", type=int, default=1,
                    help="tekrar sayılmak için azami karakter mesafesi")
    ap.add_argument("--ayrinti", action="store_true", help="her geçişi satır satır yaz")
    ap.add_argument("--out", default="output/plate_live_kiyas/plate_live_kiyas.json")
    a = ap.parse_args(argv)

    gunler = list(a.gun or [])
    if a.bastan:
        son = a.sona or a.bastan
        gunler += [a.bastan + timedelta(days=i) for i in range((son - a.bastan).days + 1)]
    if not gunler:
        gunler = [datetime.now(timezone.utc).date()]
    gunler = sorted(set(gunler))
    guid = a.guid or next((g for g, k in KAMERA_ESLEME.items() if k == a.camera), None)
    if not guid:
        ap.error(f"{a.camera} için TRASSIR guid bilinmiyor, --guid ver")

    bas = datetime.combine(gunler[0], datetime.min.time(), timezone.utc)
    son = datetime.combine(gunler[-1] + timedelta(days=1), datetime.min.time(), timezone.utc)
    tr = kumele(trassir_oku(gunler, guid), a.kume_sn)
    av = kumele(auras_oku(a.db, a.camera, bas, son), a.kume_sn)
    tekrar_isaretle(tr, a.tekrar_dk, a.tekrar_mesafe)
    tekrar_isaretle(av, a.tekrar_dk, a.tekrar_mesafe)
    print(f"günler: {', '.join(g.isoformat() for g in gunler)}  kamera: {a.camera} ({guid})")
    print(f"TRASSIR okuma→geçiş: {sum(len(g['okumalar']) for g in tr)}→{len(tr)}   "
          f"AurasVision olay→geçiş: {sum(len(g['okumalar']) for g in av)}→{len(av)}")
    sonuc = esle(tr, av, a.pencere_sn)
    o = ozet(sonuc)
    _yazdir(sonuc, o, a.ayrinti)

    gun_ozet = {}
    for g in gunler:
        gs = [r for r in sonuc if r["t"].date() == g]
        if gs:
            gun_ozet[g.isoformat()] = ozet(gs)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"gunler": [g.isoformat() for g in gunler], "ozet": o,
                               "gun_ozet": gun_ozet, "gecisler": sonuc},
                              indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\nham: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
