"""Davranış tespiti — poz sezgiseli + zamansal karar (model YOK, sahte anahtar nokta)."""
from __future__ import annotations

import unittest

import numpy as np

from src.davranis import (BILEK_SAG, BURUN, GOZ_SAG, GOZ_SOL, KULAK_SAG, KULAK_SOL,
                          OMUZ_SAG, OMUZ_SOL, DavranisHatti, DavranisTakip, ozellikler)


def kisi(bilek=(999.0, 999.0), bas=40.0, cx=300.0, cy=100.0):
    """Kameraya dönük bir kişi: baş cx,cy'de, kulaklar arası `bas` piksel."""
    kp = np.full((17, 2), 999.0)
    kc = np.zeros(17)
    kp[BURUN] = (cx, cy); kc[BURUN] = 0.9
    kp[GOZ_SOL] = (cx + 0.3 * bas, cy - 0.2 * bas); kc[GOZ_SOL] = 0.9
    kp[GOZ_SAG] = (cx - 0.3 * bas, cy - 0.2 * bas); kc[GOZ_SAG] = 0.9
    kp[KULAK_SOL] = (cx + 0.5 * bas, cy); kc[KULAK_SOL] = 0.9
    kp[KULAK_SAG] = (cx - 0.5 * bas, cy); kc[KULAK_SAG] = 0.9
    kp[OMUZ_SOL] = (cx + 1.6 * bas, cy + 1.6 * bas); kc[OMUZ_SOL] = 0.9
    kp[OMUZ_SAG] = (cx - 1.6 * bas, cy + 1.6 * bas); kc[OMUZ_SAG] = 0.9
    kp[BILEK_SAG] = bilek; kc[BILEK_SAG] = 0.9
    kutu = (cx - 2 * bas, cy - bas, cx + 2 * bas, cy + 8 * bas)
    return kutu, kp, kc


TELEFON = (300 - 20 - 4, 100 + 48)   # sağ kulağın 1,2 baş altında, yüzün yanında (ölçülen poz)
AGIZ = (300 + 4, 100 + 40)           # ağız tahmininin (300,120) ~0,5 baş altında, ortada


class OzellikTest(unittest.TestCase):
    def test_telefon_pozu(self):
        k, kp, kc = kisi(bilek=TELEFON)
        oz = ozellikler(kp, kc, k)
        self.assertTrue(oz["kulak"])
        self.assertAlmostEqual(oz["bas"], 40.0)

    def test_el_agizda_telefon_degil(self):
        k, kp, kc = kisi(bilek=AGIZ)
        oz = ozellikler(kp, kc, k)
        self.assertTrue(oz["agiz"]); self.assertFalse(oz["kulak"])   # burun hizasında: çene/ağız

    def test_el_asagida_hicbiri(self):
        k, kp, kc = kisi(bilek=(300, 400))
        oz = ozellikler(kp, kc, k)
        self.assertFalse(oz["kulak"]); self.assertFalse(oz["agiz"])

    def test_kulak_hizasindaki_el_telefon_degil(self):
        # el tam kulakta (kaşıma): telefon pozu bileğin kulağın ALTINDA olmasını ister
        k, kp, kc = kisi(bilek=(280, 102))
        oz = ozellikler(kp, kc, k)
        self.assertFalse(oz["kulak"])

    def test_profilde_bas_olcegi_burun_omuzdan(self):
        # profil: kulaklar/gözler görünmez, burun→omuz mesafesi ölçeği verir
        k, kp, kc = kisi()
        kc[KULAK_SOL] = kc[KULAK_SAG] = kc[GOZ_SOL] = kc[GOZ_SAG] = 0.0
        oz = ozellikler(kp, kc, k)
        self.assertGreater(oz["bas"], 30.0)


def _takip(**kw):
    vars_ = dict(telefon_sn=4.0, sigara_tekrar=2, sigara_pencere_sn=40.0,
                 cooldown_sn=120.0, kamera_cooldown_sn=0.0)
    vars_.update(kw)
    return DavranisTakip(**vars_)


