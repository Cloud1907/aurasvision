#!/usr/bin/env python3
# kanonik-özel: bu dosyadaki testler yalnız AurasAgents şablon reposunda
# anlamlıdır. `bin/auras-init.sh` bağlı projelere TAŞINMAZ (taşınmamalı da —
# proje kendini kurmaz). Bu yüzden bağlı projede testler atlanır, kırmızı
# vermez; ve kernel_dosyalari.eksik_test_bagimliliklari() bu dosyayı denetim
# dışı bırakır.
"""Kurucu sözleşmesi — kurulum projeyi çalışır ve YEŞİL bırakmalı.

2026-08-07 / 4Flow: taze kurulum 4 failure + 2 error verdi. Kutudan kırmızı
çıkan kurulum, insana kapıyı baştan yok saymayı öğretir — bir kapı için en
pahalı sonuç budur. Bu testler o sözleşmeyi kilitler.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(ROOT, "bin", "auras-init.sh")


@unittest.skipUnless(os.path.isfile(BETIK),
                     "auras-init.sh yok — bağlı proje, denetlenecek şey yok")
class KurucuTest(unittest.TestCase):
    def metin(self):
        with open(BETIK, encoding="utf-8") as fh:
            return fh.read()

    def test_kalite_tabani_uretilir(self):
        # Üretilmezse ratchet testleri her yeni projede kırmızı başlar.
        self.assertIn("kalite.py --baseline", self.metin())

    def test_var_olan_taban_ezilmez(self):
        # Taban yükseltmek bilinçli karardır (ADR-0004) — kurucu karar veremez.
        self.assertIn("! -f .agents/kalite-baseline.json", self.metin())

    def test_yorumlayici_yetenegi_ciktiyla_kanitlanir(self):
        # Yalnız çıkış koduna bakmak yetmez: `/usr/bin/true -c ...` 0 döner.
        self.assertIn("AURAS_PY_OK", self.metin())

    def test_proje_dosyalari_ezilmez(self):
        # AGENTS.md / CLAUDE.md projenindir; kurucu bir kez yazar, ezmez.
        self.assertIn("copy_new", self.metin())

    def test_kaynak_tazeligi_kopyalamadan_once_olculur(self):
        # Kurucu ÇALIŞMA AĞACINDAN kopyalar; ağaç origin'in gerisindeyse
        # kurulan motor eskidir ama manifest "güncel" der (2026-08-15).
        metin = self.metin()
        self.assertIn("kaynak_tazele", metin,
                      "kurucu kaynak sürümünü hiç ölçmüyor")
        self.assertLess(metin.index("kaynak_tazele"), metin.index("PYSYNC"),
                        "tazelik ölçümü motor kopyalamasından SONRA — geç")

    def test_engel_kurulumu_durdurur(self):
        # Ölçüp devam etmek kapı değildir; engel çıkışla sonuçlanmalı.
        self.assertIn("AURAS_ESKI_MOTOR", self.metin(),
                      "bilinçli atlama kapısı yok — ya sessiz geçiyor ya da "
                      "hiç atlanamıyor; ikisi de yanlış")


if __name__ == "__main__":
    unittest.main()
