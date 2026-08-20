#!/usr/bin/env python3
"""Araç tespiti testleri — çekirdek hiçbir araca bağımlı değil."""
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "araclar", os.path.join(ROOT, "bin", "araclar.py"))
araclar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(araclar)


class AraclarTest(unittest.TestCase):
    def test_playwright_tespit_edilir(self):
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "playwright.config.ts"), "w").close()
            o = araclar.ozet(td)
            self.assertTrue(o["e2e_var"])
            self.assertIsNone(o["oneri"])

    def test_e2e_yoksa_yigina_uygun_oneri_verilir(self):
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "package.json"), "w").close()
            o = araclar.ozet(td)
            self.assertFalse(o["e2e_var"])
            self.assertIn("playwright", o["oneri"].lower())

    def test_python_yiginina_python_onerisi(self):
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "requirements.txt"), "w").close()
            o = araclar.ozet(td)
            self.assertIn("pip install", o["oneri"])

    def test_bos_projede_arac_yok_ama_cokmez(self):
        with tempfile.TemporaryDirectory() as td:
            o = araclar.ozet(td)
            self.assertEqual(o["araclar"], [])
            self.assertFalse(o["birim_var"])
            self.assertIsNotNone(o["oneri"])

    def test_bu_repo_birim_testi_tespit_eder(self):
        o = araclar.ozet(ROOT)
        self.assertTrue(o["birim_var"], "AurasAgents kendi testlerini görmeli")


if __name__ == "__main__":
    unittest.main()