class TelefonTest(unittest.TestCase):
    def test_ayni_kiside_telefon_ve_sigara_bagimsizdir(self):
        from src.davranis import BILEK_SOL
        t = _takip()
        events = []
        for i in range(100):
            b, kp, kc = kisi(bilek=(345, 195))
            kp[BILEK_SOL] = AGIZ if i % 32 < 4 else (300, 400)
            kc[BILEK_SOL] = .9
            events += t.guncelle([(b, kp, kc)], i/4, [(335, 177, 355, 200)])
        self.assertEqual({e['sinif'] for e in events if e['durum'] == 'alarm'}, {'telefon', 'sigara'})

    def test_onunde_elde_dogrulanan_telefon_alarm_uretir(self):
        t = _takip()
        ol = self._kos(t, 6, bilek=(335, 190), telefon=[(323, 169, 345, 197)])
        self.assertTrue(any(o['sinif'] == 'telefon' and o['durum'] == 'alarm' for o in ol))

    def test_masadaki_telefon_ve_bos_el_alarm_uretmez(self):
        for boxes in (None, [(240, 300, 265, 330)]):
            ol = self._kos(_takip(), 20, bilek=(335, 190), telefon=boxes)
            self.assertFalse(any(o['sinif'] == 'telefon' for o in ol))

    def test_tek_kare_telefon_dogrulamasi_alarm_uretmez(self):
        t = _takip()
        ol = []
        for i in range(40):
            boxes = [(323, 169, 345, 197)] if i == 0 else None
            ol += t.guncelle([kisi(bilek=(335, 190))], i / 4, telefon_kutular=boxes)
        self.assertFalse(any(o['sinif'] == 'telefon' for o in ol))

    def _kos(self, takip, saniye, fps=4, bilek=TELEFON, telefon=None):
        olaylar = []
        for i in range(int(saniye * fps)):
            ts = i / fps
            olaylar += takip.guncelle([kisi(bilek=bilek)], ts, telefon_kutular=telefon)
        return olaylar

    def test_el_kulakta_4sn_on_uyari_sonra_alarm(self):
        t = _takip(telefon_dogrulama="tercih")
        ol = self._kos(t, 18.0)
        durumlar = [(o["sinif"], o["durum"]) for o in ol]
        self.assertIn(("telefon", "on_uyari"), durumlar)
        self.assertIn(("telefon", "alarm"), durumlar)
        # ön uyarı ≈ 4 sn'de, alarm (kutu yok) ≈ +12 sn sonra (3× telefon_sn)
        on = next(o for o in ol if o["durum"] == "on_uyari")
        al = next(o for o in ol if o["durum"] == "alarm")
        self.assertGreaterEqual(on["ts_seconds"], 3.0)
        self.assertGreaterEqual(al["ts_seconds"] - on["ts_seconds"], 11.5)
        # 9 sn'de henüz alarm yok: sigara içerken yüze yaslanan el bu sürede sahte alarm üretiyordu
        self.assertFalse(any(o["durum"] == "alarm" and o["ts_seconds"] < 9.0 for o in ol))
        self.assertEqual(al["dogrulama"], "poz")

    def test_telefon_kutusu_alarmi_hizlandirir(self):
        t = _takip(telefon_dogrulama="tercih")
        ol = self._kos(t, 6.0, telefon=[(270, 90, 295, 120)])
        al = [o for o in ol if o["durum"] == "alarm"]
        self.assertTrue(al)
        self.assertEqual(al[0]["dogrulama"], "telefon kutusu")
        self.assertLess(al[0]["ts_seconds"], 5.0)

    def test_zorunlu_kipte_kutusuz_alarm_yok(self):
        t = _takip(telefon_dogrulama="zorunlu")
        ol = self._kos(t, 20.0)
        self.assertTrue(any(o["durum"] == "on_uyari" for o in ol))
        self.assertFalse(any(o["durum"] == "alarm" for o in ol))

    def test_kisa_dokunus_alarm_uretmez(self):
        t = _takip()
        ol = self._kos(t, 2.0)          # 2 sn kulakta: kaşıma
        self.assertEqual(ol, [])

    def test_el_inince_sifirlanir_cooldown(self):
        t = _takip()
        ol = self._kos(t, 18.0)
        self.assertTrue(any(o["durum"] == "alarm" for o in ol))
        # el iner, tekrar kalkar: cooldown içinde yeni olay yok
        for i in range(8):
            t.guncelle([kisi(bilek=(300, 400))], 18.0 + i / 4)
        ol2 = []
        for i in range(80):
            ol2 += t.guncelle([kisi(bilek=TELEFON)], 20.0 + i / 4)
        self.assertEqual(ol2, [])

    def test_uzak_kisi_degerlendirilmez(self):
        t = _takip(min_bas_px=24.0)
        ol = []
        for i in range(40):
            ol += t.guncelle([kisi(bilek=(300 - 6, 112), bas=10.0)], i / 4)
        self.assertEqual(ol, [])


