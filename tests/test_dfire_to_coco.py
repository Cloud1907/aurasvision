"""D-Fire (YOLO) → COCO dönüşümü.

Neden ayrı süit: bu dönüşümün iki hatası da SESSİZDİR — eğitim çalışır, kayıp
düşer, model üretilir ve hata ancak sahada yanlış alarm olarak görülür.

  1. Negatif kare kaybı. Etiketsiz görüntüyü atlayan bir dönüştürücü D-Fire'ın
     yanlış-alarm bastıran parçasını siler. Hiçbir istisna fırlamaz.
  2. Koordinat tabanı karışması. YOLO merkez-tabanlı normalize, COCO sol-üst
     tabanlı pikseldir; karıştırıldığında kutular kayar ama biçim geçerli kalır.

Süit görüntü dosyası ister (boyut dosyadan okunur, varsayılmaz) — Pillow ile
bellekte üretilir, diskte sabit yoktur.
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.dfire_to_coco import (SINIFLAR, DonusumHatasi, bol, ciftle,
                                   coco_uret, etiket_oku,
                                   etiket_satiri_ayristir, yolo_kutu_coco)


def _goruntu_yaz(yol: Path, genislik: int = 640, yukseklik: int = 480) -> None:
    from PIL import Image

    yol.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (genislik, yukseklik), (10, 10, 10)).save(yol)


class KutuDonusumu(unittest.TestCase):
    def test_merkez_kutu_sol_uste_cevrilir(self):
        """Tam ortada, karenin yarısı kadar kutu → (%25, %25) köşe, yarım boyut."""
        self.assertEqual(yolo_kutu_coco([0.5, 0.5, 0.5, 0.5], 640, 480),
                         [160.0, 120.0, 320.0, 240.0])

    def test_sol_ust_kosedeki_kutu(self):
        self.assertEqual(yolo_kutu_coco([0.1, 0.1, 0.2, 0.2], 100, 100),
                         [0.0, 0.0, 20.0, 20.0])

    def test_kare_disina_tasan_kutu_kirpilir(self):
        """Sınırdaki kutu negatif koordinat üretmemeli — COCO doğrulayıcı patlar."""
        kutu = yolo_kutu_coco([0.95, 0.95, 0.2, 0.2], 100, 100)
        self.assertGreaterEqual(kutu[0], 0.0)
        self.assertGreaterEqual(kutu[1], 0.0)
        self.assertLessEqual(kutu[0] + kutu[2], 100.0)
        self.assertLessEqual(kutu[1] + kutu[3], 100.0)


class EtiketAyristirma(unittest.TestCase):
    def test_gecerli_satir(self):
        self.assertEqual(etiket_satiri_ayristir("1 0.5 0.5 0.2 0.2"),
                         (1, [0.5, 0.5, 0.2, 0.2]))

    def test_bos_satir_atlanir(self):
        self.assertIsNone(etiket_satiri_ayristir("   "))

    def test_eksik_alan_hata(self):
        with self.assertRaises(DonusumHatasi):
            etiket_satiri_ayristir("1 0.5 0.5 0.2")

    def test_bilinmeyen_sinif_hata(self):
        """D-Fire iki sınıflıdır; üçüncü bir id sessizce geçmemeli."""
        with self.assertRaises(DonusumHatasi):
            etiket_satiri_ayristir("2 0.5 0.5 0.2 0.2")

    def test_merkez_kare_disinda_hata(self):
        with self.assertRaises(DonusumHatasi):
            etiket_satiri_ayristir("0 1.5 0.5 0.2 0.2")

    def test_kenar_biri_asabilir(self):
        """Kadrajı dolduran nesnenin kutusu taşar; D-Fire'da 26.557 kutunun
        8'i böyle (en büyük 1.0563). Geçerlidir, kırpma ile ele alınır."""
        sinif, pay = etiket_satiri_ayristir("0 0.505 0.362 1.0297 0.708")
        self.assertEqual(sinif, 0)
        self.assertAlmostEqual(pay[2], 1.0297)

    def test_asiri_kenar_bozuk_sayilir(self):
        """2.0 üstü taşma değil bozuk etikettir — sessizce kırpılmamalı."""
        with self.assertRaises(DonusumHatasi):
            etiket_satiri_ayristir("0 0.5 0.5 3.0 0.2")

    def test_sifir_kenar_ayristirmada_gecer(self):
        """Sıfır kenar BİÇİM hatası değil bozuk ETİKETtir (D-Fire'da 18 tane);
        ayrıştırma kabul eder, coco_uret sayarak eler."""
        sinif, pay = etiket_satiri_ayristir("0 0.5 0.5 0.0 0.0")
        self.assertEqual(pay[2], 0.0)

    def test_negatif_kenar_hata(self):
        with self.assertRaises(DonusumHatasi):
            etiket_satiri_ayristir("0 0.5 0.5 -0.1 0.2")


