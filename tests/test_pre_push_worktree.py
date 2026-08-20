#!/usr/bin/env python3
"""pre-push kapısı git worktree'sinden de koşmalı — GERÇEK push ile ölçülür.

Bulgu 2026-08-07 (PR #17): worktree'den yapılan her push kapıda kaldı.
Sebep tek bir satır değil, bir SINIF: kapı, git'in kancaya miras bıraktığı
ortama (GIT_DIR) körü körüne güveniyor.

  1. `git rev-parse --show-toplevel` GIT_DIR mirası altında ya patlar
     ("fatal: this operation must be run in a work tree") ya da sessizce
     CWD'yi kök sanır. Patladığında ROOT boş kalır ve kapı
     `/bin/validate.py` arar → "KOSAMADI", çıkış 2.
  2. Patlamasa bile GIT_DIR alt süreçlere sızar: validate.py'nin koştuğu
     testler geçici depolarda `git add` yapar, miras GIT_DIR yüzünden 128
     alır → kapı "kernel dogrulamasi basarisiz" der. Oysa ihlal yok.

İkisi de kural ihlali OLMADAN push'u bloklar. Bloklanan kullanıcı
`--no-verify` alışkanlığı edinir; kapı o an kaybolur — kancanın kendi
yorumlarında uyardığı başarısızlık biçimi budur.

Ayrıca mirasın ÜÇÜNCÜ bir yüzü var ve bu bir güvenlik açığıdır: sahte bir
GIT_DIR, secret kapısının taradığı dosya kümesini daraltarak sızıntıyı
geçirebiliyordu (test_sahte_git_dir_secret_kapisini_daraltamaz).

Bu testler simülasyon değil: gerçek worktree kurar, gerçek `git push`
çalıştırır. Ortamı, argv'yi, cwd'yi ve stdin'i git'in kendisi verir.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_REL = ".agents/skills/security-review/scripts/scan_secrets.py"
PII_REL = ".agents/skills/security-review/scripts/scan_personal_data.py"
GECMIS_REL = ".agents/skills/security-review/scripts/scan_gecmis.py"
# Her kapı fail-closed: tarayıcı yoksa push engellenir. Üçü de kurulmalı,
# yoksa bu testler kapının doğru davranışına takılır.
TARAYICILAR = (SCAN_REL, PII_REL, GECMIS_REL)

# git'in kancaya miras bıraktığı, depo çözümlemesini YÖNLENDİREN değişkenler.
# Kapı bunları temizlemezse hem kendi kökünü hem alt süreçlerininkini
# kaybeder.
GIT_YONLENDIRME = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                   "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                   "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_PREFIX",
                   "GIT_NAMESPACE", "GIT_QUARANTINE_PATH")

# Sahte kernel doğrulayıcısı. İki şeyi RAPORLAR, hüküm vermez:
#   - argv[0] → kapının hangi kökü çözdüğü (yanlış ağaç sessizce geçemesin)
#   - GIT_* → alt sürece sızan git ortamı
VALIDATE_KAYNAK = """#!/usr/bin/env python3
import os, sys
print("AURAS_VALIDATE_YOLU=" + os.path.abspath(sys.argv[0]))
for ad in {yonlendirme!r}:
    print(ad + "=" + os.environ.get(ad, "<yok>"))