class SigaraTest(unittest.TestCase):
    def _dokunus_dizisi(self, takip, n, aralik=8.0, temas=1.0, fps=4, kontrol=None):
        """n kez el ağza gider (temas sn), aralik sn'de bir."""
        ol, ts = [], 0.0
        for k in range(n):
            for i in range(int(temas * fps)):
                ol += takip.guncelle([kisi(bilek=AGIZ)], ts, sigara_kontrol=kontrol); ts += 1 / fps
            for i in range(int((aralik - temas) * fps)):
                ol += takip.guncelle([kisi(bilek=(300, 400))], ts, sigara_kontrol=kontrol); ts += 1 / fps
        return ol, ts

    def test_iki_dokunus_on_uyari(self):
        t = _takip(sigara_dogrulama="tercih")
        ol, _ = self._dokunus_dizisi(t, 2)
        self.assertTrue(any(o["sinif"] == "sigara" and o["durum"] == "on_uyari" for o in ol))

    def test_tek_dokunus_yetmez(self):
        t = _takip()
        ol, _ = self._dokunus_dizisi(t, 1)
        self.assertEqual([o for o in ol if o["sinif"] == "sigara"], [])

    def test_dedektor_dogrulayinca_alarm(self):
        t = _takip(sigara_dogrulama="zorunlu")
        ol, _ = self._dokunus_dizisi(t, 3, kontrol=lambda iz: True)
        al = [o for o in ol if o["sinif"] == "sigara" and o["durum"] == "alarm"]
        self.assertTrue(al)
        self.assertEqual(al[0]["dogrulama"], "sigara dedektörü")

    def test_zorunlu_kipte_dedektor_gormezse_alarm_yok(self):
        t = _takip(sigara_dogrulama="zorunlu")
        ol, _ = self._dokunus_dizisi(t, 4, kontrol=lambda iz: False)
        self.assertFalse(any(o["sinif"] == "sigara" and o["durum"] == "alarm" for o in ol))

    def test_uzun_temas_dokunus_degil(self):
        # el ağızda 10 sn duruyor (düşünme pozu): dokunuş sayılmaz
        t = _takip(dokunus_max_sn=6.0)
        ol, _ = self._dokunus_dizisi(t, 3, aralik=14.0, temas=10.0)
        self.assertEqual([o for o in ol if o["sinif"] == "sigara"], [])


class SinifSecimiTest(unittest.TestCase):
    def test_yalniz_sigara_acikken_telefon_uretilmez(self):
        t = _takip(siniflar=("sigara",))
        ol = []
        for i in range(40):
            ol += t.guncelle([kisi(bilek=TELEFON)], i / 4)
        self.assertEqual(ol, [])

    def test_yalniz_telefon_acikken_sigara_uretilmez(self):
        t = _takip(siniflar=("telefon",))
        ol, ts = [], 0.0
        for k in range(3):
            for i in range(4):
                ol += t.guncelle([kisi(bilek=AGIZ)], ts); ts += 0.25
            for i in range(28):
                ol += t.guncelle([kisi(bilek=(300, 400))], ts); ts += 0.25
        self.assertEqual([o for o in ol if o["sinif"] == "sigara"], [])

    def test_ucuncu_nefes_alarm(self):
        # doğrulayıcı yokken 3. dokunuş alarm (tercih kipi)
        t = _takip(sigara_dogrulama="tercih")
        ol, ts = [], 0.0
        for k in range(3):
            for i in range(4):
                ol += t.guncelle([kisi(bilek=AGIZ)], ts); ts += 0.25
            for i in range(28):
                ol += t.guncelle([kisi(bilek=(300, 400))], ts); ts += 0.25
        self.assertTrue(any(o["sinif"] == "sigara" and o["durum"] == "alarm" for o in ol))


class HatTest(unittest.TestCase):
    def test_telefon_kirpma_koordinatlari_ve_bayat_kutu(self):
        from src.config import Config
        from unittest.mock import Mock
        cfg = Config({'evidence': {'enabled': False}})
        detect = Mock(return_value=[(10, 20, 25, 40)])
        hat = DavranisHatti(cfg, 640, 480, 'test', 4, telefon=detect,
                           poz=lambda frame: [kisi(bilek=(335, 190))])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hat.kare(frame, 10, 0)
        self.assertEqual(detect.call_count, 1)
        self.assertEqual(hat._telefon_boxes, [(174, 26, 189, 46)])
        hat.kare(frame, 10.5, 1)
        self.assertEqual(detect.call_count, 1)
        detect.return_value = []
        hat.kare(frame, 11, 2)
        self.assertEqual(hat._telefon_boxes, [])

    def test_hat_sahte_pozla_etiket_uretir(self):
        class Cfg(dict):
            def get(self, k, d=None):
                return dict.get(self, k, d)
        cfg = Cfg({"davranis.telefon_sn": 2.0, "davranis.camera_cooldown_seconds": 0,
                   "evidence.enabled": False})
        kare = np.zeros((480, 640, 3), dtype=np.uint8)
        olaylar = []
        hat = DavranisHatti(cfg, 640, 480, "test", 4.0,
                            poz=lambda bgr: [kisi(bilek=TELEFON)],
                            on_event=olaylar.append, on_alert=olaylar.append)
        son = []
        for i in range(40):
            son = hat.kare(kare, i / 4, i)
        self.assertEqual(len(son), 1)
        self.assertIn(son[0][0], ("telefon", "telefon?"))
        self.assertTrue(any(o["durum"] == "alarm" for o in olaylar))
        self.assertEqual(hat.sonuc.frames, 40)
        self.assertEqual(hat.sonuc.kisiler_max, 1)
        self.assertEqual(olaylar[-1].get("snapshot"), "")   # kanıt kapalı


if __name__ == "__main__":
    unittest.main()
