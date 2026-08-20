#!/usr/bin/env python3
"""Kapılar NE olduğunu doğru sınıflandırmalı — iki boşluk, aynı aile.

İkisi de 2026-08-16'da CANLI yaşandı ve ikisinde de ölçü doğruydu, ETİKET
yanlıştı. `evidence.yml:61` bu dersi zaten yazmış:
  "Araç hatası (exit 2) disiplin ihlali DEĞİLDİR — sahte kırmızı üretmek,
   sahte yeşil kadar zararlıdır: ikisi de kanıtı bozar."

BOŞLUK 1 — `bin/incele.py`: "inceleyici koşamadı" ile "inceleyicinin hükmü
okunamadı" aynı sayılıyordu. Codex kotası bitince ENGEL veriyor ve gerekçe
olarak "çıktı ayrıştırılamadı" yazıyordu — oysa çıktı diye bir şey YOKTU.
Yanlış teşhis, kullanıcıya var olmayan bir sorunu aratır.

BOŞLUK 2 — `bin/anlik.py`: "merge/pull getirdi" ile "ajan düzenledi" aynı
sayılıyordu. PR birleştirilip `git pull` yapılınca çalışma ağacı değişiyor
ve tur kapısı "kaynak değişti ama test koşmadı" diye BLOKLUYORDU. Ajan o
dosyaya hiç dokunmamıştı; içeriği commit grafiğinden geldi ve o commit'ler
kendi kapılarından geçti.
"""
import importlib.util
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


incele = _load("incele")
anlik = _load("anlik")


class AracKosamadiTest(unittest.TestCase):
    """BOŞLUK 1 — araç yokluğu hüküm değildir."""

    # Bu oturumda YAKALANAN gerçek metin. Sabit vaka olarak gömüldü çünkü
    # canlı doğrulama kotaya bağlı; mantık burada kanıtlanır, entegrasyon
    # kota dönünce (2026-08-20) doğrulanır. Sınır koda yazılıdır.
    KOTA = ("codex-review.sh exit 1: ERROR: You've hit your usage limit. "
            "Upgrade to Pro ... try again at Aug 20th, 2026 1:11 PM.")
    AUTH = "codex-review.sh exit 1: ERROR: not logged in. Run `codex login`."
    YOK = "codex-review.sh exit 127: codex: command not found"
    BICIM = "SONUC satırı yok"

    def test_kota_hatasi_arac_yoklugudur(self):
        self.assertTrue(incele.arac_kosamadi(self.KOTA))

    def test_auth_hatasi_arac_yoklugudur(self):
        self.assertTrue(incele.arac_kosamadi(self.AUTH))

    def test_komut_bulunamadi_arac_yoklugudur(self):
        self.assertTrue(incele.arac_kosamadi(self.YOK))

    def test_bicim_hatasi_arac_yoklugu_DEGILDIR(self):
        """İnceleyici koştu ama hükmü okunamadı → bu HÂLÂ fail-closed."""
        self.assertFalse(incele.arac_kosamadi(self.BICIM))
        self.assertFalse(incele.arac_kosamadi(""))

    def test_kirpma_sinyali_yutmaz(self):
        """İşaret çıktının SONUNDA olsa bile sınıflandırmaya ulaşmalı.

        CANLI ÖLÇÜM 2026-08-16 — birim test geçmiş, entegrasyon DÜŞMÜŞTÜ:
        `codex_incele` stderr'i `[:200]` ile kırpıyordu ve kota mesajı
        ("usage limit") çıktının SONUNDAydı. Kırpılmış metinde işaret hiç
        yoktu; `arac_kosamadi` False dönüyor, kapı ENGEL veriyordu. Temiz
        mesajla yazılmış test bunu göremez — gerçek çıktı temiz gelmiyor.

        Daha kötüsü: düzeltme PR'ı bu commit OLMADAN squash edildi ve main'de
        `arac_kosamadi` VAR ama hiç tetiklenmeyen hâlde kaldı. Düzelmiş
        görünen, düzelmemiş kapı — bu bekçi onun tekrarını engeller.
        """
        uzun = ("Codex inceliyor...\n" + "+ diff satırı\n" * 60
                + "ERROR: You've hit your usage limit. Try again Aug 20th.")
        self.assertGreater(len(uzun), 200)
        self.assertNotIn("usage limit", uzun[:200])   # kırpma sinyali keser
        m = incele.ARAC_YOK.search(uzun)
        self.assertTrue(m, "işaret ham çıktıda bulunmalı")
        self.assertTrue(
            incele.arac_kosamadi(f"araç koşamadı ({m.group(0)}) — {uzun[:200]}"))

    def test_codex_incele_isareti_hata_metnine_tasir(self):
        """Uçtan uca: kırpılmış hata metni sınıflandırılabilir olmalı."""
        uzun_err = "x\n" * 300 + "ERROR: You've hit your usage limit."
        eski = incele._kos
        try:
            incele._kos = lambda *a, **k: (1, "", uzun_err)
            _out, hata = incele.codex_incele(1, butce=1)
        finally:
            incele._kos = eski
        self.assertTrue(incele.arac_kosamadi(hata),
                        f"kırpma sinyali yuttu: {hata[:80]}")

    def test_zaman_asimi_arac_yoklugu_DEGILDIR(self):
        """Zaman aşımı bütçe sorunudur; araç vardı, iş bitmedi."""
        self.assertFalse(incele.arac_kosamadi("zaman aşımı (900s)"))

    # --- karar tablosu ---

    TEMIZ = {"P0": [], "P1": [], "P2": []}

    def test_arac_kosamadiysa_ENGEL_degil_INSAN(self):
        """Ölçülemedi ≠ kirli. Karar insana gider, akış kilitlenmez."""
        k, gerekce = incele.karar("approval", self.TEMIZ, True, False,
                                  hata=self.KOTA)
        self.assertEqual(k, "insan")
        self.assertIn("ölçülemedi", gerekce.lower())

    def test_arac_kosamadiysa_bile_auto_merge_YOK(self):
        """Gevşetme yalnız ENGEL→İNSAN'dır; kanıtsız merge asla."""
        k, _g = incele.karar("auto", self.TEMIZ, True, False, hata=self.KOTA)
        self.assertEqual(k, "insan")

    def test_okunamadi_hala_ENGEL(self):
        """Araç koştu, hüküm okunmadı → fail-closed korunur."""
        k, gerekce = incele.karar("auto", self.TEMIZ, True, False,
                                  hata=self.BICIM)
        self.assertEqual(k, "engel")
        self.assertIn("ayrıştırılamadı", gerekce)

    def test_deny_arac_yoklugunda_da_ENGEL(self):
        """Politika ölçümden bağımsızdır; araç yokluğu deny'ı gevşetemez."""
        k, _g = incele.karar("deny", self.TEMIZ, True, False, hata=self.KOTA)
        self.assertEqual(k, "engel")

    def test_kirmizi_ci_arac_yoklugunda_da_ENGEL(self):
        k, _g = incele.karar("auto", self.TEMIZ, False, False, hata=self.KOTA)
        self.assertEqual(k, "engel")


