#!/usr/bin/env python3
"""İş sözleşmesi (contract) okuma — PR gövdesinden ön risk ve birleşik risk.

Neden ayrı modül: `incele.py` merge KARARINI verir; burası kararın GİRDİSİNİ
okur (contract var mı, ön risk ne, üç kaynak nasıl birleşir). İkisi ayrı
değişme sebebi taşır — biri politika, diğeri veri okuma.

Bağımsız inceleme bulgusu (2026-08-15): Issue Form'un ÖN riski merge
kararına hiç girmiyordu; `incele.py` yalnız değişen yollara bakıyordu.
"Risk iki kez hesaplanır, eskalasyon yalnız yukarı" kuralı fiilen yarısı
çalışıyordu.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import surec  # noqa: E402
from risk import birlestir, risk_sinifi, yikici_aksiyon  # noqa: E402

_kos = surec.kos

# Issue Form'un "Ön risk sınıfı" alanı. Contract'lı işte doldurulur; micro
# işte contract YOKTUR ve bu ayrım korunmalıdır (AGENTS.md: diff tek cümleyle
# tarif edilebiliyorsa form atlanır).
_ON_RISK = re.compile(r"ön\s*risk[^\n:]*[:\s]+.*?\b(auto|approval|deny)\b",
                      re.I | re.S)


def on_risk_oku(govde, contractli):
    """Contract gövdesinden ön risk: sınıf | 'yok' | 'okunamadi'.

    Üç durum AYRI tutulur, çünkü ikisini karıştırmak iki ayrı hata üretir:
    - 'yok'       → contract hiç yok (micro iş). Ön risk uygulanamaz;
                    birleşime KATILMAZ, yoksa her micro PR approval'a çıkar
                    ve belgelenmiş micro yolu ölür.
    - 'okunamadi' → contract VAR ama risk alanı okunamıyor. Fail-closed:
                    approval. Bozuk contract otomatik merge üretemez.
    - sınıf       → okundu, birleşime girer.
    """
    if not contractli:
        return "yok"
    m = _ON_RISK.search(govde or "")
    return m.group(1).lower() if m else "okunamadi"


def pr_contract(pr):
    """(gövde, contract'lı mı) — PR gövdesi ve `contract` etiketi."""
    kod, out, _e = _kos("gh", "pr", "view", str(pr), "--json", "body,labels")
    if kod != 0:
        return "", False
    try:
        veri = json.loads(out or "{}") or {}
    except ValueError:
        return "", False
    etiketler = {(e or {}).get("name", "") for e in veri.get("labels") or []}
    return veri.get("body") or "", "contract" in etiketler


def birlesik_risk(dosyalar, diff, pr=None, contract=None):
    """Ön risk × yol riski × aksiyon riski — yalnız yukarı (AGENTS.md).

    Üç kaynak da tek başına eksiktir:
    - ön risk   : işin niyeti (contract'ta beyan edilir)
    - yol riski : diff'in dokunduğu yüzey
    - aksiyon   : diff'in İÇERİĞİ (veri silme, yetki genişletme) — yoldan
                  görülmez, `risk.yikici_aksiyon` içerikten okur

    `contract` testler için dışarıdan enjekte edilebilir (gh çağrısı yapmadan).
    """
    if contract is None:
        contract = pr_contract(pr) if pr is not None else ("", False)
    on = on_risk_oku(*contract)
    yol = risk_sinifi(dosyalar)
    aksiyon = "deny" if yikici_aksiyon(diff) else "auto"
    if on == "yok":                  # micro iş: ön risk uygulanamaz
        return birlestir(yol, aksiyon)
    if on == "okunamadi":            # bozuk contract otomatik merge üretemez
        return birlestir("approval", yol, aksiyon)
    return birlestir(on, yol, aksiyon)
