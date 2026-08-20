#!/usr/bin/env python3
"""Rapor kaynak doğrulayıcısı + test-önce disiplini testleri.

test_skill_validators.py 400 satır sınırını aştığı için ayrıldı: secret
tarayıcısı ile kaynak doğrulayıcısı iki ayrı kapı, iki ayrı dosya.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITATIONS = os.path.join(ROOT, ".agents", "skills", "research-with-evidence",
                         "scripts", "check_citations.py")
TESTFIRST = os.path.join(ROOT, ".agents", "skills", "implement-change",
                         "scripts", "check_test_first.py")


def kos(script, *arg):
    p = subprocess.run([sys.executable, script, *arg],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    return p.returncode, p.stdout + p.stderr


class CheckCitationsTest(unittest.TestCase):
    """Komut çıktısı da kaynaktır.

    4cast denetimi (2026-08-06): kanıtların çoğu `komut → sonuç` biçimindeydi
    (`gh api … → HTTP 403`, `git shortlog → semih 191`) ama araç yalnız URL ve
    dosya:satır tanıyordu → iyi kaynaklandırılmış rapor %89 kaynaksız çıktı.
    Yanlış sinyal, sinyalsizlikten kötüdür: aracı susturmaya iter.
    """

    def olc(self, govde):
        with tempfile.TemporaryDirectory() as td:
            yol = os.path.join(td, "r.md")
            with open(yol, "w", encoding="utf-8") as fh:
                fh.write("# Rapor\n\n## Bulgular\n\n" + govde + "\n")
            return kos(CITATIONS, yol)

    def test_komut_ciktisi_kaynak_sayilir(self):
        kod, cikti = self.olc(
            "Ana dalda koruma kurulamıyor; `gh api repos/x/y/branches/main/"
            "protection` → HTTP 403 döndü ve bu Free plan sınırıdır.")
        self.assertEqual(kod, 0, f"komut→sonuç kaynak sayılmadı:\n{cikti}")

    def test_ciplak_komut_adi_kaynak_sayilmaz(self):
        # Komutu ANMAK kanıt değildir; koşup sonucu göstermek kanıttır.
        kod, _c = self.olc(
            "Bu depoda kalite ölçümü için `bin/kalite.py` kullanılmalıdır "
            "ve ölçüm düzenli tekrarlanmalıdır diye düşünüyoruz.")
        self.assertEqual(kod, 1, "çıplak komut anması kaynak sayıldı")

    def test_yonetici_ozeti_iddia_sayilmaz(self):
        # Özet, altında kanıtlanmış bulguyu tekrar eder; kaynak orada durur.
        with tempfile.TemporaryDirectory() as td:
            yol = os.path.join(td, "r.md")
            with open(yol, "w", encoding="utf-8") as fh:
                fh.write("# Rapor\n\n## Yönetici özeti\n\n"
                         "Ürün sağlam ama süreç boruları delik; bulguların "
                         "hiçbiri mimari yeniden yazım gerektirmiyor.\n\n"
                         "## Bulgular\n\n"
                         "Deploy testlere bağlı değil "
                         "`.github/workflows/deploy.yml:16` satırında "
                         "tetikleyici doğrudan push olarak tanımlı.\n")
            self.assertEqual(kos(CITATIONS, yol)[0], 0,
                             "özet bölümü iddia sayıldı")

    def test_yorum_etiketi_kaynaksiz_sayilmaz(self):
        # Açıkça "bu çıkarım" demek, ölçümmüş gibi sunmanın tersidir.
        kod, _c = self.olc(
            "Devralma maliyetini belirleyen şey tek dosyada yoğunlaşan karar "
            "sayısıdır `[yorum]` — bu depoda ölçülmedi, denetçi çıkarımıdır.")
        self.assertEqual(kod, 0, "[yorum] etiketi kaynaksız sayıldı")

    def test_dosya_satir_hala_kaynak(self):
        kod, _c = self.olc(
            "Deploy testlere bağlı değil; `.github/workflows/deploy.yml:16` "
            "satırında tetikleyici doğrudan push olarak tanımlanmış durumda.")
        self.assertEqual(kod, 0)


class CheckTestFirstTest(unittest.TestCase):
    def test_kaynak_varken_testsiz_diff_uyarir(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-b", "main", td], check=True,
                           capture_output=True)
            for k, v in (("user.email", "t@t.t"), ("user.name", "t")):
                subprocess.run(["git", "-C", td, "config", k, v], check=True,
                               capture_output=True)
            with open(os.path.join(td, "app.py"), "w") as fh:
                fh.write("x = 1\n")
            subprocess.run(["git", "-C", td, "add", "-A"], check=True,
                           capture_output=True)
            subprocess.run(["git", "-C", td, "commit", "-m", "ilk"],
                           check=True, capture_output=True)
            with open(os.path.join(td, "app.py"), "a") as fh:
                fh.write("y = 2\n")
            p = subprocess.run([sys.executable, TESTFIRST],
                               capture_output=True, text=True, cwd=td,
                               timeout=60)
            self.assertEqual(p.returncode, 1,
                             "kaynak değişti test değişmedi — uyarmalıydı")


if __name__ == "__main__":
    unittest.main()
