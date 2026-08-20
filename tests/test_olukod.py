#!/usr/bin/env python3
"""Ölü import bekçisi — ratchet'in görmediği borç sınıfı.

Ölçüm 2026-08-16: repoda 12 kullanılmayan import vardı ve `kalite.py` bunu
HİÇ saymıyordu (boyut, karmaşıklık, borç işareti ve debug artığı sayıyordu,
ölü kodu değil). Biri bu oturumda BENİM bıraktığım artıktı — regex'leri
`yuzey.py`'ye taşırken `kapi.py`'deki `import re` kaldı. Bekçisiz kalan
boşluğa, boşluğu açan kişi düştü.

Neden ruff DEĞİL (ölçüldü, aynı gün): ruff bu repoda 316 bulgu üretiyor ve
ilk dört kural (200 bulgu) ya kozmetik ya da mimariyle ÇATIŞIYOR —
`PLW1510 subprocess-without-check` en tepede, oysa bu repo çıkış kodunu
bilerek okur (`run_event` oracle'ı tam olarak buna dayanır). 300 gürültüyü
yönetmek için yeni bir CI bağımlılığı eklemek, kapatılan boşluktan pahalıydı.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "olukod", os.path.join(ROOT, "bin", "olukod.py"))
olukod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(olukod)


class OluImportTest(unittest.TestCase):
    def bul(self, kod):
        return [ad for _satir, ad in olukod.olu_importlar(kod)]

    def test_kullanilmayan_import_yakalanir(self):
        self.assertEqual(self.bul("import os\nimport sys\nprint(os.getcwd())\n"),
                         ["sys"])

    def test_kullanilan_import_yakalanmaz(self):
        self.assertEqual(self.bul("import os\nprint(os.getcwd())\n"), [])

    def test_takma_ad_izlenir(self):
        self.assertEqual(self.bul("import datetime as dt\nx = dt.date.today()\n"), [])
        self.assertEqual(self.bul("import datetime as dt\nx = 1\n"), ["dt"])

    def test_from_import_izlenir(self):
        self.assertEqual(self.bul("from os import getcwd\nprint(getcwd())\n"), [])
        self.assertEqual(self.bul("from os import getcwd\nx = 1\n"), ["getcwd"])

    def test_noqa_tasiyan_satir_atlanir(self):
        """Yeniden dışa verme meşrudur — `kernel_dosyalari.py` bunu yapar."""
        self.assertEqual(
            self.bul("from manifest import kurulu_surum  # noqa: F401\n"), [])

    def test_yildizli_import_atlanir(self):
        """`from x import *` adları çözülemez; uydurma bulgu üretilmez."""
        self.assertEqual(self.bul("from os import *\nx = 1\n"), [])

    def test_bozuk_sozdizimi_cokmez(self):
        """Ölçüm aracı, ölçtüğü şey bozukken patlamamalı."""
        self.assertEqual(olukod.olu_importlar("def ("), [])

    def test_sadece_nitelikle_kullanim_sayilir(self):
        """`ad.` biçimindeki kullanım da kullanımdır."""
        self.assertEqual(self.bul("import os.path\nprint(os.path.join('a'))\n"), [])

    def test_repo_temiz(self):
        """Bu repo ölü import taşımamalı — bekçinin canlı ölçümü."""
        bulgular = []
        for kok, altlar, dosyalar in os.walk(ROOT):
            altlar[:] = [d for d in altlar if d not in
                         (".git", "__pycache__", ".codegraph", "node_modules",
                          ".venv", "worktrees")]
            for f in dosyalar:
                if not f.endswith(".py"):
                    continue
                yol = os.path.join(kok, f)
                with open(yol, encoding="utf-8") as fh:
                    for satir, ad in olukod.olu_importlar(fh.read()):
                        bulgular.append(f"{os.path.relpath(yol, ROOT)}:{satir} {ad}")
        self.assertEqual(bulgular, [], f"ölü import: {bulgular}")


if __name__ == "__main__":
    unittest.main()
