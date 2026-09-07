"""Eğitim ayarı doğrulaması — model, GPU ve veri seti İSTEMEZ.

Neden test ediliyor: bu script'in koşusu SAATLER sürüyor. Geçersiz bir
çözünürlük ya da eksik bir split, hatayı ancak eğitim başladıktan sonra
verirse o saatler boşa gider. Bu yüzden doğrulama koşudan ÖNCE yapılır ve
burada sınanan da tam olarak o kapıdır.
"""
import tempfile
import unittest
from pathlib import Path

from scripts.fire_train import (COZUNURLUK_BOLEN, SINIF_ADLARI,
                                EgitimAyarHatasi, cozunurluk_dogrula,
                                efektif_batch, en_iyi_agirlik,
                                veri_seti_dogrula)


class Cozunurluk(unittest.TestCase):
    def test_gecerli_cozunurluk_gecer(self):
        self.assertEqual(cozunurluk_dogrula(512), 512)
        self.assertEqual(cozunurluk_dogrula(640), 640)

    def test_bolunmeyen_cozunurluk_reddedilir(self):
        """RF-DETR-Small patch 16 × 2 pencere = 32'ye bölünmeli."""
        with self.assertRaises(EgitimAyarHatasi):
            cozunurluk_dogrula(500)

    def test_sifir_ve_negatif_reddedilir(self):
        for d in (0, -32):
            with self.assertRaises(EgitimAyarHatasi):
                cozunurluk_dogrula(d)

    def test_bolen_sabiti_beklenen(self):
        self.assertEqual(COZUNURLUK_BOLEN, 32)


class VeriSeti(unittest.TestCase):
    def test_eksik_split_reddedilir(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(EgitimAyarHatasi) as c:
                veri_seti_dogrula(Path(d))
            self.assertIn("train", str(c.exception))

    def test_valid_yoksa_reddedilir(self):
        """Doğrulama split'i olmadan early stopping ve en iyi seçimi anlamsız."""
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            (kok / "train").mkdir()
            (kok / "train" / "_annotations.coco.json").write_text("{}")
            with self.assertRaises(EgitimAyarHatasi) as c:
                veri_seti_dogrula(kok)
            self.assertIn("valid", str(c.exception))

    def test_tam_veri_seti_gecer(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            for ad in ("train", "valid"):
                (kok / ad).mkdir()
                (kok / ad / "_annotations.coco.json").write_text("{}")
            self.assertEqual(veri_seti_dogrula(kok), kok)


class EfektifBatch(unittest.TestCase):
    def test_carpim(self):
        self.assertEqual(efektif_batch(2, 8), 16)

    def test_sifir_reddedilir(self):
        with self.assertRaises(EgitimAyarHatasi):
            efektif_batch(0, 8)


class EnIyiAgirlik(unittest.TestCase):
    def test_ema_checkpoint_tercih_edilir(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            (kok / "checkpoint_best_ema.pth").write_bytes(b"x")
            self.assertEqual(en_iyi_agirlik(kok).name, "checkpoint_best_ema.pth")

    def test_agirlik_yoksa_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(en_iyi_agirlik(Path(d)))

    def test_bilinen_ad_yoksa_pth_dosyasina_duser(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            (kok / "epoch_9.pth").write_bytes(b"x")
            self.assertIsNotNone(en_iyi_agirlik(kok))


class SinifSirasi(unittest.TestCase):
    def test_dfire_sirasi_korunur(self):
        """0=smoke, 1=fire — config.yaml fire.classes ile aynı olmak zorunda."""
        self.assertEqual(SINIF_ADLARI, ["smoke", "fire"])


if __name__ == "__main__":
    unittest.main()