sys.exit({kod})
"""

# Gerçek desenli sahte token — tarayıcının yakalaması BEKLENEN girdi.
# Kanonik "EXAMPLE" anahtarları tarayıcı tarafından bilinçli elenir; onlarla
# kurulan bir istismar testi yeşil görünür ama hiçbir şey ölçmez.
YEM_TOKEN = "ghp_" + "0123456789abcdefghijABCDEFGHIJ0123"


def temiz_ortam():
    """Ortamdan git yönlendirmesini söker.

    Testin KENDİSİ bir pre-push kancası içinde koşuyor olabilir (validate.py
    tests/ dizinini kancadan çağırır). O zaman GIT_DIR miras alınır ve
    kurulum git komutları ölçülen hatayı değil, ortamın hatasını gösterir.
    """
    ortam = dict(os.environ)
    for ad in GIT_YONLENDIRME:
        ortam.pop(ad, None)
    return ortam


def depo_kur(kok, validate_kod=0, sizinti=None):
    """Kapının çalışması için gereken minimum dosya ağacını yazar."""
    os.makedirs(os.path.join(kok, "bin", "hooks"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "bin", "hooks", "pre-push"),
                 os.path.join(kok, "bin", "hooks", "pre-push"))
    with open(os.path.join(kok, "bin", "validate.py"), "w") as fh:
        fh.write(VALIDATE_KAYNAK.format(yonlendirme=list(GIT_YONLENDIRME),
                                        kod=validate_kod))
    for rel in TARAYICILAR:
        hedef = os.path.join(kok, rel)
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), hedef)
    with open(os.path.join(kok, "temiz.py"), "w") as fh:
        fh.write("x = 1\n")
    if sizinti:
        with open(os.path.join(kok, "sizinti.py"), "w") as fh:
            fh.write(f'TOKEN = "{sizinti}"\n')


def git_kur(ortam):
    """check=True + temiz ortamlı git koşucusu."""
    def g(*argv, **kw):
        return subprocess.run(["git", "-c", "user.email=t@example.com",
                               "-c", "user.name=t", *argv], check=True,
                              capture_output=True, env=ortam, **kw)
    return g


class PrePushWorktreeTest(unittest.TestCase):
    def kur(self, td, validate_kod=0):
        """Kancası kurulu bir depo + worktree + yerel bare uzak depo.

        Yerleşim `bin/install-hooks.sh` ile aynı: kanca ANA deponun
        .git/hooks'una KOPYALANIR. Worktree'ler o dizini paylaşır — kanca
        worktree'den push'ta da bu kopyadan koşar.
        """
        ana = os.path.join(td, "ana")
        depo_kur(ana, validate_kod=validate_kod)
        ortam = temiz_ortam()
        g = git_kur(ortam)
        g("init", "-q", "-b", "main", ana)
        g("-C", ana, "add", "-A")
        g("-C", ana, "commit", "-qm", "init")
        shutil.copy2(os.path.join(ROOT, "bin", "hooks", "pre-push"),
                     os.path.join(ana, ".git", "hooks", "pre-push"))
        os.chmod(os.path.join(ana, ".git", "hooks", "pre-push"), 0o755)
        uzak = os.path.join(td, "uzak.git")
        g("init", "-q", "--bare", uzak)
        wt = os.path.join(td, "wt")
        g("-C", ana, "worktree", "add", "-q", "-b", "dal", wt)
        return wt, uzak, ortam

    def push(self, td, validate_kod=0):
        wt, uzak, ortam = self.kur(td, validate_kod=validate_kod)
        p = subprocess.run(["git", "push", uzak, "dal"], cwd=wt, env=ortam,
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr, wt

    def test_worktreeden_push_kapiyi_kosturur(self):
        """Kapı worktree'den de koşar ve kendi kökünü doğru çözer.

        Kök, push edilen ağaçtır — yani WORKTREE'nin çalışma dizini. Ana
        deponun kökü değil: o an başka bir dal duruyor olabilir, o ağacı
        doğrulamak yanlış şeyi ölçmektir. (`$0`'dan türetmek — kanca ana
        deponun .git/hooks'unda durduğu için — tam bu hatayı yapar.)
        """
        with tempfile.TemporaryDirectory() as td:
            kod, cikti, wt = self.push(td)
            self.assertNotIn("/bin/validate.py': [Errno 2]", cikti,
                             "ROOT boş çözüldü — kapı '/bin/validate.py' arıyor")
            self.assertEqual(kod, 0, f"worktree push'u kural ihlali olmadan "
                                     f"bloklandı:\n{cikti}")
            beklenen = os.path.join(os.path.realpath(wt), "bin", "validate.py")
            self.assertIn(f"AURAS_VALIDATE_YOLU={beklenen}", cikti,
                          "kapı yanlış ağacı doğruladı")

    def test_git_ortami_alt_sureclere_sizmaz(self):
        """git'in kancaya verdiği GIT_DIR, kapının araçlarına geçmemeli.

        Sızarsa doğrulayıcının kendi git işleri (geçici depoda `git add`,
        `git ls-files`) miras alınan depoya yönelir ve 128 döner. Kapı bunu
        "kernel dogrulamasi basarisiz" diye okur — olmayan bir ihlal.
        """
        with tempfile.TemporaryDirectory() as td:
            kod, cikti, _ = self.push(td)
            for ad in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
                self.assertIn(f"{ad}=<yok>", cikti,
                              f"{ad} alt sürece sızdı — kapının araçları "
                              f"yanlış depoya bakar")
            self.assertEqual(kod, 0, cikti)

    def test_worktreede_ihlal_hala_bloklar(self):
        """Negatif kontrol: kök düzeldi diye kapı gevşemesin."""
        with tempfile.TemporaryDirectory() as td:
            kod, cikti, _ = self.push(td, validate_kod=1)
            self.assertNotEqual(kod, 0, "ihlal worktree'den push'ta geçti")
            self.assertIn("dogrulamasi basarisiz", cikti)


class OrtamMirasiTest(unittest.TestCase):
    """Ortamdan gelen git yönlendirmesi kapıyı yönetemez."""

    def hazirla(self, td, sizinti=None):
        depo = os.path.join(td, "depo")
        os.makedirs(depo)
        depo_kur(depo, sizinti=sizinti)
        ortam = temiz_ortam()
        g = git_kur(ortam)
        g("init", "-q", "-b", "main", depo)
        g("-C", depo, "add", "-A")
        return depo, ortam, g

    def kosur(self, depo, ortam, cwd=None):
        p = subprocess.run(
            ["sh", os.path.join(depo, "bin", "hooks", "pre-push")],
            cwd=cwd or depo, env=ortam, capture_output=True, text=True,
            timeout=60, input="")
        return p.returncode, p.stdout + p.stderr

    def test_bozuk_git_ortami_kapiyi_kor_etmez(self):
        """Bildirilen belirtinin birebir üretimi.

        Work-tree'si olmayan bir depoya işaret eden GIT_DIR mirası altında
        `--show-toplevel` "fatal: this operation must be run in a work tree"
        verir, ROOT boş kalır, kapı `/bin/validate.py` arar ve "KOSAMADI"
        der — kural ihlali olmadan.
        """
        with tempfile.TemporaryDirectory() as td:
            depo, ortam, g = self.hazirla(td)
            bare = os.path.join(td, "bare.git")
            g("init", "-q", "--bare", bare)
            ortam["GIT_DIR"] = bare
            kod, cikti = self.kosur(depo, ortam)
            self.assertNotIn("'/bin/validate.py'", cikti,
                             "ROOT boş kaldı — kapı kök dizinde araç arıyor")
            self.assertEqual(kod, 0, f"kural ihlali yokken bloklandı:\n{cikti}")
            beklenen = os.path.join(os.path.realpath(depo), "bin",
                                    "validate.py")
            self.assertIn(f"AURAS_VALIDATE_YOLU={beklenen}", cikti)

    def test_sahte_git_dir_secret_kapisini_daraltamaz(self):
        """Denetim bulgusu 2026-08-07 — secret kapısı BYPASS'ı.

        Secret taraması `--git` modunda `git ls-files` ile kapsamını
        belirler. Ortamdan gelen GIT_DIR o listeyi BAŞKA bir deponun
        index'inden okuttuğu için kapsam, saldırganın seçtiği kümeye
        daralıyordu.

        İstismar: `GIT_DIR=<tek dosyalık temiz depo> git push` — tarayıcı
        "1 dosya tarandı, temiz ✓" der, çıkış 0, token uzak depoya gider.
        Ölçülen (eski kanca): kontrolde çıkış 1, saldırıda çıkış 0.
        Sızan secret geri alınamaz; bu yüzden şiddet HIGH.
        """
        with tempfile.TemporaryDirectory() as td:
            depo, ortam, g = self.hazirla(td, sizinti=YEM_TOKEN)
            # Yem: yalnız 'temiz.py' izleyen ayrı bir depo
            yem = os.path.join(td, "yem")
            os.makedirs(yem)
            with open(os.path.join(yem, "temiz.py"), "w") as fh:
                fh.write("x = 1\n")
            g("init", "-q", "-b", "main", yem)
            g("-C", yem, "add", "-A")

            kod, cikti = self.kosur(depo, dict(ortam))
            self.assertEqual(kod, 1, "kontrol: secret zaten yakalanmalıydı")

            ortam["GIT_DIR"] = os.path.join(yem, ".git")
            kod, cikti = self.kosur(depo, ortam)
            self.assertEqual(kod, 1,
                             f"sahte GIT_DIR secret kapısını atlattı:\n{cikti}")
            self.assertIn("secret kapisi gecilemedi", cikti)

    def test_yedek_kok_sessiz_kullanilmaz(self):
        """`$0` yedek yolu kapının kendisi hakkında yalan söyleyebildiği yer.

        Keşif hiç çalışmazsa kapı kökü kanca konumundan türetir. O kök, push
        edilen ağaç OLMAYABİLİR (kurulu kanca ana deponun .git/hooks'unda
        durur; worktree'nin ağacı başkadır). Yanlış ağacı tarayan secret
        kapısı "temiz" der — kanıt gibi görünen bir hiçlik.

        Yedek yolu bloklamak kapıyı duvara çevirirdi (bu işin çıkış noktası
        tam olarak buydu). O yüzden kural: kullanılabilir ama SESSİZ olamaz,
        ve ağaç ayrışması ayrıca söylenmeli.
        """
        with tempfile.TemporaryDirectory() as td:
            depo, ortam, _ = self.hazirla(td)
            disari = os.path.join(td, "disari")   # git deposu DEĞİL
            os.makedirs(disari)
            kod, cikti = self.kosur(depo, ortam, cwd=disari)
            self.assertIn("UYARI", cikti, "yedek kök sessizce kullanıldı")
            self.assertIn("DIKKAT", cikti,
                          "ağaç ayrışması söylenmedi — 'temiz' yanlış "
                          "güven üretir")
            self.assertIn(os.path.realpath(disari), cikti,
                          "hangi dizinle ayrıştığı söylenmeli")


if __name__ == "__main__":
    unittest.main()
