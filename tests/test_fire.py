"""Yangın/duman erken uyarı — zamansal doğrulama, maskeleme, kanıt, feragat.

Bu süit MODEL VE GPU İSTEMEZ: `DumanTakip` saf mantıktır, tespitler test
içinde elle üretilir. Sebep proje kuralı değil ölçüm: hattın değerini model
değil zamansal doğrulama belirliyor (BRE/FIA ölçümü, tek kare ~%58 —
.agents/reports/2026-09-02-yangin-ve-tekstil-hata-tespiti.md), o yüzden asıl
test edilmesi gereken kısım modelden bağımsız olmalı.

Kriter → test eşlemesi (EARS):
  K1 tek kare alarm üretmez            → test_tek_kare_ne_on_uyari_ne_alarm_uretir
  K2 N-of-M doğrulama → ön uyarı       → test_dogrulama_esigi_asilinca_on_uyari
  K3 süren doğrulama → alarm           → test_on_uyari_surunce_alarma_yukselir
  K4 cooldown                          → test_alarm_cooldown_icinde_tekrarlamaz
  K5 maskelenen bölge yok sayılır      → test_maskelenen_bolgedeki_tespit_yok_sayilir
  K6 izleme bölgesi dışı sayılmaz      → test_izleme_bolgesi_disindaki_tespit_sayilmaz
  K7 kanıt klibi yazılır               → test_kanit_klibi_yazilir
  K8 model yoksa AÇIK hata             → test_model_dosyasi_yoksa_acik_hata
  K9 feragat etiketi zorunlu           → test_alarm_etiketi_feragat_tasir
  +  pencere dışı vuruş sayılmaz       → test_pencere_disinda_kalan_vuruslar_sayilmaz
"""
import unittest

from src.fire import FERAGAT, DumanTakip, alarm_etiketi, model_yolu

# Kadraj ortasında sabit bir duman kutusu (piksel) — 640x480 kare varsayımı.
KUTU = (300, 200, 380, 300)
W, H = 640, 480


def tespit(kutu=KUTU, sinif="duman", conf=0.7):
    return [(sinif, *kutu, conf)]


def takip(**kw):
    """Testte okunur varsayılanlar: 4 kare / 6 sn pencere, 3 sn'de alarm."""
    varsayilan = dict(pencere_sn=6.0, dogrulama_kare=4, iou_baglama=0.2,
                      alarm_sn=3.0, cooldown_sn=120.0)
    varsayilan.update(kw)
    return DumanTakip(W, H, **varsayilan)


def besle(t, kare_sayisi, adim=0.5, ts0=0.0, kutu=KUTU):
    """kare_sayisi kadar ardışık kareyi besler; üretilen tüm olayları döndürür."""
    olaylar = []
    for i in range(kare_sayisi):
        olaylar += t.guncelle(tespit(kutu), ts0 + i * adim)
    return olaylar


class TekKare(unittest.TestCase):
    def test_tek_kare_ne_on_uyari_ne_alarm_uretir(self):
        """K1: bir karede duman görmek olay değildir — BRE/FIA ölçümünün karşılığı."""
        t = takip()
        self.assertEqual(t.guncelle(tespit(), 0.0), [])

    def test_esigin_bir_altinda_hala_sessiz(self):
        """Doğrulama eşiğinin bir altı hâlâ sessiz olmalı (off-by-one kapanı)."""
        t = takip(dogrulama_kare=4)
        self.assertEqual(besle(t, 3), [])


class Dogrulama(unittest.TestCase):
    def test_dogrulama_esigi_asilinca_on_uyari(self):
        """K2: pencere içinde N kare aynı odağı doğrularsa ÖN UYARI (alarm değil)."""
        t = takip(dogrulama_kare=4)
        olaylar = besle(t, 4)
        self.assertEqual([o["durum"] for o in olaylar], ["on_uyari"])
        self.assertEqual(olaylar[0]["sinif"], "duman")
        self.assertEqual(olaylar[0]["dogrulama"], 4)

    def test_on_uyari_yalnizca_bir_kez_uretilir(self):
        """Aynı odak için ön uyarı her karede tekrar üretilmez (alarm spam'i)."""
        t = takip(dogrulama_kare=4, alarm_sn=1e9)
        olaylar = besle(t, 8)
        self.assertEqual([o["durum"] for o in olaylar], ["on_uyari"])

    def test_pencere_disinda_kalan_vuruslar_sayilmaz(self):
        """Pencereden düşen vuruşlar birikmez: seyrek tespit alarma yükselmemeli."""
        t = takip(pencere_sn=2.0, dogrulama_kare=4)
        # 3 sn aralıkla 6 kare → pencerede hiçbir zaman 2'den fazla vuruş olmaz
        self.assertEqual(besle(t, 6, adim=3.0), [])

    def test_ayri_konumdaki_tespitler_ayri_odak(self):
        """Uzak iki tespit tek odağa toplanmaz; ikisi de tek başına eşiği geçmez."""
        t = takip(dogrulama_kare=4)
        uzak = (10, 10, 90, 110)
        olaylar = []
        for i in range(6):
            kutu = KUTU if i % 2 == 0 else uzak
            olaylar += t.guncelle(tespit(kutu), i * 0.5)
        self.assertEqual(olaylar, [])