class MergeGetirdiTest(unittest.TestCase):
    """BOŞLUK 2 — commit grafiğinden gelen içerik ajanın düzenlemesi değildir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.kok = self._tmp.name
        self.git("init", "-b", "main", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.yaz("src/app.py", "print(1)\n")
        self.git("add", "-A"); self.git("commit", "-qm", "ilk")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.kok,
                              capture_output=True, text=True)

    def yaz(self, rel, icerik):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as fh:
            fh.write(icerik)

    def test_merge_getirdigi_dosya_delta_sayilmaz(self):
        """Tur içinde HEAD ilerlerse, gelen içerik ajanın işi değildir."""
        onceki = anlik.al(self.kok)
        # Başka bir dalda yapılmış iş main'e geliyor (merge/pull benzetimi)
        self.git("checkout", "-qb", "yan")
        self.yaz("src/app.py", "print(2)\n")
        self.git("commit", "-aqm", "yan iş")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "yan")
        self.assertEqual(anlik.degisenler(self.kok, onceki), [])

    def test_merge_UZERINE_yapilan_duzenleme_delta_sayilir(self):
        """Gevşetme yalnız temiz dosyaya: ajan üstüne yazdıysa GÖRÜNÜR."""
        onceki = anlik.al(self.kok)
        self.git("checkout", "-qb", "yan")
        self.yaz("src/app.py", "print(2)\n")
        self.git("commit", "-aqm", "yan iş")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "yan")
        self.yaz("src/app.py", "print(3)\n")          # ajan dokunuyor
        self.assertIn("src/app.py", anlik.degisenler(self.kok, onceki))

    def test_commit_edilmemis_duzenleme_hala_gorunur(self):
        """HEAD hiç oynamadıysa eski davranış aynen korunur."""
        onceki = anlik.al(self.kok)
        self.yaz("src/app.py", "print(9)\n")
        self.assertIn("src/app.py", anlik.degisenler(self.kok, onceki))

    def test_izlenmeyen_yeni_dosya_hala_gorunur(self):
        onceki = anlik.al(self.kok)
        self.yaz("src/yeni.py", "x = 1\n")
        self.assertIn("src/yeni.py", anlik.degisenler(self.kok, onceki))

    def test_git_disinda_cokmez(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(anlik.degisenler(d, {}), [])


if __name__ == "__main__":
    unittest.main()
