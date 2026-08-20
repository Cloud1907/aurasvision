#!/usr/bin/env python3
"""Süitin ortam ön-koşulları — eksik bağımlılık GÖRÜNÜR olsun diye tek yerde.

Neden bu dosya var: `import yaml` doğrudan test modülünün tepesinde dururken
PyYAML'sız yorumlayıcıda modül import'ta çöker ve içindeki testler süiteden
YOK OLUR. Çıktı "3 hata" der; gerçek "34 test hiç koşmadı"dır. Kapsamın
daraldığını hiçbir satır söylemez — sayının kendisi yanıltır. 2026-08-07
ölçümü, aynı repo: python3.13 (PyYAML var) 220 test / OK, python3 (PyYAML yok)
186 test / 3 hata.

Doğru davranış iki katmanlıdır ve biri diğerinin yerine geçmez:
  1. Bağımlılık eksikse test ATLANIR — sayıda kalır, gerekçesi yazılır
     (`pyyaml_gerekir`). Kapsam artık sessizce daralamaz.
  2. `tests/test_ortam.py` eksikliği TEK ve yüksek sesli bir hataya çevirir.
     Atlama tek başına yetmez: exit 0 veren eksik süit CI'da "geçti" diye
     okunur, oysa "koşmadı" ile "geçti" aynı şey değildir.
"""
import os
import shutil
import subprocess
import sys
import unittest

try:
    import yaml
except ImportError:                 # kurulum eksiği — kural ihlali değil
    yaml = None

# Atlanan her testin yanında görünen kısa gerekçe.
PYYAML_SEBEP = ("PyYAML yok — bu test yaml okumadan anlamsız "
                "(python3 -m pip install pyyaml)")

# test_ortam'ın tek, yüksek sesli hatası: neyin kaybolduğunu ADIYLA söyler.
PYYAML_EKSIK = (
    "PyYAML kurulu değil — yaml'a bağlı testler ATLANDI, süit EKSİK koştu. "
    "Yukarıdaki 'skipped' sayısı koşmayan testlerdir; bu yorumlayıcıda "
    "'OK' TAM KAPSAM DEMEK DEĞİLDİR. Kurulum: python3 -m pip install pyyaml "
    "(ya da PyYAML'lı bir yorumlayıcı ile koş)."
)

#: Sınıf ya da metot üstünde: @pyyaml_gerekir
pyyaml_gerekir = unittest.skipUnless(yaml is not None, PYYAML_SEBEP)


# --- modül düzeyinde atlamanın TEK meşru kaydı ------------------------------
# sebep → ön-koşul yoklaması. Yoklama True ise "bu makinede o bağımlılık
# GERÇEKTEN yok" demektir; keşif bekçisi atlamayı ancak o zaman meşru sayar.
#
# Neden sebebi yalnız OKUMAK yetmez: `raise unittest.SkipTest("...")` bir
# modülün bütün testlerini süitten çıkarır ve çıkış kodunu 0 bırakır. Sebep
# denetlenmeseydi beyan kanıt yerine geçerdi — modül başına yazılan tek bir
# satır "Ran N"i sessizce daraltırdı (Codex bağımsız incelemesi, PR #47, P1).
# Yoklamayla birlikte, kayıtlı bir sebebi kopyalayan modül bağımlılığın VAR
# olduğu makinede blok alır.
#
# Yeni bir meşru atlama buraya ilan edilmeden var olamaz: burası, atlama
# kararının gözden geçirildiği tek yerdir. Kural `bin/kapsam_bekcisi.py`
# (`atlama_hukmu`) içinde, kapı `bin/validate.py`de.
MESRU_ATLAMALAR = {
    PYYAML_SEBEP: lambda: yaml is None,
}


# --- pre-push kapısının yorumlayıcı sözleşmesi -----------------------------
# Kapı (`bin/hooks/pre-push`, py_uygun) adayı ÇIKTIYLA sınar, çıkış koduyla
# değil: `/usr/bin/true` de 0 döner ve kapıyı sessizce geçerdi (denetim
# bulgusu 2026-08-07). Buradaki sınama o sözleşmenin birebir kopyasıdır —
# test kapının kabul edeceği yorumlayıcıyı, kapının ölçütüyle bulmalı.
_KANIT = "AURAS_PY_OK"
# Kapının kendi aday listesi + koşan yorumlayıcı. Sıra önemli: `sys.executable`
# başta, çünkü PyYAML'lıysa süitle aynı yorumlayıcıda kalmak en az sürprizli.
_ADAYLAR = (sys.executable, "python3", "python3.13", "python3.12",
            "python3.11", "/opt/homebrew/bin/python3.13")


def _kapiya_uygun(yol):
    try:
        p = subprocess.run(
            [yol, "-c", f'import yaml,sys; sys.stdout.write("{_KANIT}")'],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.stdout.strip() == _KANIT


def _yol_coz(aday):
    """Adayın MUTLAK yolu (bulunamazsa None).

    `abspath` şart: `shutil.which` göreli bir PATH girdisinde göreli yol
    döndürür (ör. `PATH=./araclar`). O yol testin çalışma dizininde çözülür
    ama kapı GEÇİCİ DEPONUN içinde koşar — orada çözülmez ve meşru override
    ortamın PATH biçimine bağlı olarak kırılır.
    """
    yol = shutil.which(aday) if aday else None
    return os.path.abspath(yol) if yol else None


def kapi_yorumlayicisi():
    """pre-push kapısının KABUL EDECEĞİ bir python3'ün TAM YOLU (yoksa None).

    Çıplak ad değil tam yol döner: dönen değer yalnız kapıya verilmiyor,
    kapının DUYURDUĞU yorumlayıcıyla da karşılaştırılıyor. `python3.13` gibi
    kısa bir ad başka bir yolun içine alt-dize olarak düşebilir ve karşılaştırma
    yanlışlıkla tutabilir; tam yol o gevşekliği kapatır.
    """
    for aday in _ADAYLAR:
        yol = _yol_coz(aday)
        if yol and _kapiya_uygun(yol):
            return yol
    return None


KAPI_PYTHON = kapi_yorumlayicisi()

# Neden atlamak burada sessizlik ÜRETMEZ: `sys.executable` PyYAML taşıyorsa
# ilk aday olarak seçilir, yani KAPI_PYTHON asla None olmaz. None ise
# `yaml` importu da çökmüştür ve `tests/test_ortam.py` zaten yüksek sesle
# kırmızı verir. Atlama tek sinyal olarak kalamaz.
kapi_yorumlayicisi_gerekir = unittest.skipUnless(
    KAPI_PYTHON is not None,
    "kapının kabul edeceği (PyYAML'lı) python3 yok — meşru override "
    "senaryosu bu makinede KURULAMAZ; bkz. test_ortam")
