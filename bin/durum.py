#!/usr/bin/env python3
"""Tur tablosu — "hangi skill çağrıldı, ne yapıldı" sorusunun makine cevabı.

Kullanım:
  python3 bin/durum.py            # son 15 tur
  python3 bin/durum.py --n 50
  python3 bin/durum.py --json     # Agent Ofis projeksiyonu için

Sütunların anlamı:
  YÖNLENDİRİLEN  router'ın zorunlu tuttuğu skill (bin/route.py)
  YÜKLENEN       gerçekten Skill aracıyla yüklenen skill (PostToolUse kaydı)
  DURUM          uyumlu | SAPMA (başkası yüklendi) | ATLANDI (sessiz atlama)
                 | atlandı:<sebep> (gerekçesi kayda geçmiş) | sohbet

SAPMA/ATLANDI satırları hesap sorulacak yerlerdir: ajan yönlendirmeyi
gerekçesiz atlamışsa burada görünür.
"""
import argparse
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _run_event():
    spec = importlib.util.spec_from_file_location(
        "_re", os.path.join(HERE, "run_event.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def olaylari_oku(path):
    """Bozuk satırı atla, kalanı oku (kayıt disposable — kısmi okuma meşru)."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def _yeni_tur(olay=None):
    return {"ts": (olay or {}).get("ts", ""), "intent": (olay or {}).get("intent", ""),
            "routed": (olay or {}).get("routed"), "extras": (olay or {}).get("extras", []),
            "task_class": (olay or {}).get("task_class", ""),
            "skills": [], "subagent": [], "atlanan": {}, "kapandi": False}


def turlari_cikar(olaylar, session=None):
    """Olayları turlara böl. Tur sınırı OTURUM BAŞINA çizilir.

    Eşzamanlı oturumlar tek kayda yazar (`.claude/worktrees/`); sınır global
    çizilirse B'nin route olayı A'nın turunu kapatır ve A'nın yüklediği skill
    B'nin turuna düşer — tablo gerçekte olmayan bir SAPMA gösterir.
    Session taşımayan eski satırlar ortak kovada kalır (geriye uyum).
    """
    if session:
        olaylar = [o for o in olaylar if o.get("session") in (None, session)]
    turlar = []
    acik = {}                     # session -> o oturumun son turu
    for o in olaylar:
        kind = o.get("kind")
        s = o.get("session")
        if kind == "route":
            tur = _yeni_tur(o)
            turlar.append(tur)
            acik[s] = tur
            continue
        cur = acik.get(s)
        if cur is None:
            cur = _yeni_tur()
            turlar.append(cur)
            acik[s] = cur
        _uygula(cur, kind, o)
    for t in turlar:
        t["durum"] = _durum(t)
    return turlar


def _uygula(tur, kind, olay):
    """Olayı ait olduğu tura işle (dal sayısını turlari_cikar'dan ayırır)."""
    if kind == "skill" and olay.get("skill"):
        tur["skills"].append(olay["skill"])
    elif kind == "subagent" and olay.get("agent"):
        tur["subagent"].append(olay["agent"])
    elif kind == "skipped" and olay.get("skill"):
        tur.setdefault("atlanan", {})[olay["skill"]] = olay.get("reason", "?")
    elif kind == "stop":
        tur["kapandi"] = True


def _durum(tur):
    routed = tur.get("routed")
    skills = tur.get("skills", [])
    if not routed:
        return "sohbet" if not skills else "uyumlu"
    if routed in skills:
        return "uyumlu"
    if routed in (tur.get("atlanan") or {}):
        # Gerekçesi kayda geçmiş atlama: denetlenebilir (haklı demek değil).
        return f"atlandı:{tur['atlanan'][routed]}"
    return "SAPMA" if skills else "ATLANDI"


def _kirp(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def tablo(turlar):
    basliklar = ("#", "ZAMAN", "İSTEK", "SINIF", "YÖNLENDİRİLEN",
                 "YÜKLENEN", "AJAN", "DURUM")
    genis = (3, 5, 30, 12, 20, 20, 12, 20)
    satirlar = [" ".join(b.ljust(w) for b, w in zip(basliklar, genis)).rstrip()]
    satirlar.append(" ".join("─" * w for w in genis))
    for i, t in enumerate(turlar, 1):
        satirlar.append(" ".join(_kirp(v, w).ljust(w) for v, w in zip((
            i,
            t.get("ts", "")[11:16],
            t.get("intent", ""),
            t.get("task_class", ""),
            t.get("routed") or "—",
            ", ".join(t.get("skills")) or "—",
            ", ".join(t.get("subagent")) or "—",
            t.get("durum", ""),
        ), genis)).rstrip())
    return "\n".join(satirlar)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=None)
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--json", action="store_true",
                    help="makine-okunur çıktı (Agent Ofis projeksiyonu)")
    ap.add_argument("--session", default=None,
                    help="yalnız bu oturumun turları (eşzamanlı çalışmada)")
    args = ap.parse_args(argv)

    path = args.log or _run_event().log_path()
    turlar = turlari_cikar(olaylari_oku(path), args.session)[-args.n:]
    if args.json:
        print(json.dumps(turlar, ensure_ascii=False, indent=2))
        return 0
    if not turlar:
        print(f"Kayıt yok ({path}). Hook'lar kuruluysa ilk istekte dolmaya başlar.")
        return 0
    print(tablo(turlar))
    sapma = [t for t in turlar if t["durum"] in ("SAPMA", "ATLANDI")]  # sessizler
    if sapma:
        print(f"\n{len(sapma)} turda yönlendirilen skill yüklenmedi — "
              "gerekçesi konuşmada olmalı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
