"""Model metriği → ÜRÜN metriği köprüsü.

Neden ayrı test dosyası: `mAP` bu üründe başarı ölçütü DEĞİLDİR. Hattımız
pencere içinde N kare onay arıyor (src/fire.py DumanTakip), yani süren bir
yangını yakalamak için kare-başına recall'ın yüksek olması gerekmez — ama
yanlış alarmı kare-başına yanlış pozitif belirler. Bu ilişki sezgiyle
kestirilemez; hesaplanır. Hesap yanlışsa yanlış `conf` eşiği seçilir ve
hata sahada, alarm gelmediğinde görülür.

Bu süit veri seti ve model İSTEMEZ — saf olasılık.
"""
import unittest

from src.fire import gereken_recall, onay_olasiligi, pencere_kare


class PencereKare(unittest.TestCase):
    def test_islenen_kare_sayisi_stride_ile_azalir(self):
        """25 fps kaynak, her 3 karede bir işlem, 6 sn pencere → ~50 kare."""
        self.assertEqual(pencere_kare(25.0, 3, 6.0), 50)

    def test_stride_1_tum_kareleri_isler(self):
        self.assertEqual(pencere_kare(25.0, 1, 6.0), 150)

    def test_en_az_bir_kare_doner(self):
        """Aşırı stride/kısa pencere sıfır kare vermemeli (sıfıra bölme kapanı)."""
        self.assertGreaterEqual(pencere_kare(1.0, 100, 0.1), 1)


class OnayOlasiligi(unittest.TestCase):
    """P(en az k onay | n bağımsız kare, kare-başına recall p)."""

    def test_kusursuz_dedektor_kesin_onaylar(self):
        self.assertAlmostEqual(onay_olasiligi(1.0, 50, 4), 1.0)

    def test_hic_gormeyen_dedektor_asla_onaylamaz(self):
        self.assertAlmostEqual(onay_olasiligi(0.0, 50, 4), 0.0)

    def test_tek_kare_tek_onay_recall_kadardir(self):
        self.assertAlmostEqual(onay_olasiligi(0.5, 1, 1), 0.5)

    def test_iki_karede_en_az_bir_onay(self):
        """P(≥1 | n=2, p=0.5) = 1 − 0.25 = 0.75."""
        self.assertAlmostEqual(onay_olasiligi(0.5, 2, 1), 0.75)

    def test_gerekenden_fazla_onay_istenemez(self):
        """k > n → olanaksız."""
        self.assertAlmostEqual(onay_olasiligi(0.9, 3, 4), 0.0)

    def test_sifir_onay_her_zaman_saglanir(self):
        self.assertAlmostEqual(onay_olasiligi(0.0, 10, 0), 1.0)

    def test_recall_arttikca_olasilik_azalmaz(self):
        onceki = -1.0
        for p in (0.0, 0.02, 0.05, 0.1, 0.3, 0.7, 1.0):
            simdi = onay_olasiligi(p, 50, 4)
            self.assertGreaterEqual(simdi, onceki)
            onceki = simdi

    def test_dusuk_recall_uzun_pencerede_yine_onaylar(self):
        """%10 kare-recall, 50 karede 4 onayı ~%75 olasılıkla sağlar.

        Sabit ÖLÇÜLDÜ, tahmin edilmedi: ilk yazımda ">0.75" varsayılmıştı,
        gerçek değer 0.7497 — yani varsayım kılpayı yanlıştı. Ürün açısından
        anlamı: %10 recall YETMEZ (dörtte bir olay kaçar); eşik %15
        civarında tutulmalı (bkz. GerekenRecall).
        """
        self.assertAlmostEqual(onay_olasiligi(0.10, 50, 4), 0.75, places=2)


class GerekenRecall(unittest.TestCase):
    def test_bulunan_recall_hedefi_saglar(self):
        p = gereken_recall(50, 4, 0.95)
        self.assertGreaterEqual(onay_olasiligi(p, 50, 4), 0.95)

    def test_bulunan_recall_gereksiz_yuksek_degil(self):
        """Bir tık altı hedefi KAÇIRMALI — yoksa 1.0 döndürmek de 'doğru' olurdu."""
        p = gereken_recall(50, 4, 0.95)
        self.assertLess(onay_olasiligi(max(0.0, p - 0.01), 50, 4), 0.95)

    def test_gereken_recall_sasirtici_derecede_dusuk(self):
        """Ürün kararının kendisi: 50 karede 4 onay için %15 kare-recall yeter.

        ÖLÇÜLDÜ (tahmin %8 idi ve yanlıştı). Naif beklenti — "dedektör olayı
        görmeli" — ~%90 recall ister; zamansal doğrulama bunu 6 kat aşağı
        çekiyor. `fire.conf` eşiğini yükseltip precision satın alma kararının
        dayanağı budur, ama marj %8 sanıldığı kadar geniş DEĞİL.
        """
        self.assertAlmostEqual(gereken_recall(50, 4, 0.95), 0.15, places=2)
        self.assertLess(gereken_recall(50, 4, 0.95), 0.20)

    def test_olanaksiz_hedefte_bir_doner(self):
        """k > n: hiçbir recall yetmez → 1.0 (yanıltıcı düşük sayı dönmesin)."""
        self.assertEqual(gereken_recall(3, 4, 0.95), 1.0)


class YapilandirmaTutarliligi(unittest.TestCase):
    def test_varsayilan_config_makul_bir_recall_istiyor(self):
        """config.yaml varsayılanları (6 sn / 4 kare, 25fps, stride 3) ile
        gereken kare-recall'ı ölç — belgeye yazdığımız sayı burada kilitlenir."""
        n = pencere_kare(25.0, 3, 6.0)
        p = gereken_recall(n, 4, 0.95)
        self.assertEqual(n, 50)
        self.assertAlmostEqual(p, 0.15, places=2)   # docs/yangin-modeli.md ile aynı sayı
        self.assertGreater(p, 0.01)   # sıfıra yakınsa hesap bozulmuş demektir


if __name__ == "__main__":
    unittest.main()
