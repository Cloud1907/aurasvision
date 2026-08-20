#!/usr/bin/env python3
"""Yüzey sınıflandırması — bir yol NE tür kanıt yükümlülüğü doğurur?

Neden ayrı modül: `kapi.py` KARAR verir (kanıt yeterli mi, blok mu uyarı mı);
burası ÖLÇER (bu yol kaynak mı, risk yüzeyi mi, görünür yüzey mi). İkisi ayrı
değişme sebebi taşır: sınıflandırma bir yüzey sözlüğüdür, karar bir politika.

Ölçü DOSYA ADI DEĞİL YÜZEY (öz-denetim bulgusu 2026-08-16): eski desen ham
alt-dize arıyordu ve `tests/test_session_izolasyonu.py` ile
`docs/token-notlari.md` "risk yüzeyi" sayılıyordu — bir turu bizzat bloklamış,
sonra yanlış olduğu ölçülmüştü. Yanlış pozitif kapının güvenilirliğini yakar:
kullanıcı `--no-verify` alışkanlığı edinir, ki AGENTS.md'de yazılı en büyük
korku budur.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diller  # noqa: E402  (dil kapsamının tek tanımı)

# Dil kapsamı TEK kaynaktan (bin/diller.py): aynı soruyu üç ayrı listeyle
# cevaplamak, listelerin ayrışmasıyla biter — ve ayrıştıkları ölçüldü
# (H. Demir denetimi 2026-08-15). Bekçi: tests/test_diller.py
KAYNAK_UZANTI = tuple(sorted(diller.KAYNAK))
# Test dosyası imzaları.
TEST_YOL = re.compile(r"(^|/)tests?/|(^|/)test_|_test\.|\.test\.|\.spec\.")
# Risk yüzeyi: dokunulursa güvenlik incelemesi ister (AGENTS.md risk politikası).
#
# Ölçü DOSYA ADI DEĞİL YÜZEY (öz-denetim bulgusu 2026-08-16). Eski desen ham
# alt-dize arıyordu ve `tests/test_session_izolasyonu.py` ile
# `docs/token-notlari.md` "risk yüzeyi" sayılıyordu — bir turu bizzat
# BLOKLADI. Yanlış pozitif kapının güvenilirliğini yakar: kullanıcı
# `--no-verify` alışkanlığı edinir, ki AGENTS.md'de yazılı en büyük korku
# budur. Aynı ders UI_YOL'da 2026-08-01'de öğrenilmişti (yol-parçası sınırı).
RISK_DIZIN = re.compile(
    r"(^|/)(auth|kimlik|oturum|session|sessions|secret|secrets|credential"
    r"|credentials|payment|payments|odeme|ödeme|upload|uploads|permission"
    r"|permissions|migration|migrations|hooks)(/|$)", re.I)
RISK_DOSYA = re.compile(
    r"(^|/)\.env($|\.)"
    r"|(^|/)settings(\.local)?\.json$"
    r"|(^|/)[^/]*(auth|token|secret|credential|session|password|parola)[^/]*"
    r"\.(py|js|mjs|cjs|ts|tsx|jsx|cs|go|rb|java|kt|php|swift|sql|sh)$", re.I)
# Test ve doküman yüzeyi tek başına açık TAŞIYAMAZ: bir test dosyası
# üretimde çalışmaz, bir markdown istismar edilemez. İnceleme zorunluluğu
# buralarda gürültüdür — kapsam dışı bırakmak korumayı değil gürültüyü keser.
INCELEME_MUAF = re.compile(r"^(tests?|docs?|\.agents/reports)/", re.I)


def risk_yuzeyi_mi(yol):
    """Bu yol güvenlik incelemesi zorunlu kılan bir yüzey mi?"""
    # `lstrip("./")` KARAKTER KÜMESİ siler, önek değil: ".env" → "env"
    # olurdu ve secret dosyası risk yüzeyi sayılmazdı (bu testte yakalandı).
    rel = yol.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if INCELEME_MUAF.match(rel):
        return False
    return bool(RISK_DIZIN.search(rel) or RISK_DOSYA.search(rel))
# Görünür yüzey: değişirse birim testi yetmez, TIKLAMA kanıtı istenir.
UI_UZANTI = tuple(sorted(diller.GORUNUR))
# Yol-parçası sınırına demirli: aksi halde "security-review/", "overview/",
# "Interview/" içindeki "view" alt dizesi eşleşir ve markdown/backend dosyası
# görünür yüzey sanılır (2026-08-01 yanlış pozitifi — 4cast'te yakalandı).
UI_YOL = re.compile(
    r"(^|/)(components?|pages?|views?|screens?|web|ui|frontend)/", re.I)

# Büyük değişim eşikleri (Codex: 300 satır kaba; dosya sayısı + net satır).
E2E_CMD_RE = re.compile(r"(playwright|cypress|selenium|puppeteer|e2e)", re.I)
BUYUK_DOSYA = 5
BUYUK_SATIR = 150