class NegatifKareler(unittest.TestCase):
    """En kritik davranış: yangın/duman İÇERMEYEN kare veri setinde KALMALI."""

    def test_bos_etiket_dosyasi_negatif_sayilir(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bos.txt"
            p.write_text("", encoding="utf-8")
            self.assertEqual(etiket_oku(p), [])

    def test_olmayan_etiket_dosyasi_negatif_sayilir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(etiket_oku(Path(d) / "yok.txt"), [])

    def test_negatif_goruntu_coco_images_icinde_kalir(self):
        """Naif dönüştürücü bunu siler; sildiğinde bu test kırmızıya döner."""
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            _goruntu_yaz(kok / "images" / "neg.jpg")
            _goruntu_yaz(kok / "images" / "poz.jpg")
            (kok / "labels").mkdir(parents=True, exist_ok=True)
            (kok / "labels" / "neg.txt").write_text("", encoding="utf-8")
            (kok / "labels" / "poz.txt").write_text("1 0.5 0.5 0.2 0.2\n",
                                                    encoding="utf-8")
            coco, ozet = coco_uret(ciftle(kok / "images", kok / "labels"))
            self.assertEqual(ozet["goruntu"], 2)
            self.assertEqual(ozet["negatif"], 1)
            self.assertEqual(len(coco["annotations"]), 1)
            adlar = {i["file_name"] for i in coco["images"]}
            self.assertIn("neg.jpg", adlar)


class DusenKutu(unittest.TestCase):
    """Sıfır alanlı kutu atılır ama SAYILIR — sessiz kayıp olmamalı."""

    def test_sifir_alanli_kutu_sayilarak_elenir(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            _goruntu_yaz(kok / "images" / "a.jpg", 100, 100)
            (kok / "labels").mkdir(parents=True, exist_ok=True)
            (kok / "labels" / "a.txt").write_text(
                "0 0.5 0.5 0.0 0.0\n1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            coco, ozet = coco_uret(ciftle(kok / "images", kok / "labels"))
            self.assertEqual(ozet["kutu"], 1)
            self.assertEqual(ozet["dusen_kutu"], 1)
            self.assertEqual(len(coco["annotations"]), 1)


class CocoYapisi(unittest.TestCase):
    def test_kategori_kimlikleri_birden_baslar(self):
        """Roboflow/RF-DETR düzeni: smoke=1, fire=2 (YOLO'da 0 ve 1)."""
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            _goruntu_yaz(kok / "images" / "a.jpg", 100, 100)
            (kok / "labels").mkdir(parents=True, exist_ok=True)
            (kok / "labels" / "a.txt").write_text(
                "0 0.5 0.5 0.2 0.2\n1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            coco, ozet = coco_uret(ciftle(kok / "images", kok / "labels"))
            kats = {c["id"]: c["name"] for c in coco["categories"]}
            self.assertEqual(kats, {1: SINIFLAR[0], 2: SINIFLAR[1]})
            self.assertEqual({a["category_id"] for a in coco["annotations"]},
                             {1, 2})
            self.assertEqual(ozet["smoke"], 1)
            self.assertEqual(ozet["fire"], 1)

    def test_alan_kutudan_hesaplanir(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            _goruntu_yaz(kok / "images" / "a.jpg", 100, 100)
            (kok / "labels").mkdir(parents=True, exist_ok=True)
            (kok / "labels" / "a.txt").write_text("0 0.5 0.5 0.4 0.4\n",
                                                  encoding="utf-8")
            coco, _ = coco_uret(ciftle(kok / "images", kok / "labels"))
            a = coco["annotations"][0]
            self.assertAlmostEqual(a["area"], a["bbox"][2] * a["bbox"][3], places=1)
            self.assertTrue(json.dumps(coco))   # serileşebilir olmalı


class Bolme(unittest.TestCase):
    def test_bolme_deterministik(self):
        """Aynı girdi aynı bölünmeyi vermeli; yoksa iki koşu kıyaslanamaz."""
        ciftler = [(Path(f"{i}.jpg"), Path(f"{i}.txt")) for i in range(100)]
        a1, v1 = bol(ciftler, 0.1)
        a2, v2 = bol(ciftler, 0.1)
        self.assertEqual(a1, a2)
        self.assertEqual(v1, v2)

    def test_bolme_kayipsiz(self):
        ciftler = [(Path(f"{i}.jpg"), Path(f"{i}.txt")) for i in range(100)]
        train, valid = bol(ciftler, 0.1)
        self.assertEqual(len(train) + len(valid), 100)
        self.assertFalse(set(train) & set(valid))

    def test_oran_sifir_ayirmaz(self):
        ciftler = [(Path("a.jpg"), Path("a.txt"))]
        train, valid = bol(ciftler, 0.0)
        self.assertEqual(len(train), 1)
        self.assertEqual(valid, [])


if __name__ == "__main__":
    unittest.main()
