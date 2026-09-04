"""Yangın değerlendirme mantığı — model ve veri seti İSTEMEZ.

Neden test ediliyor: bu script'in ürettiği sayı doğrudan `fire.conf` değerine,
yani sahada alarmın çalıp çalmamasına dönüşüyor. Hata sessizdir — yanlış eşik
de geçerli bir sayı gibi görünür. Özellikle iki karar sınanıyor:

  · Eşleştirme SINIF-BAĞIMSIZ olmalı: alarm açısından "duman yerine alev dedi"
    kaçırma değildir; sınıf-duyarlı eşleştirme recall'ı yapay olarak düşürür.
  · Öneri, recall'ı hedefin ÜSTÜNDE tutan EN YÜKSEK eşiği seçmeli. En yüksek
    recall'ı seçmek yanlıştır — fazla recall ürüne katkı vermez, yanlış alarm
    getirir.
"""
import unittest

from scripts.fire_eval import (dilim_recall, iou, kare_sonucu, oneri, tarama,
                               _dilim_adi)


def _d(conf, kutu=(10, 10, 20, 20), sinif="smoke"):
    return {"sinif": sinif, "kutu": list(kutu), "conf": conf}


def _g(kutu=(10, 10, 20, 20), alan=400.0):
    return {"bbox": list(kutu), "area": alan}


class Iou(unittest.TestCase):
    def test_ayni_kutu_bir(self):
        self.assertAlmostEqual(iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)

    def test_ayrik_kutu_sifir(self):
        self.assertEqual(iou([0, 0, 10, 10], [50, 50, 10, 10]), 0.0)

    def test_yarim_ortusme(self):
        self.assertAlmostEqual(iou([0, 0, 10, 10], [5, 0, 10, 10]), 1 / 3, places=4)

    def test_sifir_alan_bolme_hatasi_vermez(self):
        self.assertEqual(iou([0, 0, 0, 0], [0, 0, 0, 0]), 0.0)


class KareSonucu(unittest.TestCase):
    def test_esigin_altindaki_tespit_sayilmaz(self):
        yakalandi, yanlis = kare_sonucu([_d(0.2)], [_g()], 0.5)
        self.assertFalse(yakalandi)
        self.assertFalse(yanlis)

    def test_ortusen_tespit_kareyi_yakalar(self):
        yakalandi, yanlis = kare_sonucu([_d(0.9)], [_g()], 0.5)
        self.assertTrue(yakalandi)
        self.assertFalse(yanlis)

    def test_sinif_bagimsiz_eslesme(self):
        """Duman yerine alev demek alarm açısından KAÇIRMA değildir."""
        yakalandi, _ = kare_sonucu([_d(0.9, sinif="fire")], [_g()], 0.5)
        self.assertTrue(yakalandi)

    def test_negatif_karede_tespit_nuisance(self):
        yakalandi, yanlis = kare_sonucu([_d(0.9)], [], 0.5)
        self.assertFalse(yakalandi)
        self.assertTrue(yanlis)

    def test_negatif_karede_tespit_yoksa_temiz(self):
        self.assertEqual(kare_sonucu([], [], 0.5), (False, False))

    def test_kayik_tespit_yanlis_pozitif(self):
        yakalandi, yanlis = kare_sonucu([_d(0.9, kutu=(300, 300, 20, 20))],
                                        [_g()], 0.5)
        self.assertFalse(yakalandi)
        self.assertTrue(yanlis)


class Tarama(unittest.TestCase):
    def setUp(self):
        # 1,2 pozitif kare · 3,4 negatif kare
        self.gercek = {1: [_g()], 2: [_g()], 3: [], 4: []}
        self.tespit = {1: [_d(0.9)], 2: [_d(0.3)], 3: [_d(0.4)], 4: []}

    def test_esik_yukseldikce_recall_dusmez_artmaz(self):
        s = tarama(self.tespit, self.gercek, [0.2, 0.5, 0.95])
        recalls = [x["kare_recall"] for x in s]
        self.assertEqual(recalls, sorted(recalls, reverse=True))

    def test_dusuk_esikte_iki_pozitif_de_yakalanir(self):
        s = tarama(self.tespit, self.gercek, [0.2])[0]
        self.assertEqual(s["kare_recall"], 1.0)

    def test_negatif_alarm_orani_olculur(self):
        """3 numaralı negatif kare 0.4 güvenle tespit üretiyor → 1/2 = 0.5."""
        s = tarama(self.tespit, self.gercek, [0.35])[0]
        self.assertEqual(s["negatif_alarm_orani"], 0.5)
        self.assertEqual(s["negatif_alarmli_kare"], 1)

    def test_yuksek_esikte_negatif_alarm_sifirlanir(self):
        s = tarama(self.tespit, self.gercek, [0.95])[0]
        self.assertEqual(s["negatif_alarm_orani"], 0.0)


class DilimRecall(unittest.TestCase):
    def test_dilim_siniri(self):
        self.assertEqual(_dilim_adi(100), "kucuk")
        self.assertEqual(_dilim_adi(32 * 32), "orta")
        self.assertEqual(_dilim_adi(96 * 96), "buyuk")

    def test_kucuk_nesne_ayri_raporlanir(self):
        gercek = {1: [_g(kutu=(0, 0, 10, 10), alan=100.0)],
                  2: [_g(kutu=(0, 0, 200, 200), alan=40000.0)]}
        tespit = {1: [], 2: [_d(0.9, kutu=(0, 0, 200, 200))]}
        d = dilim_recall(tespit, gercek, 0.5)
        self.assertEqual(d["kucuk"]["recall"], 0.0)
        self.assertEqual(d["buyuk"]["recall"], 1.0)


class Oneri(unittest.TestCase):
    def test_en_yuksek_uygun_esik_secilir(self):
        """En yüksek RECALL değil, hedefi tutturan en yüksek EŞİK seçilir."""
        satirlar = [{"esik": 0.1, "kare_recall": 0.90, "negatif_alarm_orani": 0.4},
                    {"esik": 0.5, "kare_recall": 0.40, "negatif_alarm_orani": 0.1},
                    {"esik": 0.8, "kare_recall": 0.05, "negatif_alarm_orani": 0.0}]
        s = oneri(satirlar, 0.15, 0.05)
        self.assertEqual(s["esik"], 0.5)

    def test_marj_hesaba_katilir(self):
        """Taban 0.15 + marj 0.10 = 0.25; 0.20'lik satır seçilmemeli."""
        satirlar = [{"esik": 0.3, "kare_recall": 0.30, "negatif_alarm_orani": 0.1},
                    {"esik": 0.6, "kare_recall": 0.20, "negatif_alarm_orani": 0.0}]
        s = oneri(satirlar, 0.15, 0.10)
        self.assertEqual(s["esik"], 0.3)

    def test_hicbir_esik_yetmezse_none(self):
        """Sayı uydurmak yerine açıkça 'yok' demeli."""
        satirlar = [{"esik": 0.1, "kare_recall": 0.02, "negatif_alarm_orani": 0.9}]
        s = oneri(satirlar, 0.15, 0.05)
        self.assertIsNone(s["esik"])
        self.assertIn("hiçbir eşikte", s["gerekce"])


if __name__ == "__main__":
    unittest.main()