class Alarm(unittest.TestCase):
    def test_on_uyari_surunce_alarma_yukselir(self):
        """K3: doğrulama alarm_sn boyunca sürerse durum ALARM'a yükselir."""
        t = takip(dogrulama_kare=4, alarm_sn=3.0)
        olaylar = besle(t, 12, adim=0.5)   # 0.0 → 5.5 sn
        durumlar = [o["durum"] for o in olaylar]
        self.assertEqual(durumlar, ["on_uyari", "alarm"])
        self.assertGreaterEqual(olaylar[1]["sure"], 3.0)

    def test_alarm_cooldown_icinde_tekrarlamaz(self):
        """K4: alarm sürerken cooldown dolmadan ikinci alarm yazılmaz."""
        t = takip(dogrulama_kare=4, alarm_sn=3.0, cooldown_sn=120.0)
        olaylar = besle(t, 60, adim=0.5)   # 30 sn kesintisiz duman
        self.assertEqual([o["durum"] for o in olaylar].count("alarm"), 1)

    def test_cooldown_dolunca_alarm_tekrarlar(self):
        """Cooldown dolduğunda süren yangın yeniden hatırlatılır (sessizleşmez)."""
        t = takip(dogrulama_kare=4, alarm_sn=3.0, cooldown_sn=10.0)
        olaylar = besle(t, 100, adim=0.5)  # 50 sn
        self.assertGreaterEqual([o["durum"] for o in olaylar].count("alarm"), 4)

    def test_alarm_olayi_kanit_icin_kutu_tasir(self):
        """Alarm, kanıt karesinin çerçeveleyeceği kutuyu taşımalı."""
        t = takip(dogrulama_kare=4, alarm_sn=3.0)
        alarm = [o for o in besle(t, 12) if o["durum"] == "alarm"][0]
        self.assertEqual(len(alarm["kutu"]), 4)
        self.assertEqual(tuple(int(v) for v in alarm["kutu"]), KUTU)


class Bolgeler(unittest.TestCase):
    # Kadrajın sol yarısını kaplayan poligon (normalize koordinat).
    SOL = [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]
    # KUTU'nun merkezi (340, 250) → normalize (0.53, 0.52): SOL'un DIŞINDA.

    def test_maskelenen_bolgedeki_tespit_yok_sayilir(self):
        """K5: maske içindeki tespit hiç değerlendirilmez (kaynak makinesi, egzoz)."""
        sag = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
        t = takip(dogrulama_kare=4, maskeler=[{"name": "Kaynak", "points": sag}])
        self.assertEqual(besle(t, 20), [])

    def test_izleme_bolgesi_disindaki_tespit_sayilmaz(self):
        """K6: izleme bölgesi tanımlıysa yalnız onun içi değerlendirilir."""
        t = takip(dogrulama_kare=4, bolgeler=[{"name": "Depo", "points": self.SOL}])
        self.assertEqual(besle(t, 20), [])

    def test_izleme_bolgesi_icindeki_tespit_sayilir(self):
        """Bölge kısıtı çalışan tespiti de susturmamalı (kapsam daralması kapanı)."""
        sag = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
        t = takip(dogrulama_kare=4, bolgeler=[{"name": "Depo", "points": sag}])
        self.assertTrue(besle(t, 4))

    def test_bolge_tanimli_degilse_tum_kadraj_izlenir(self):
        """Bölge yoksa varsayılan davranış daralmamalı."""
        t = takip(dogrulama_kare=4, bolgeler=[], maskeler=[])
        self.assertTrue(besle(t, 4))


class Feragat(unittest.TestCase):
    def test_alarm_etiketi_feragat_tasir(self):
        """K9: her yangın alarmı 'sertifikalı alarm değildir' ibaresini taşır."""
        etiket = alarm_etiketi({"sinif": "duman", "dogrulama": 5, "sure": 4.2})
        self.assertIn(FERAGAT, etiket)

    def test_feragat_bos_degil(self):
        self.assertTrue(FERAGAT.strip())


class ModelKapisi(unittest.TestCase):
    def test_model_dosyasi_yoksa_acik_hata(self):
        """K8: eksik model SESSİZ SIFIR OLAY değil, adıyla söylenen hata olur."""
        with self.assertRaises(FileNotFoundError) as ctx:
            model_yolu("models/olmayan-yangin-modeli.pt")
        self.assertIn("olmayan-yangin-modeli.pt", str(ctx.exception))

    def test_ultralytics_hazir_modeli_indirmeye_birakilmaz(self):
        """`yolo11n.pt` gibi hazır isim yangın modeli DEĞİLDİR; sessizce geçmemeli.

        Ultralytics bilinen adları otomatik indirir; bu, 'model yüklendi ama
        yangın sınıfı yok' durumunu sessiz sıfır olaya çevirirdi.
        """
        with self.assertRaises(FileNotFoundError):
            model_yolu("yolo11n.pt")


class KanitKlibi(unittest.TestCase):
    def test_kanit_klibi_yazilir(self):
        """K7: doğrulayan kareler klip olur — durağan kareden duman ayırt edilemez."""
        try:
            import numpy as np
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest("cv2/numpy yok — klip yazımı doğrulanamaz (ölçülemedi)")
        import tempfile
        from pathlib import Path

        from src.evidence import klip_kaydet

        class SahteCfg:
            def __init__(self, kok):
                self._kok = kok

            def get(self, anahtar, varsayilan=None):
                return {"paths.output_dir": self._kok, "evidence.enabled": True,
                        "evidence.fire": True}.get(anahtar, varsayilan)

        with tempfile.TemporaryDirectory() as td:
            kareler = [np.zeros((120, 160, 3), dtype="uint8") for _ in range(6)]
            yol = klip_kaydet(SahteCfg(td), kareler, "depo", "fire", fps=5.0)
            self.assertTrue(yol, "klip yolu boş döndü")
            self.assertTrue((Path(td) / "evidence" / Path(yol).relative_to("evidence")).exists())


if __name__ == "__main__":
    unittest.main()
