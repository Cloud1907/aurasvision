#!/usr/bin/env python3
"""Dil kapsamı tek kaynaktan gelir — kapılar ayrışamaz.

H. Demir denetimi (2026-08-15): "bu dosya kaynak kod mu?" sorusu üç ayrı
yerde ayrı listeyle cevaplanıyordu ve listeler çoktan ayrışmıştı. `.sql` ve
`.sh` tur kapısında kaynaktı, kalite ölçümünde yoktu; `.rs`, `.vue`,
`.svelte` kalite ölçümünde vardı, tur kapısında yoktu. Aynı değişiklik bir
kapıda yükümlülük doğuruyor, diğerinde görünmüyordu.

Bu bekçi ayrışmayı yapısal olarak imkânsız kılar: kapılar `bin/diller.py`
dışında kendi listesini TUTAMAZ.
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, yol=None):
    spec = importlib.util.spec_from_file_location(
        name, yol or os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


diller = _load("diller")
kapi = _load("kapi")
kalite = _load("kalite")


class DillerTest(unittest.TestCase):
    def test_kapi_tek_kaynaktan_okur(self):
        self.assertEqual(set(kapi.KAYNAK_UZANTI), set(diller.KAYNAK))

    def test_kalite_tek_kaynaktan_okur(self):
        self.assertEqual(set(kalite.KOD_UZANTI), set(diller.KALITE))

    def test_gorunur_yuzey_tek_kaynaktan_okur(self):
        self.assertEqual(set(kapi.UI_UZANTI), set(diller.GORUNUR))

    def test_suslu_kume_kalite_kumesinin_alt_kumesi(self):
        """Süslü parantezli dil, önce kalite kapsamında olmalı."""
        self.assertTrue(diller.SUSLU <= diller.KALITE)

    def test_gorunur_yuzey_kaynagin_alt_kumesi_degil(self):
        """`.css`/`.html` kaynak değildir ama görünürdür — ayrım korunmalı."""
        self.assertIn(".css", diller.GORUNUR)
        self.assertNotIn(".css", diller.KAYNAK)

    def test_kabuk_ve_sql_kalite_disinda(self):
        """Kabuk/SQL'de 'fonksiyon karmaşıklığı' anlamlı değil — dürüst kapsam."""
        for u in (".sh", ".sql"):
            self.assertIn(u, diller.KAYNAK)
            self.assertNotIn(u, diller.KALITE)

    def test_hicbir_kapi_kendi_listesini_tutmaz(self):
        """Kapı dosyalarında elle yazılmış uzantı kümesi kalmamalı.

        Kaba ama yönü doğru sinyal: bir dosyada üç ya da daha fazla uzantı
        dizesi yan yana yazılıysa orada ikinci bir liste doğuyor demektir.
        """
        desen = re.compile(r'(?:"\.[a-z]{1,6}",\s*){3,}')
        for rel in ("bin/kapi.py", "bin/kalite.py",
                    ".agents/skills/implement-change/scripts/check_test_first.py"):
            yol = os.path.join(ROOT, rel)
            if not os.path.isfile(yol):
                continue
            with open(yol, encoding="utf-8") as fh:
                govde = fh.read()
            # `diller.py` importu varsa liste oradan gelir; yoksa elle liste
            # kalmış demektir.
            if desen.search(govde):
                self.assertIn("diller", govde,
                              f"{rel}: elle uzantı listesi var, diller.py'den oku")


if __name__ == "__main__":
    unittest.main()
