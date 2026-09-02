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


if __name__ == "__main__":
    unittest.main()
