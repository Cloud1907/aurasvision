#!/usr/bin/env python3
"""gitleaks muafiyeti — kapının KENDİ malzemesi sır sanılmasın.

Neden `kernel_dosyalari.py`'den ayrı: orası "hangi dosyalar motorun" sorusunu
yanıtlar; burası bambaşka bir soruyu — "üçüncü parti bir tarayıcı bizim
ürettiğimiz dosyaları yanlış pozitif sayıyor mu". İkincisi gitleaks'in kural
setiyle birlikte değişir, manifest'le değil; aynı dosyada durmaları yalnızca
ikisinin de kurulum sırasında gerekmesindendi.

Kural: muafiyet DAİMA gerekçelidir ve GÖRÜNÜR kalır (AGENTS.md). Buradaki iki
girdinin de ölçülmüş sebebi aşağıda yazılıdır.
"""
import os

GITLEAKS_CFG = ".gitleaks.toml"

# Manifest yalnız sha256 özeti taşır; gitleaks'in generic-api-key kuralı
# uzun hex bloklarını anahtar sanar. 4cast'te bu 7 yanlış pozitif üretip
# CI'ı bir haftadan uzun kırmızıda tuttu (2026-08-07). Dosyayı kernel
# ÜRETTİĞİ için sorun bağlı HER projede tekrarlanır — kurulumda çözülmeli.
MUAFIYET_BLOGU = """
[allowlist]
description = "AurasAgents kernel dosyalari — sir degil, kapinin kendi malzemesi"
paths = [
  # Manifest yalniz sha256 OZETI tasir; generic-api-key kurali uzun hex'i
  # anahtar saniyor (4cast: 7 yanlis pozitif, CI bir haftadan uzun kirmizi).
  '''\\.agents/\\.kernel-manifest\\.json''',
  # Skill eval fixture'lari KASITLI sahte anahtar tasir — tarayicinin kendi
  # kabul vakalari. Bizim tarayicimiz `--exclude */eval/*` ile diliyor ama
  # gitleaks bunu bilmiyordu ve her projede ayni yanlis pozitifi uretiyordu
  # (4Flow: stripe-access-token @ security-review/eval/cases.md, 2026-08-07).
  '''\\.agents/skills/.*/eval/.*''',
]
"""


def gitleaks_kullaniyor(kok):
    """Proje gitleaks koşuyor mu (config'i var ya da workflow'da anılıyor)."""
    if os.path.isfile(os.path.join(kok, GITLEAKS_CFG)):
        return True
    wf = os.path.join(kok, ".github", "workflows")
    if not os.path.isdir(wf):
        return False
    for ad in sorted(os.listdir(wf)):
        try:
            with open(os.path.join(wf, ad), encoding="utf-8",
                      errors="replace") as fh:
                if "gitleaks" in fh.read():
                    return True
        except OSError:
            continue
    return False


def manifest_muaf_mi(kok):
    """Manifest gitleaks allowlist'inde mi (yoksa yanlış pozitif üretir).

    'kernel-manifest' aranır, '.kernel-manifest.json' DEĞİL: gitleaks yol
    desenleri regex'tir ve nokta kaçışlıdır (`\\.kernel-manifest\\.json`).
    Düz nokta aramak kendi şablonumuzu bile eşleştirmiyordu (test yakaladı).
    """
    try:
        with open(os.path.join(kok, GITLEAKS_CFG), encoding="utf-8") as fh:
            metin = fh.read()
        # Eval fixture muafiyeti sonradan eklendi; ikisi de olmalı yoksa
        # kurulum "muaf" sanıp CI'ı yanlış pozitifle kırmızı bırakır.
        return "kernel-manifest" in metin and "skills/.*/eval" in metin
    except OSError:
        return False
