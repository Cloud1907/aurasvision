#!/usr/bin/env python3
"""Push aralığı (geçmiş) secret taraması — index taramasının kör noktası.

Bağımsız inceleme bulgusu (Codex, 2026-08-12): pre-push secret kapısı yalnız
index'i (git ls-files) tarıyordu. Commit A'da eklenip commit B'de silinen
sır, index ve çalışma kopyası temizken push'la uzak GEÇMİŞE sızar — geri
alınamaz. Bu testler o vakayı kilitler: remote_sha..local_sha aralığındaki
her commit'in EKLENEN satırları taranmalı.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, ".agents", "skills", "security-review", "scripts")
GECMIS = os.path.join(SCRIPTS, "scan_gecmis.py")
SIFIR = "0" * 40

# Parçalı kurulum: düz yazılırsa bu dosyanın KENDİSİ secret kapısına takılır
# (tests/test_skill_validators.py ile aynı konvansiyon). Stripe dokümanındaki
# örnek anahtar — gerçek hesaba ait değil.
ORNEK_ANAHTAR = "sk_" + "live_4eC39HqLyjWDarjtT1zdp7dc"


def git(td, *arg):
    return subprocess.run(
        ["git", "-C", td, "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *arg],
        check=True, capture_output=True, text=True)


def commit_yap(td, mesaj):
    git(td, "add", "-A")
    git(td, "commit", "-q", "-m", mesaj)
    return git(td, "rev-parse", "HEAD").stdout.strip()


def depo_kur(td):
    """Boş depo + temiz taban commit'i; taban SHA'sını döndürür."""
    subprocess.run(["git", "init", "-q", "-b", "main", td], check=True,
                   capture_output=True)
    with open(os.path.join(td, "temiz.py"), "w") as fh:
        fh.write("x = 1\n")
    return commit_yap(td, "taban")


def gecmis_sirli_depo(td):
    """Sır commit A'da eklenir, B'de silinir → (taban, a, b) SHA'ları."""
    taban = depo_kur(td)
    with open(os.path.join(td, "sir.py"), "w") as fh:
        fh.write(f'KEY = "{ORNEK_ANAHTAR}"\n')
    a = commit_yap(td, "A: sir ekle")
    os.remove(os.path.join(td, "sir.py"))
    b = commit_yap(td, "B: sir sil")
    return taban, a, b


def tara(*arg):
    p = subprocess.run([sys.executable, GECMIS, *arg],
                       capture_output=True, text=True, timeout=120)
    # stderr de kapı çıktısıdır: kullanım hataları oraya yazılır.
    return p.returncode, p.stdout + p.stderr


class GecmisTaramaTest(unittest.TestCase):
    def test_eklenip_silinen_sir_yakalanir(self):
        """Kör noktanın kendisi: index temiz, geçmiş kirli → BULGU."""
        with tempfile.TemporaryDirectory() as td:
            taban, a, _b = gecmis_sirli_depo(td)
            kod, cikti = tara("--push-range", taban, "HEAD", td)
            self.assertEqual(kod, 1, f"geçmişteki sır kaçtı:\n{cikti}")
            self.assertIn("sir.py", cikti)
            # Bulgu HANGİ commit'te olduğunu söylemeli — temizlik rebase
            # ister, hedef commit'i okuyucu aramak zorunda kalmamalı.
            self.assertIn(a[:12], cikti)

    def test_temiz_aralik_gecer(self):
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            with open(os.path.join(td, "ek.py"), "w") as fh:
                fh.write("y = 2\n")
            commit_yap(td, "temiz ek")
            kod, cikti = tara("--push-range", taban, "HEAD", td)
            self.assertEqual(kod, 0, cikti)

    def test_yeni_dal_tum_yerel_commitleri_tarar(self):
        """remote_sha sıfırsa (yeni dal) uzağa gidecek HER commit taranır."""
        with tempfile.TemporaryDirectory() as td:
            gecmis_sirli_depo(td)
            kod, cikti = tara("--push-range", SIFIR, "HEAD", td)
            self.assertEqual(kod, 1, f"yeni dalda geçmiş taranmadı:\n{cikti}")
            self.assertIn("sir.py", cikti)

    def test_uzakta_olmayan_remote_sha_yedege_duser(self):
        """Yerelde bilinmeyen remote_sha aralığı kurulamaz — kapı yine de
        taramalı (yedek: --not --remotes), sessizce geçmemeli."""
        with tempfile.TemporaryDirectory() as td:
            gecmis_sirli_depo(td)
            yok_sha = "a" * 40
            kod, cikti = tara("--push-range", yok_sha, "HEAD", td)
            self.assertEqual(kod, 1, f"bilinmeyen remote_sha kapıyı köreltti:\n{cikti}")

    def test_muafiyet_uygulanir_ama_gorunur(self):
        """Allowlist aynı sözleşmeyle geçerli: bastırır ama 'muaf:' ile söyler."""
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            os.makedirs(os.path.join(td, ".agents"))
            with open(os.path.join(td, ".agents", "secret-allowlist.txt"),
                      "w") as fh:
                fh.write("fixtures/*  # test fixture — bilinçli sahte anahtar\n")
            os.makedirs(os.path.join(td, "fixtures"))
            with open(os.path.join(td, "fixtures", "sir.py"), "w") as fh:
                fh.write(f'KEY = "{ORNEK_ANAHTAR}"\n')
            commit_yap(td, "A: fixture ekle")
            os.remove(os.path.join(td, "fixtures", "sir.py"))
            commit_yap(td, "B: fixture sil")
            kod, cikti = tara("--push-range", taban, "HEAD", td)
            self.assertEqual(kod, 0, cikti)
            self.assertIn("muaf:", cikti, "bastırma sessiz olamaz")

    def test_dislama_uygulanir(self):
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            os.makedirs(os.path.join(td, "skill", "eval"))
            with open(os.path.join(td, "skill", "eval", "cases.md"), "w") as fh:
                fh.write(f"beklenen bulgu: {ORNEK_ANAHTAR}\n")
            commit_yap(td, "A: eval fixture")
            kod, cikti = tara("--push-range", taban, "HEAD",
                              "--exclude", "*/eval/*", td)
            self.assertEqual(kod, 0, cikti)

    def test_commit_mesajindaki_sir_yakalanir(self):
        """Mesaj da push'la uzağa gider — diff taraması onu görmez.

        Güvenlik denetimi kanıtı (2026-08-12): `git commit -m "fix: anahtar
        sk_live_..."` eklenen-satır taramasından temiz geçiyordu.
        """
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            with open(os.path.join(td, "ek.py"), "w") as fh:
                fh.write("y = 2\n")
            git(td, "add", "-A")
            git(td, "commit", "-q", "-m", f"fix: anahtar {ORNEK_ANAHTAR} kullan")
            kod, cikti = tara("--push-range", taban, "HEAD", td)
            self.assertEqual(kod, 1, f"mesajdaki sır kaçtı:\n{cikti}")
            self.assertIn("commit mesaj", cikti)

    def test_bos_aralik_temiz_ama_gorunur(self):
        """Aynı SHA'ya push (yeni commit yok) bulgu üretmez, kapı asılmaz."""
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            kod, cikti = tara("--push-range", taban, taban, td)
            self.assertEqual(kod, 0, cikti)

    def test_gecersiz_sha_arac_hatasi(self):
        """Bozuk girdi 'temiz' okunamaz — kullanım hatası exit 2."""
        with tempfile.TemporaryDirectory() as td:
            depo_kur(td)
            kod, _cikti = tara("--push-range", SIFIR, "bozuk-sha", td)
            self.assertEqual(kod, 2)


