#!/usr/bin/env python3
"""Eksik ortam TEK yüksek sesli hataya dönüşür — sessiz kapsam kaybı yok.

Bu dosya süitin kendi dürüstlük kapısıdır. `ortam.pyyaml_gerekir` eksik
bağımlılıkta testleri atlar (sayı korunur, gerekçe görünür); buradaki tek
test o atlamanın exit 0 ile "geçti" diye okunmasını engeller.

Neden ayrı bir hata: bir kapının YOKLUĞU asla "geçti" diye okunamaz. Eksik
süit yeşil dönerse CI kanıtı yalan söyler — kapsam daraldığı hâlde
`tests=passed` yazılır.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortam  # noqa: E402
from ortam import PYYAML_EKSIK, yaml  # noqa: E402


class OrtamTest(unittest.TestCase):
    def test_pyyaml_kurulu_degilse_suit_yesil_donmez(self):
        self.assertIsNotNone(yaml, PYYAML_EKSIK)


class YorumlayiciYoluTest(unittest.TestCase):
    """Kapıya verilen yol MUTLAK olmalı — kapı başka dizinde koşuyor.

    Codex bulgusu (PR #37): `shutil.which` göreli bir PATH girdisinde göreli
    yol döndürür. Test onu `AURAS_PYTHON` olarak kapıya verir, kapı ise
    geçici deponun içinde koşar — göreli yol orada çözülmez ve meşru override
    ortamın PATH biçimine bağlı olarak kırılır.
    """

    def test_goreli_path_girdisi_mutlak_yola_cevrilir(self):
        with tempfile.TemporaryDirectory(dir=".") as td:
            sahte = os.path.join(td, "sahte-python")
            os.symlink(sys.executable, sahte)
            # PATH girdisi bilerek GÖRELİ (cwd'ye göre) — which de göreli döner.
            with mock.patch.dict(os.environ, {"PATH": os.path.relpath(td)}):
                yol = ortam._yol_coz("sahte-python")
            self.assertIsNotNone(yol, "aday PATH'te olduğu hâlde bulunamadı")
            self.assertTrue(os.path.isabs(yol),
                            f"kapıya göreli yol verilecekti: {yol}")


class GerekirTest(unittest.TestCase):
    """`ortam.gerekir` düz (TestCase olmayan) sınıfta da GERÇEKTEN atlatmalı.

    Ölçüm 2026-09-02: pytest `__unittest_skip__` bayrağını yalnız TestCase
    alt sınıflarında okur. `tests/test_birim.py` pytest-native olduğu için
    ona konan `unittest.skipUnless` etkisiz kalıyor, test atlandığı sanılırken
    KOŞUYOR. Bu yüzden `gerekir` iki bayrağı birden takar; bekçi, biri
    sadeleştirme adına düşürülürse bunu yakalar.
    """

    def test_kosul_yoksa_iki_bayrak_birden_takilir(self):
        @ortam.gerekir(False, "kurgu sebep")
        class Duz:
            pass

        self.assertTrue(getattr(Duz, "__unittest_skip__", False),
                        "unittest koşucusu için atlama bayrağı yok")
        if ortam.pytest is not None:
            adlar = [m.name for m in getattr(Duz, "pytestmark", [])]
            self.assertIn("skipif", adlar,
                          "pytest koşucusu için skipif markı yok — düz sınıf "
                          "atlandığı sanılıp KOŞAR")

    def test_kosul_varsa_atlanmaz(self):
        @ortam.gerekir(True, "kurgu sebep")
        class Duz:
            pass

        self.assertFalse(getattr(Duz, "__unittest_skip__", False))
        for m in getattr(Duz, "pytestmark", []):
            if m.name == "skipif":
                self.assertFalse(m.args[0], "koşul sağlandığı hâlde atlanıyor")


class SunucuKapisiTest(unittest.TestCase):
    """Sunucu kapısı cv2'ye DEĞİL, src.server'ın import edilebilirliğine bakar.

    Yalnız cv2'ye bakan bir kapı, cv2'si olup fastapi'si olmayan makinede
    modülü yine import'ta çökertirdi — testler süitten sessizce düşerdi.
    """

    def test_sunucu_yiginin_tamami_yoklanir(self):
        self.assertEqual(set(ortam.SUNUCU_MODULLERI),
                         {"cv2", "fastapi", "pydantic"})

    def test_eksik_modul_sebepte_adiyla_gecer(self):
        for m in ortam.SUNUCU_MODULLERI:
            if not ortam._kurulu(m):
                self.assertIn(m, ortam.SUNUCU_SEBEP,
                              "eksik bağımlılık gerekçede adıyla görünmeli")


if __name__ == "__main__":
    unittest.main()
