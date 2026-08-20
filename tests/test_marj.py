#!/usr/bin/env python3
"""Eşiğe yakınlık bekçisi — ratchet'in 401'de konuşması geç kalıyordu.

ÖLÇÜM 2026-08-16: repoda 13 dosya eşiğin %85-100 bandında, İKİSİ duvarda
(`bin/kernel_dosyalari.py` 400/400, `bin/route.py` 399/400). Ratchet yalnız
401'de konuşur; yani bir katkıcının aldığı İLK sinyal, kırılmış kapıdır —
üstelik ilgisiz bir değişikliğin ortasında.

Bu tam olarak iki kez yaşandı, aynı gün: `bin/incele.py` 400/400 iken kırpma
düzeltmesi onu 407'ye çıkardı ve acil bir hata düzeltmesi, zorunlu bir
refactor'la aynı PR'a sıkıştı. Sonra `bin/kernel_dosyalari.py` 400'e dayandı.

Bu bekçi mekanizmanın SINIFINI de sabitler: `bul()` bir PUSULADIR, kapı
değil — çıkış kodunu ASLA değiştirmez. Uyarıyı kapıya çevirmek, tabanı
gizlice 380'e indirmek olurdu; o karar ADR ister, uyarı istemez.
"""
import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(ad):
    spec = importlib.util.spec_from_file_location(
        ad, os.path.join(ROOT, "bin", f"{ad}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


marj = _load("marj")
kalite = _load("kalite")

ESIK = {"max_dosya_satir": 100, "max_fonksiyon_satir": 20, "max_dal": 10}


class BantTest(unittest.TestCase):
    """Bandın içi/dışı — yakınlık ölçüsünün kendisi."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.kok = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def yaz(self, ad, satir_sayisi):
        yol = os.path.join(self.kok, ad)
        with open(yol, "w", encoding="utf-8") as fh:
            fh.write("x = 1\n" * satir_sayisi)

    def turler(self, **kw):
        """Banda giren öğelerin kimlik kümesi."""
        return {kimlik for _oran, _tur, kimlik, _deger, _limit
                in marj.bul(self.kok, ESIK, **kw)}

    def test_esikte_duran_dosya_gorunur(self):
        """Tam limitte olan dosya EN acil vakadır — ihlal değil, ama duvarda."""
        self.yaz("tam.py", 100)
        self.assertIn("tam.py", self.turler())

    def test_bandin_icindeki_gorunur(self):
        self.yaz("yakin.py", 96)
        self.assertIn("yakin.py", self.turler())

    def test_ihlal_eden_GORUNMEZ(self):
        """İhlali ratchet söylüyor; burada tekrar etmek çift sayım olurdu."""
        self.yaz("buyuk.py", 140)
        self.assertNotIn("buyuk.py", self.turler())

    def test_uzaktaki_gorunmez(self):
        self.yaz("kucuk.py", 40)
        self.assertNotIn("kucuk.py", self.turler())

    def test_orana_gore_sirali(self):
        """En acil önce: 100/100, sonra 96/100."""
        self.yaz("a_yakin.py", 96)
        self.yaz("b_tam.py", 100)
        sira = [k for _o, _t, k, _d, _l in marj.bul(self.kok, ESIK)]
        self.assertEqual(sira[:2], ["b_tam.py", "a_yakin.py"])

    def test_bant_daraltilabilir(self):
        """Gürültü ayarı çağıranın; ölçü sabit."""
        self.yaz("yakin.py", 90)
        self.assertIn("yakin.py", self.turler(bant=0.85))
        self.assertNotIn("yakin.py", self.turler(bant=0.95))

    def test_uzun_fonksiyon_da_olculur(self):
        with open(os.path.join(self.kok, "f.py"), "w", encoding="utf-8") as fh:
            fh.write("def uzun():\n" + "    x = 1\n" * 19)
        turler = {t for _o, t, _k, _d, _l in marj.bul(self.kok, ESIK)}
        self.assertIn("uzun_fonksiyon", turler)

    def test_bos_dizinde_cokmez(self):
        self.assertEqual(marj.bul(self.kok, ESIK), [])

    def test_dosya_duvari_dal_gurultusunun_altinda_kalmaz(self):
        """Tür başına gösterim: 10/10 dallar, 399/400 dosyayı gizlemesin.

        Düz oran sıralaması bunu YAPIYORDU (2026-08-16): dört adet tam
        limitte dal listeyi doldurup uyarıyı doğuran vakayı kapağın altında
        bıraktı. Uyarı, kendi sebebini gizlerse uyarı değildir.
        """
        yakin = ([(1.0, "karmasik_fonksiyon", f"d{i}.py:1", 10, 10)
                  for i in range(6)]
                 + [(0.9975, "buyuk_dosya", "route.py", 399, 400)])
        metin = "\n".join(marj.satirlar(yakin))
        self.assertIn("route.py", metin)
        # 7 öğe, tür başına 2 → 3 gösterilir; kalan 4 SAYILIR, gizlenmez.
        self.assertIn("4 öğe daha", metin)

    def test_bos_girdi_satir_uretmez(self):
        self.assertEqual(marj.satirlar([]), [])


class PusulaTest(unittest.TestCase):
    """Sınıf sabiti: uyarı GÖRÜNÜR ama HİÇBİR ŞEYİ bloklamaz."""

    def test_cikis_kodunu_degistirmez(self):
        """Bu repoda şu an banda giren öğe VAR; yine de --check yeşil kalmalı."""
        self.assertTrue(marj.bul(ROOT, kalite.ayarlar()),
                        "ölçüm ön-koşulu: repoda banda giren öğe olmalı")
        cikti = io.StringIO()
        with redirect_stdout(cikti):
            kod = kalite.main(["--check"])
        self.assertEqual(kod, 0, "yakınlık uyarısı kapıya dönüşmüş")
        self.assertIn("EŞİĞE YAKIN", cikti.getvalue())

    def test_json_ciktisinda_da_var(self):
        """Makine okuyucusu uyarıyı görebilmeli (CI/rapor)."""
        cikti = io.StringIO()
        with redirect_stdout(cikti):
            kalite.main(["--json"])
        self.assertIn("yaklasan", cikti.getvalue())


if __name__ == "__main__":
    unittest.main()
