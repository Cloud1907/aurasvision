#!/usr/bin/env python3
# kanonik-özel: buradaki iddia yalnız AurasAgents şablon reposunda doğrudur.
# "tests/ altındaki debug artıkları TARAYICININ KENDİ fixture'larıdır" —
# bağlı projede tests/ gerçek proje testleri taşır (4Flow: tests/smoke_test.js,
# 13 meşru console.log). Bu yüzden test orada ATLANIR, kırmızı vermez.
"""Tarayıcı kendi fixture'ını gerçek borç sanmamalı — kanonik depo iddiası.

Geçmiş: kalite.py'nin DEBUG deseni parçalı kuruluyor, çünkü düz yazılırsa
dosyanın KENDİSİ bulgu üretiyordu. Aynı sınıf hata test fixture'larında da
oldu. Bu test o dönüşü engeller.

Kapsam dersi (2026-08-07, 4Flow kurulumu): ölçüt önce `"test_" in dosya`
idi → adı test_* olan her dosyayı fixture saydı. `tests/` ile daraltıldı →
bağlı projenin gerçek testlerini fixture saydı. İki kez daraltmak yetmedi;
çünkü sorun kapsam değil, iddianın KENDİSİNİN kanonik-özel olmasıydı.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARAC = os.path.join(ROOT, "bin", "kalite.py")
KANONIK = os.path.join(ROOT, "bin", "auras-init.sh")

spec = importlib.util.spec_from_file_location("_kalite_k", ARAC)
kalite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kalite)


@unittest.skipUnless(os.path.isfile(KANONIK),
                     "bağlı proje — tests/ gerçek proje testleri taşır")
class FixtureTest(unittest.TestCase):
    def test_kendi_fixturei_gercek_borc_sayilmaz(self):
        r = kalite.olc(ROOT)
        sahte = [b for b in r["bulgular"]
                 if b["tur"] == "debug_artigi"
                 and b["dosya"].replace(os.sep, "/").startswith("tests/")]
        self.assertEqual(sahte, [], "kendi test fixture'ı gerçek borç sayılıyor")


if __name__ == "__main__":
    unittest.main()
