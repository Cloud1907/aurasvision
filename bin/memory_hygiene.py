#!/usr/bin/env python3
"""Hafıza bakım robotu — bayat/çelişen/kaynaksız kayıtları işaretler.

AurasAgents hafıza otoritesi (AGENTS.md):
  1. AGENTS.md + docs/decisions/  (kanonik)
  2. Run/PR kayıtları
  3. Auto-memory  (disposable — hiçbir iş buna bağımlı olamaz)

Bu araç 2 ve 3. katmanı denetler; 90 günden eski, kaynaksız veya çelişki
işareti taşıyan kayıtları RAPORLAR (silmez — insan kararı). ADR ve AGENTS.md
kanonik olduğu için asla otomatik işaretlenmez.

Kullanım:
  python3 bin/memory_hygiene.py                 # varsayılan konumları tarar
  python3 bin/memory_hygiene.py --path DIR      # ek konum
  python3 bin/memory_hygiene.py --today 2026-07-24   # referans tarih (test)
  python3 bin/memory_hygiene.py --max-age 90    # bayatlık eşiği (gün)

Çıktı: bulgu listesi. Kritik bulgu (kanonik katmanda kaynaksız karar) varsa
exit 1; yalnız öneri varsa exit 0.
"""
import argparse
import datetime as dt
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# İç göstergeler — memory kayıtlarında beklenen provenance alanları
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SECRET_RE = re.compile(
    r"("
    r"sk-[A-Za-z0-9]{16,}"                      # OpenAI-tarzı anahtar
    r"|ghp_[A-Za-z0-9]{20,}"                    # GitHub token
    r"|AKIA[0-9A-Z]{16}"                        # AWS access key id
    r"|AIza[0-9A-Za-z_\-]{35}"                  # Google API key
    r"|xox[baprs]-[0-9A-Za-z-]{10,}"           # Slack token
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"          # özel anahtar bloğu
    r"|(?:authorization\s*[:=]|bearer)\s*['\"]?(?:basic|bearer|digest)?\s*[A-Za-z0-9_\-\.+/=]{16,}"  # Authorization: Basic/Bearer (base64 dahil)
    r"|password\s*[:=]\s*['\"][^'\"]{6,}"       # hardcoded parola
    r")", re.I)
CONFLICT_MARKERS = ("çelişki", "conflict", "eski karar", "yanlış çıktı",
                    "superseded", "geçersiz")


def parse_date(s):
    m = DATE_RE.search(s or "")
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None



def scan_file(path, today, max_age, findings):
    rel = os.path.relpath(path, ROOT)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        # Okunamayan dosyayı sessizce yutma — bulgu olarak raporla.
        findings.append(("OKUNAMADI", rel, f"taranamadı: {type(e).__name__}"))
        return
    # Secret sızıntısı — her katmanda kritik
    if SECRET_RE.search(text):
        findings.append(("KRİTİK", rel, "olası secret sızıntısı — hafızadan temizle"))

    # Bayatlık: dosyada/adında bir tarih varsa ve eşiği aşıyorsa
    dates = [parse_date(line) for line in text.splitlines()]
    dates = [d for d in dates if d]
    newest = max(dates) if dates else parse_date(rel)
    if newest and (today - newest).days > max_age:
        findings.append(("BAYAT", rel,
                         f"{(today - newest).days} gün dokunulmamış "
                         f"(>{max_age}) — gözden geçir veya emekliye ayır"))

    # Çelişki işareti
    low = text.lower()
    for mk in CONFLICT_MARKERS:
        if mk in low:
            findings.append(("ÇELİŞKİ", rel,
                             f"'{mk}' işareti — kanonik kaynakla karşılaştır"))
            break

    # Kaynaksız kalıcı karar: 'karar/decision' geçen ama kaynak yok.
    # İndeks dosyaları (MEMORY.md) pointer taşır, karar kaydı değildir — atla.
    is_index = os.path.basename(path).upper() == "MEMORY.MD"
    if not is_index and ("karar" in low or "decision" in low) and \
       not re.search(r"(commit|sha|adr|pr #|http|docs/decisions)", low):
        findings.append(("KAYNAKSIZ", rel,
                         "karar var ama provenance (commit/ADR/PR/URL) yok"))


def default_targets():
    t = []
    # Proje içi kanonik/karar kayıtları
    for d in ("docs/decisions", ".agent-ofis", ".agents/reports"):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            t.append(p)
    # Kullanıcı auto-memory (varsa). Claude proje-slug'ı mutlak yoldan türetilir;
    # sabit /Users/... yolu yok (no hidden local dependency ilkesi).
    slug = os.path.abspath(ROOT).replace("/", "-")
    home = os.path.expanduser(os.path.join("~/.claude/projects", slug, "memory"))
    if os.path.isdir(home):
        t.append(home)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--max-age", type=int, default=90)
    ap.add_argument("--today", default=None)
    args = ap.parse_args()

    today = parse_date(args.today) if args.today else dt.date.today()
    if today is None:
        print("HATA: --today YYYY-MM-DD biçiminde olmalı")
        return 2

    targets = args.path or default_targets()
    if not targets:
        # Çıktı sözleşmesi: rapor başlığı her koşumda basılır (yeni projede de).
        print("HAFIZA BAKIMI: 0 kayıt tarandı, 0 bulgu")
        print("  taranacak hafıza konumu yok (henüz kayıt yok) — temiz ✓")
        return 0

    findings = []
    scanned = 0
    for t in targets:
        if os.path.isfile(t):
            scan_file(t, today, args.max_age, findings)
            scanned += 1
        else:
            for root, _, files in os.walk(t):
                for f in files:
                    if f.endswith(".md"):
                        scan_file(os.path.join(root, f), today,
                                  args.max_age, findings)
                        scanned += 1

    print(f"HAFIZA BAKIMI: {scanned} kayıt tarandı, {len(findings)} bulgu")
    if not findings:
        print("  temiz ✓")
        return 0
    critical = 0
    for level, rel, msg in findings:
        mark = "✗" if level in ("KRİTİK", "KAYNAKSIZ") else "•"
        print(f"  {mark} [{level}] {rel}: {msg}")
        if level in ("KRİTİK", "KAYNAKSIZ"):
            critical += 1
    print("")
    print("Not: bu araç SİLMEZ; kalıcılaştırma/emeklilik reviewed PR ile olur "
          "(AGENTS.md hafıza otoritesi).")
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
