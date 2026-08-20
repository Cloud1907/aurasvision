#!/usr/bin/env python3
"""pre-push kapısının davranışı — izole depoda, gerçek script ile.

Kapı üç şeyi zorlar: kernel doğrulaması, secret taraması, proje kapısı.
Üçünün de "yok" hâli "geçti" OLAMAZ; sessiz atlama en tehlikeli hatadır
(koruma illüzyonu). Bu testler o sessizlikleri kilitler.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import KAPI_PYTHON, kapi_yorumlayicisi_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_REL = ".agents/skills/security-review/scripts/scan_secrets.py"
PII_REL = ".agents/skills/security-review/scripts/scan_personal_data.py"
GECMIS_REL = ".agents/skills/security-review/scripts/scan_gecmis.py"
# Kişisel veri ve geçmiş tarayıcıları scan_secrets'ı içe aktarıyor (kural ve
# dışlama TEK kaynaktan gelmeli); izole depoda üçü de bulunmalı — kapı
# eksik tarayıcıda fail-closed bloklar.
TARAYICILAR = (SCAN_REL, PII_REL, GECMIS_REL)


def kur(td, proje_kapisi=None, kapi_calistirilabilir=True, tarayici=True,
        validate_kod=0, ortam=None):
    """İzole bir depoda kapıyı kurar; pre-push'un çıkış kodunu döndürür.

    validate_kod: sahte kernel doğrulayıcısının çıkış kodu.
      0 geçti · 1 kural ihlali · 2 araç hatası (doğrulama koşamadı).
    ortam: alt sürece verilecek ortam (AURAS_PYTHON denemeleri için).
    """
    os.makedirs(os.path.join(td, "bin", "hooks"))
    shutil.copy2(os.path.join(ROOT, "bin", "hooks", "pre-push"),
                 os.path.join(td, "bin", "hooks", "pre-push"))
    with open(os.path.join(td, "bin", "validate.py"), "w") as fh:
        fh.write("#!/usr/bin/env python3\nimport sys\n"
                 f'print("ok")\nsys.exit({validate_kod})\n')
    if tarayici:
        for rel in TARAYICILAR:
            hedef = os.path.join(td, rel)
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), hedef)
    with open(os.path.join(td, "temiz.py"), "w") as fh:
        fh.write("x = 1\n")
    if proje_kapisi is not None:
        yol = os.path.join(td, "bin", "hooks", "proje-kapisi")
        with open(yol, "w") as fh:
            fh.write(proje_kapisi)
        if kapi_calistirilabilir:
            os.chmod(yol, 0o755)
        else:
            os.chmod(yol, 0o644)
    subprocess.run(["git", "init", "-q", "-b", "main", td], check=True,
                   capture_output=True)
    # Dosyalar STAGE edilmeli: secret kapısı --git modunda yalnız izlenen
    # içeriği tarar (push edilecek olan budur). Stage'lenmemiş depo "0 dosya
    # tarandı" verir ve bu bilinçli olarak 'temiz' sayılmaz.
    subprocess.run(["git", "-C", td, "add", "-A"], check=True,
                   capture_output=True)
    # input="" ŞART: pre-push sonunda 'while read' ile git'ten ref bekler;
    # stdin miras alınırsa test süresiz asılır.
    p = subprocess.run(["sh", os.path.join(td, "bin", "hooks", "pre-push")],
                       capture_output=True, text=True, cwd=td, timeout=60,
                       input="", env=ortam)
    return p.returncode, p.stdout + p.stderr


class PrePushTest(unittest.TestCase):
    def test_temiz_depo_gecer(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(kur(td)[0], 0)

    def test_kural_ihlali_bloklar(self):
        with tempfile.TemporaryDirectory() as td:
            kod, cikti = kur(td, validate_kod=1)
            self.assertEqual(kod, 1)
            self.assertIn("dogrulamasi basarisiz", cikti)

    def test_arac_hatasi_ihlalden_ayrilir(self):
        """"Koşamadı" ile "kaldı" aynı mesajı almaz.

        2026-08-07: Homebrew python3'u 3.14'e taşıdı, PyYAML yeni
        yorumlayıcıda yoktu; validate.py 2 ile çıktı, kapı "dogrulama
        BASARISIZ" dedi. Kullanıcı olmayan bir kural ihlalini aramaya
        başlar. İkisi de bloklar (fail-closed doğru), ama sebep doğru
        söylenmeli — yanlış teşhis --no-verify alışkanlığı üretir.
        """
        with tempfile.TemporaryDirectory() as td:
            kod, cikti = kur(td, validate_kod=2)
            self.assertEqual(kod, 1, "araç hatası da bloklamalı (fail-closed)")
            self.assertIn("KOSAMADI", cikti)
            self.assertNotIn("dogrulamasi basarisiz", cikti)

    def test_sahte_yorumlayici_kapiyi_sessizce_gecemez(self):
        """AURAS_PYTHON kapıyı köreltemez.

        Denetim bulgusu 2026-08-07 (security-review, bu PR'ın kendi diff'i):
        `AURAS_PYTHON=/usr/bin/true git push` ile secret'lı push kapıyı
        SESSİZCE geçti — exit 0, sıfır satır çıktı. `true` argümanları yok
        sayıp 0 döndüğü için kapı "doğrulama geçti" sandı. Çıkış kodu,
        süreç kendi hakkında yalan söyleyebiliyorsa kanıt değildir.
        """
        with tempfile.TemporaryDirectory() as td:
            ortam = dict(os.environ, AURAS_PYTHON="/usr/bin/true")
            kod, cikti = kur(td, ortam=ortam)
            self.assertEqual(kod, 1, "sahte yorumlayıcı push'u geçirmemeli")
            self.assertIn("AURAS_PYTHON gecerli bir python3 degil", cikti)

    @kapi_yorumlayicisi_gerekir
    def test_gecerli_override_gorunur_olur(self):
        """Meşru override çalışır ama SESSİZ olmaz — kapı kör kalmasın.

        Override MEŞRU olmalı, yoksa test kendi senaryosunu kurmuyor demektir.
        Eskiden `sys.executable` veriliyordu; süiti PyYAML'sız bir yorumlayıcı
        koştuğunda kapı onu HAKLI OLARAK reddediyordu (exit 1) ve test kırmızı
        yanıyordu — kusur kapıda değil, testin kabulünde. Doğrusu adayı
        kapının kendi ölçütüyle seçmek (bkz. ortam.kapi_yorumlayicisi).
        """
        with tempfile.TemporaryDirectory() as td:
            ortam = dict(os.environ, AURAS_PYTHON=KAPI_PYTHON)
            kod, cikti = kur(td, ortam=ortam)
            self.assertEqual(kod, 0, f"meşru override bloklandı:\n{cikti}")
            # Duyurunun İÇİNDE yol da aranır. Yalnız cümleyi aramak yetmez:
            # kapı override'ı yok sayıp yedek listeden BAŞKA bir yorumlayıcıya
            # düşse ve duyuruyu yine de bassa, cümle-arayan iddia yeşil kalırdı
            # — duyuru var ama yanlış şeyi duyuruyor olurdu. Ölçüldü: tam bu
            # sabotajda cümle-arayan sürüm OK diyordu.
            self.assertIn(f"AURAS_PYTHON ile kosuyor: {KAPI_PYTHON}", cikti,
                          "override duyurulmadı ya da duyurulan yorumlayıcı "
                          "verilen değil — kapı kör kalır")

    def test_tarayici_yoksa_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            kod, cikti = kur(td, tarayici=False)
            self.assertEqual(kod, 1, "tarayıcı yoksa sessizce geçmemeli")
            self.assertIn("tarayicisi bulunamadi", cikti)

    def test_kisisel_veri_tarayicisi_yoksa_fail_closed(self):
        """Yeni kapının "yok" hâli de "geçti" OLAMAZ.

        Secret kapısıyla aynı kural: eksik kurulum görünür olmalı, sessizce
        atlanmamalı — sessiz atlama koruma illüzyonudur.
        """
        with tempfile.TemporaryDirectory() as td:
            kur(td)                      # her şeyi kur, sonra PII'yi sil
            os.remove(os.path.join(td, PII_REL))
            p = subprocess.run(
                ["sh", os.path.join(td, "bin", "hooks", "pre-push")],
                capture_output=True, text=True, cwd=td, timeout=60, input="")
            self.assertEqual(p.returncode, 1)
            self.assertIn("kisisel veri tarayicisi bulunamadi",
                          p.stdout + p.stderr)

    def test_toplu_kisisel_veri_push_u_bloklar(self):
        with tempfile.TemporaryDirectory() as td:
            kur(td)
            with open(os.path.join(td, "dump.json"), "w", encoding="utf-8") as fh:
                fh.write("[" + ",".join(
                    f'{{"email":"k{i}@sirket.com.tr"}}' for i in range(20)) + "]")
            subprocess.run(["git", "-C", td, "add", "-A"], check=True,
                           capture_output=True)
            p = subprocess.run(
                ["sh", os.path.join(td, "bin", "hooks", "pre-push")],
                capture_output=True, text=True, cwd=td, timeout=60, input="")
            self.assertEqual(p.returncode, 1)
            self.assertIn("kisisel veri kapisi gecilemedi", p.stdout + p.stderr)

    def test_proje_kapisi_yoksa_gecer(self):
        # Uzantı noktası OPSİYONEL — yokluğu ihlal değildir
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(kur(td, proje_kapisi=None)[0], 0)

    def test_proje_kapisi_ihlalde_bloklar(self):
        with tempfile.TemporaryDirectory() as td:
            kod, cikti = kur(td, '#!/bin/sh\necho "yasak: X"\nexit 1\n')
            self.assertEqual(kod, 1)
            self.assertIn("proje kapisi gecilemedi", cikti)

    def test_proje_kapisi_temizse_gecer(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(kur(td, "#!/bin/sh\nexit 0\n")[0], 0)

    def test_proje_kapisi_ref_akisini_yiyemez(self):
        """Denetim bulgusu: kapı stdin okursa git'in ref listesini yer.

        O zaman sonraki while-read hiçbir ref görmez ve ref'e dayanan her
        politika (ör. 'main'e doğrudan push' uyarısı) sessizce kaybolur.
        """
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "bin", "hooks"))
            shutil.copy2(os.path.join(ROOT, "bin", "hooks", "pre-push"),
                         os.path.join(td, "bin", "hooks", "pre-push"))
            with open(os.path.join(td, "bin", "validate.py"), "w") as fh:
                fh.write('#!/usr/bin/env python3\nprint("ok")\n')
            for rel in TARAYICILAR:
                hedef = os.path.join(td, rel)
                os.makedirs(os.path.dirname(hedef), exist_ok=True)
                shutil.copy2(os.path.join(ROOT, rel), hedef)
            with open(os.path.join(td, "temiz.py"), "w") as fh:
                fh.write("x = 1\n")
            # Stdin'i sonuna kadar yiyen bir proje kapısı
            yol = os.path.join(td, "bin", "hooks", "proje-kapisi")
            with open(yol, "w") as fh:
                fh.write("#!/bin/sh\ncat >/dev/null\nexit 0\n")
            os.chmod(yol, 0o755)
            subprocess.run(["git", "init", "-q", "-b", "main", td], check=True,
                           capture_output=True)
            subprocess.run(["git", "-C", td, "add", "-A"], check=True,
                           capture_output=True)
            # Ref satırındaki SHA'lar GERÇEK olmalı: geçmiş kapısı artık bu
            # aralığı tarıyor ve uydurma SHA fail-closed bloklanır — o zaman
            # test ref akışını değil, kapının başka davranışını ölçer.
            subprocess.run(["git", "-C", td, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-q", "-m", "t"],
                           check=True, capture_output=True)
            sha = subprocess.run(["git", "-C", td, "rev-parse", "HEAD"],
                                 check=True, capture_output=True,
                                 text=True).stdout.strip()
            p = subprocess.run(
                ["sh", os.path.join(td, "bin", "hooks", "pre-push")],
                capture_output=True, text=True, cwd=td, timeout=60,
                input=f"refs/heads/main {sha} refs/heads/main {sha}\n")
            self.assertEqual(p.returncode, 0)
            self.assertIn("dogrudan main", p.stdout,
                          "proje kapısı git'in ref akışını yemiş — ref'e "
                          "dayanan politikalar sessizce kayboluyor")

    def test_calistirilamayan_proje_kapisi_sessizce_atlanmaz(self):
        # chmod unutulursa kapı kaybolurdu — görünür hata olmalı
        with tempfile.TemporaryDirectory() as td:
            kod, cikti = kur(td, "#!/bin/sh\nexit 1\n",
                             kapi_calistirilabilir=False)
            self.assertEqual(kod, 1)
            self.assertIn("calistirilabilir degil", cikti)


if __name__ == "__main__":
    unittest.main()
