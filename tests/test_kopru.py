#!/usr/bin/env python3
"""Kanıt köprüsü — kurulumu kolaylaştıran araç, kolayca da yanlış kurulur.

İki özellik sessizce bozulursa pahalıdır:
  1. PUBLIC repo reddi. Bozulursa PR açan herkes kurucunun makinesinde kod
     çalıştırabilir hâle gelir; bu bir stil hatası değil, uzaktan kod
     çalıştırmadır. Testi olmayan sert kapı, kapı değil temennidir.
  2. Geri dönüş yolu. Köprünün tek meşrulaştırıcısı geçici olmasıdır:
     `CI_RUNNER` silinince CI kendiliğinden GitHub runner'ına dönmeli.
     İfade yanlış yazılırsa dönüş yolu kapanır ve geçici olan kalıcı olur.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARAC = os.path.join(ROOT, "bin", "kopru.py")

spec = importlib.util.spec_from_file_location("_kopru", ARAC)
kopru = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kopru)


class PublicRepoReddi(unittest.TestCase):
    """Sert kapı: public repoya kurulum denenmeden reddedilir."""

    def setUp(self):
        self._gercek = kopru.gorunurluk
        self.cagrildi = []
        kopru.runner_indir = lambda d: self.cagrildi.append(d) or True

    def tearDown(self):
        kopru.gorunurluk = self._gercek

    def test_public_reddedilir(self):
        kopru.gorunurluk = lambda repo: "PUBLIC"
        self.assertEqual(kopru.kur("sahip/acik", 1), 2)

    def test_internal_de_reddedilir(self):
        # PRIVATE dışındaki HER değer reddedilir — beyaz liste, kara liste değil.
        kopru.gorunurluk = lambda repo: "INTERNAL"
        self.assertEqual(kopru.kur("sahip/ic", 1), 2)

    def test_red_kurulumu_hic_baslatmaz(self):
        # Red "sonra temizleriz" değil, "hiç başlamaz" olmalı.
        kopru.gorunurluk = lambda repo: "PUBLIC"
        kopru.kur("sahip/acik", 3)
        self.assertEqual(self.cagrildi, [])

    def test_gorunurluk_okunamazsa_reddedilir(self):
        # Bilinmeyen görünürlük "muhtemelen private"a düşmez (fail-closed).
        kopru.gorunurluk = lambda repo: None
        self.assertEqual(kopru.kur("sahip/bilinmiyor", 1), 2)


class GeriDonusYolu(unittest.TestCase):
    """Köprü tek anahtarla açılıp kapanmalı; ifade bunu garanti eder."""

    def test_runs_on_ifadesi_degiskene_bagli(self):
        self.assertIn("vars.CI_RUNNER", kopru.RUNS_ON)

    def test_degisken_bosken_github_runnerina_duser(self):
        # `|| 'ubuntu-latest'` olmadan değişken silindiğinde runs-on boş kalır
        # ve iş SONSUZA KADAR queued bekler — sessiz kilitlenme.
        self.assertIn("|| 'ubuntu-latest'", kopru.RUNS_ON)


class WorkflowYamasi(unittest.TestCase):
    def _repo(self, icerik):
        gecici = tempfile.mkdtemp()
        dizin = os.path.join(gecici, ".github", "workflows")
        os.makedirs(dizin)
        with open(os.path.join(dizin, "ci.yml"), "w") as f:
            f.write(icerik)
        return gecici, os.path.join(dizin, "ci.yml")

    def _oku(self, yol):
        with open(yol) as f:
            return f.read()

    def _yamala(self, kok):
        """Aracın insan çıktısı test raporunu boğmasın; dönüş kodu korunur."""
        with contextlib.redirect_stdout(io.StringIO()):
            return kopru.yamala(kok)

    def test_runs_on_anahtara_baglanir(self):
        kok, dosya = self._repo("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
        self._yamala(kok)
        self.assertIn(kopru.RUNS_ON, self._oku(dosya))
        self.assertNotIn("runs-on: ubuntu-latest\n", self._oku(dosya))

    def test_concurrency_eklenir(self):
        kok, dosya = self._repo("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
        self._yamala(kok)
        self.assertIn("cancel-in-progress: true", self._oku(dosya))

    def test_mevcut_concurrency_korunur(self):
        # deploy.yml'de `cancel-in-progress: false` BİLİNÇLİ bir karardır
        # (çalışan deploy yarıda kesilmez). Araç onu ezerse production'ı böler.
        kaynak = ("on: push\nconcurrency:\n  group: deploy\n"
                  "  cancel-in-progress: false\njobs:\n  d:\n    runs-on: ubuntu-latest\n")
        kok, dosya = self._repo(kaynak)
        self._yamala(kok)
        self.assertIn("cancel-in-progress: false", self._oku(dosya))
        self.assertNotIn("cancel-in-progress: true", self._oku(dosya))

    def test_iki_kez_kosmak_bozmaz(self):
        kok, dosya = self._repo("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
        self._yamala(kok)
        birinci = self._oku(dosya)
        self._yamala(kok)
        self.assertEqual(birinci, self._oku(dosya))

    def test_bos_workflow_atlanir(self):
        # 4Flow'da mobile-tests.yml boştu; boş dosyaya `jobs:` enjekte etmek
        # geçersiz YAML üretir ve TÜM workflow'u kırar.
        kok, dosya = self._repo("")
        self.assertEqual(self._yamala(kok), 0)
        self.assertEqual(self._oku(dosya), "")

    def test_workflow_dizini_yoksa_hata(self):
        self.assertEqual(self._yamala(tempfile.mkdtemp()), 2)


class MakineyeOzguYollar(unittest.TestCase):
    """Araç yolu repoya yazılırsa o yolu olmayan makinede kapı kırılır."""

    def test_android_sdk_varsa_env_yazilir(self):
        dizin = tempfile.mkdtemp()
        gercek = kopru.KOK
        try:
            sahte_kok = tempfile.mkdtemp()
            os.makedirs(os.path.join(sahte_kok, "Library", "Android", "sdk"))
            kopru.KOK = sahte_kok
            satirlar = kopru.env_dosyasi(dizin)
        finally:
            kopru.KOK = gercek
        self.assertTrue(any(s.startswith("ANDROID_HOME=") for s in satirlar))
        with open(os.path.join(dizin, ".env")) as f:
            self.assertIn("ANDROID_SDK_ROOT=", f.read())

    def test_sdk_yoksa_bos_env_yazilmaz(self):
        # Boş .env yazmak "ayarlandı" izlenimi verir; yokluk görünür kalmalı.
        dizin = tempfile.mkdtemp()
        gercek = kopru.KOK
        try:
            kopru.KOK = tempfile.mkdtemp()
            self.assertEqual(kopru.env_dosyasi(dizin), [])
        finally:
            kopru.KOK = gercek
        self.assertFalse(os.path.exists(os.path.join(dizin, ".env")))


class PathBicimi(unittest.TestCase):
    """`.path` TEK PATH dizesidir; satır satır yazılırsa yalnız ilki geçerli olur."""

    def _yaz(self):
        dizin = tempfile.mkdtemp()
        kopru.yol_dosyasi(dizin)
        with open(os.path.join(dizin, ".path")) as f:
            return f.read()

    def test_tek_satir(self):
        # Ölçüm 2026-08-16: satır satır yazılmış .path ile ilk koşular geçti
        # (action'lar önbellekteydi), yeni indirme gerekince `tar: command not
        # found`. Hata kurulumda değil, günler sonra ilgisiz yerde patladı.
        self.assertEqual(len(self._yaz().strip().split("\n")), 1)

    def test_iki_nokta_ile_ayrilir(self):
        self.assertIn(":", self._yaz())

    def test_temel_sistem_yollari_var(self):
        # /usr/bin olmadan tar, curl, git bulunamaz — runner ilk adımda ölür.
        yol = self._yaz().strip().split(":")
        for gerekli in ("/usr/bin", "/bin"):
            self.assertIn(gerekli, yol)


if __name__ == "__main__":
    unittest.main()
