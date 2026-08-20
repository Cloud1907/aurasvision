#!/usr/bin/env python3
"""Proje test aracı tespiti — "tıklama kanıtı" kapısının bilgi kaynağı.

İlke: çekirdek hiçbir araca bağımlı değildir. Playwright, Cypress, jest,
pytest… hangisi kuruluysa o kullanılır; hiçbiri yoksa bu AÇIKÇA söylenir ve
ihtiyaç doğduğunda kurulum önerilir. Araç seçimi projenin, kanıt talebi
sistemindir.

Kullanım:
    python3 bin/araclar.py                 # insan okur
    python3 bin/araclar.py --json          # kapı/otomasyon okur
    python3 bin/araclar.py --path /proje   # başka projeyi tara
"""
import argparse
import json
import os

# (ad, tür, kanıt dosyası imzaları, koşum komutu önerisi)
IMZALAR = (
    ("playwright", "e2e", ("playwright.config.ts", "playwright.config.js",
                           "playwright.config.mjs", "e2e/"), "npx playwright test"),
    ("cypress", "e2e", ("cypress.config.ts", "cypress.config.js", "cypress/"),
     "npx cypress run"),
    ("selenium", "e2e", ("selenium/", "conftest_selenium.py"), "pytest selenium/"),
    ("vitest", "birim", ("vitest.config.ts", "vitest.config.js"), "npx vitest run"),
    ("jest", "birim", ("jest.config.js", "jest.config.ts"), "npx jest"),
    ("pytest", "birim", ("pytest.ini", "pyproject.toml", "conftest.py"),
     "python3 -m pytest"),
    ("unittest", "birim", ("tests/",), "python3 -m unittest discover -s tests"),
    ("dotnet-test", "birim", (".sln",), "dotnet test"),
    ("go-test", "birim", ("go.mod",), "go test ./..."),
)

# Tıklama kanıtı üretebilen tarayıcı araçları (MCP) — kurulum gerektirmez.
TARAYICI_MCP = ("mcp__chrome-devtools__click", "mcp__Claude_Browser__computer")


def tespit(kok):
    bulunan = []
    for ad, tur, imzalar, komut in IMZALAR:
        for imza in imzalar:
            yol = os.path.join(kok, imza)
            varsa = os.path.isdir(yol) if imza.endswith("/") else os.path.isfile(yol)
            if varsa:
                bulunan.append({"ad": ad, "tur": tur, "kanit": imza,
                                "komut": komut})
                break
    return bulunan


def ozet(kok):
    araclar = tespit(kok)
    return {
        "proje": os.path.abspath(kok),
        "araclar": araclar,
        "birim_var": any(a["tur"] == "birim" for a in araclar),
        "e2e_var": any(a["tur"] == "e2e" for a in araclar),
        "tarayici_mcp": list(TARAYICI_MCP),
        "oneri": oneri(araclar, kok),
    }


def oneri(araclar, kok):
    """E2E yoksa projenin yığınına uygun tek satırlık kurulum önerisi."""
    if any(a["tur"] == "e2e" for a in araclar):
        return None
    if os.path.isfile(os.path.join(kok, "package.json")):
        return ("E2E aracı yok. Tıklama kanıtı için: "
                "`npm init playwright@latest` (veya tarayıcı MCP'siyle elle "
                "tıklama — kurulum gerektirmez, ama tekrarlanabilir değildir).")
    if any(os.path.isfile(os.path.join(kok, f))
           for f in ("pyproject.toml", "requirements.txt")):
        return ("E2E aracı yok. Python yığını için: "
                "`pip install playwright && playwright install`.")
    return ("E2E aracı yok. Tıklama kanıtı şimdilik tarayıcı MCP'siyle elle "
            "üretilebilir; tekrarlanabilir kanıt için bir E2E aracı gerekir.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.getcwd())
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    o = ozet(args.path)
    if args.json:
        print(json.dumps(o, ensure_ascii=False, indent=2))
        return 0
    print(f"Proje: {o['proje']}")
    if not o["araclar"]:
        print("  Test aracı bulunamadı.")
    for a in o["araclar"]:
        print(f"  {a['tur']:5} {a['ad']:12} ({a['kanit']}) → {a['komut']}")
    print(f"  birim: {'✓' if o['birim_var'] else '✗'}   "
          f"e2e: {'✓' if o['e2e_var'] else '✗'}")
    if o["oneri"]:
        print(f"\n  {o['oneri']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