class PrePushGecmisTest(unittest.TestCase):
    """Kancanın kendisi aralığı taramalı — tarayıcı tek başına kapı değildir."""

    def kanca_kur(self, td):
        os.makedirs(os.path.join(td, "bin", "hooks"))
        shutil.copy2(os.path.join(ROOT, "bin", "hooks", "pre-push"),
                     os.path.join(td, "bin", "hooks", "pre-push"))
        with open(os.path.join(td, "bin", "validate.py"), "w") as fh:
            fh.write('#!/usr/bin/env python3\nprint("ok")\n')
        for ad in ("scan_secrets.py", "scan_personal_data.py",
                   "scan_gecmis.py"):
            hedef = os.path.join(td, ".agents", "skills", "security-review",
                                 "scripts", ad)
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copy2(os.path.join(SCRIPTS, ad), hedef)

    def kanca_kos(self, td, stdin):
        p = subprocess.run(["sh", os.path.join(td, "bin", "hooks", "pre-push")],
                           capture_output=True, text=True, cwd=td, timeout=120,
                           input=stdin)
        return p.returncode, p.stdout + p.stderr

    def test_gecmisteki_sir_pushu_bloklar(self):
        """Uçtan uca kör nokta: index temiz, işlem geçmişi kirli → PUSH YOK."""
        with tempfile.TemporaryDirectory() as td:
            taban, _a, b = gecmis_sirli_depo(td)
            self.kanca_kur(td)
            commit_yap(td, "kanca kurulumu")
            kod, cikti = self.kanca_kos(
                td, f"refs/heads/main {b} refs/heads/main {taban}\n")
            self.assertEqual(kod, 1, f"geçmişteki sır push'u geçti:\n{cikti}")
            self.assertIn("gecmis secret kapisi", cikti)

    def test_temiz_gecmis_pushu_gecer(self):
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            self.kanca_kur(td)
            b = commit_yap(td, "temiz is")
            kod, cikti = self.kanca_kos(
                td, f"refs/heads/is {b} refs/heads/is {taban}\n")
            self.assertEqual(kod, 0, cikti)

    def test_ref_silme_pushu_takilmaz(self):
        """Dal silme push'unda (local_sha sıfır) taranacak commit yok."""
        with tempfile.TemporaryDirectory() as td:
            taban = depo_kur(td)
            self.kanca_kur(td)
            commit_yap(td, "kanca kurulumu")
            kod, cikti = self.kanca_kos(
                td, f"(delete) {SIFIR} refs/heads/eski {taban}\n")
            self.assertEqual(kod, 0, cikti)

    def test_gecmis_tarayici_yoksa_fail_closed(self):
        """Kapının 'yok' hâli 'geçti' OLAMAZ (secret/PII kapısıyla aynı kural)."""
        with tempfile.TemporaryDirectory() as td:
            depo_kur(td)
            self.kanca_kur(td)
            os.remove(os.path.join(td, ".agents", "skills", "security-review",
                                   "scripts", "scan_gecmis.py"))
            commit_yap(td, "kanca kurulumu")
            kod, cikti = self.kanca_kos(td, "")
            self.assertEqual(kod, 1, "tarayıcı yokken sessizce geçti")
            self.assertIn("gecmis secret tarayicisi bulunamadi", cikti)


if __name__ == "__main__":
    unittest.main()
