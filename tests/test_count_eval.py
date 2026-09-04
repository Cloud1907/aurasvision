"""Sayım kova-karşılaştırma mantığı — arşiv, model, TRASSIR bağlantısı İSTEMEZ.

Neden test ediliyor: `docs/olcumler-sayim.md`'ye yazılacak korelasyon sayısı bu
mantığa dayanıyor. Kova indeksleme hatası (kapalı/açık aralık, saniye/dakika
karışıklığı) sessizce yanlış bir korelasyon üretir — ancak elle doğrulanan bir
küçük örnekle yakalanır.
"""
import unittest
from datetime import datetime, timedelta, timezone

from scripts.count_eval import korelasyon, kova_say

BAS = datetime(2026, 9, 3, 13, 0, 0, tzinfo=timezone.utc)


def _t(saniye: float) -> datetime:
    return BAS + timedelta(seconds=saniye)


class KovaSayimi(unittest.TestCase):
    def test_ilk_kovaya_duser(self):
        olaylar = [(_t(0), "in"), (_t(10), "out")]
        self.assertEqual(kova_say(olaylar, BAS, 300, 2), [2, 0])

    def test_ikinci_kovaya_duser(self):
        olaylar = [(_t(305), "in")]
        self.assertEqual(kova_say(olaylar, BAS, 300, 2), [0, 1])

    def test_kova_siniri_kapali_acik(self):
        """Tam 300. saniye ikinci kovaya girer (>=), 299.99 birinciye."""
        olaylar = [(_t(299.99), "in"), (_t(300.0), "in")]
        self.assertEqual(kova_say(olaylar, BAS, 300, 2), [1, 1])

    def test_pencere_disi_olay_sayilmaz(self):
        """Bas'tan ÖNCE veya adet*bucket_sn'den SONRA olan olay atlanır."""
        olaylar = [(_t(-10), "in"), (_t(1000), "in")]
        self.assertEqual(kova_say(olaylar, BAS, 300, 2), [0, 0])

    def test_yon_ayrimi_yapilmaz_toplam_sayilir(self):
        """Bucket karşılaştırması yön-bağımsızdır (debounce farkı yüzünden)."""
        olaylar = [(_t(1), "in"), (_t(2), "out"), (_t(3), "in")]
        self.assertEqual(kova_say(olaylar, BAS, 300, 1), [3])

    def test_bos_liste_sifir_kova(self):
        self.assertEqual(kova_say([], BAS, 300, 3), [0, 0, 0])


class Korelasyon(unittest.TestCase):
    def test_tam_orantili_seriler_bir_verir(self):
        self.assertEqual(korelasyon([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)

    def test_ters_orantili_seriler_eksi_bir_verir(self):
        self.assertEqual(korelasyon([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_sabit_seri_tanimsiz_none_doner(self):
        """Varyans sıfırsa Pearson tanımsızdır — 0.0 gibi yanlış bir sayı DÖNMEMELİ."""
        self.assertIsNone(korelasyon([5, 5, 5], [1, 2, 3]))

    def test_tek_elemanli_seri_tanimsiz(self):
        self.assertIsNone(korelasyon([1], [1]))

    def test_iliskisiz_seriler_ne_bir_ne_eksi_bir(self):
        r = korelasyon([1, 5, 2, 8, 3], [7, 1, 9, 2, 6])
        self.assertLess(abs(r), 0.9)


if __name__ == "__main__":
    unittest.main()
