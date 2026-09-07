"""Dedektör motoru seçimi ve LİSANS KAPISI.

Neden bu testler var: bu ürün kapalı kaynak ticari olarak satılacak. Ultralytics
YOLO AGPL-3.0'dır ve AGPL "SaaS boşluğunu" kapatır — modeli sunucu arkasında
sunmak bile dağıtım sayılır. Yani yanlış motor seçimi bir performans tercihi
değil, HUKUKİ bir olaydır ve sessizce olmamalıdır.

Kapı şu kuralı uygular: varsayılan motor Apache-2.0'dır; AGPL motor ancak
yapılandırmada AÇIKÇA kabul edilirse yüklenir. Böylece lisans kararı
config.yaml'da görünür ve denetlenebilir olur, import zincirinde saklı kalmaz.

Bu süit model ve ağırlık İSTEMEZ — sahte arka uçla koşar.
"""
import unittest

from src.dedektor import (LISANSLAR, VARSAYILAN_MOTOR, LisansHatasi,
                          lisans_kapisi, normalize)


class Varsayilan(unittest.TestCase):
    def test_varsayilan_motor_apache(self):
        """Hiçbir şey seçilmezse ticari olarak temiz motor gelmeli."""
        self.assertEqual(LISANSLAR[VARSAYILAN_MOTOR], "Apache-2.0")

    def test_varsayilan_motor_rfdetr(self):
        self.assertEqual(VARSAYILAN_MOTOR, "rfdetr")


class LisansKapisi(unittest.TestCase):
    def test_apache_motor_onaysiz_gecer(self):
        self.assertEqual(lisans_kapisi("rfdetr", agpl_kabul=False), "Apache-2.0")

    def test_agpl_motor_onaysiz_reddedilir(self):
        """Kazayla AGPL'e düşmek MÜMKÜN OLMAMALI — sessiz geçiş yok."""
        with self.assertRaises(LisansHatasi) as ctx:
            lisans_kapisi("ultralytics", agpl_kabul=False)
        self.assertIn("AGPL", str(ctx.exception))

    def test_agpl_motor_acik_onayla_gecer(self):
        """Bilinçli seçim engellenmez — yalnız görünür kılınır."""
        self.assertEqual(lisans_kapisi("ultralytics", agpl_kabul=True), "AGPL-3.0")

    def test_bilinmeyen_motor_reddedilir(self):
        with self.assertRaises(LisansHatasi):
            lisans_kapisi("bilinmeyen-motor", agpl_kabul=True)

    def test_hata_mesaji_cikis_yolunu_soyler(self):
        """Hata yalnız 'hayır' dememeli; ne yapılacağını söylemeli."""
        try:
            lisans_kapisi("ultralytics", agpl_kabul=False)
        except LisansHatasi as e:
            self.assertIn("fire.engine", str(e))
            self.assertIn("agpl_kabul", str(e))

    def test_pml_katmani_apache_sayilmaz(self):
        """RF-DETR XL/2XL PML 1.0'dır — Apache değildir, karıştırılmamalı."""
        self.assertNotIn("rfdetr-xl", LISANSLAR)
        self.assertNotIn("rfdetr-2xl", LISANSLAR)


class SahteTespitler:
    """supervision.Detections'ın test için gereken yüzeyi."""

    def __init__(self, xyxy, confidence, class_id):
        self.xyxy = xyxy
        self.confidence = confidence
        self.class_id = class_id


class Normalize(unittest.TestCase):
    ADLAR = {0: "smoke", 1: "fire"}

    def test_kutu_guven_sinif_uclusune_cevirir(self):
        d = SahteTespitler([[10, 20, 30, 40]], [0.8], [1])
        self.assertEqual(normalize(d, self.ADLAR),
                         [("fire", 10.0, 20.0, 30.0, 40.0, 0.8)])

    def test_coklu_tespit_sirasi_korunur(self):
        d = SahteTespitler([[0, 0, 5, 5], [1, 1, 9, 9]], [0.5, 0.9], [0, 1])
        cikti = normalize(d, self.ADLAR)
        self.assertEqual([c[0] for c in cikti], ["smoke", "fire"])

    def test_bos_tespit_bos_liste(self):
        self.assertEqual(normalize(SahteTespitler([], [], []), self.ADLAR), [])

    def test_none_bos_liste(self):
        """Arka uç None dönerse çökmemeli (kare atlanmalı)."""
        self.assertEqual(normalize(None, self.ADLAR), [])

    def test_bilinmeyen_sinif_id_ham_kalir(self):
        """Ad haritasında olmayan id sessizce DÜŞMEMELİ — görünür kalsın."""
        d = SahteTespitler([[0, 0, 1, 1]], [0.6], [7])
        self.assertEqual(normalize(d, self.ADLAR)[0][0], "7")

    def test_cikti_dumantakip_ile_uyumlu(self):
        """normalize çıktısı doğrudan DumanTakip.guncelle'ye girebilmeli."""
        from src.fire import DumanTakip

        d = SahteTespitler([[300, 200, 380, 300]], [0.9], [0])
        t = DumanTakip(640, 480, dogrulama_kare=2, alarm_sn=1e9)
        olaylar = []
        for i in range(3):
            olaylar += t.guncelle(normalize(d, self.ADLAR), i * 0.5)
        self.assertEqual([o["durum"] for o in olaylar], ["on_uyari"])
        self.assertEqual(olaylar[0]["sinif"], "duman")   # smoke → duman


if __name__ == "__main__":
    unittest.main()
