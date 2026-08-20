#!/usr/bin/env python3
"""install-hooks.sh — kapı NEREYE kurulur, git'in gerçekten baktığı yere mi.

Kurulum yanlış dizine yazarsa kapı "kuruldu" der ama hiç koşmaz: koruma
illüzyonu, kapının kendisinin olmamasından beterdir. Bu testler kurulum
hedefini kilitler.
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GIT_YONLENDIRME = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                   "GIT_COMMON_DIR", "GIT_PREFIX")


def temiz_ortam():
    ortam = dict(os.environ)
    for ad in GIT_YONLENDIRME:
        ortam.pop(ad, None)
    return ortam


class InstallHooksTest(unittest.TestCase):
    def kur_depo(self, td, hooks_path=None):
        """Kurulum script'i ve kancası olan gerçek bir depo döndürür."""
        ana = os.path.join(td, "ana")
        os.makedirs(os.path.join(ana, "bin", "hooks"))
        for rel in ("bin/install-hooks.sh", "bin/hooks/pre-push"):
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(ana, rel))
        ortam = temiz_ortam()

        def g(*argv, **kw):
            return subprocess.run(["git", "-c", "user.email=t@example.com",
                                   "-c", "user.name=t", *argv], check=True,
                                  capture_output=True, env=ortam, **kw)

        g("init", "-q", "-b", "main", ana)
        if hooks_path:
            g("-C", ana, "config", "core.hooksPath", hooks_path)
        g("-C", ana, "add", "-A")
        g("-C", ana, "commit", "-qm", "init")
        return ana, ortam, g

    def calistir(self, cwd, ortam):
        p = subprocess.run(["bash", "bin/install-hooks.sh"], cwd=cwd,
                           env=ortam, capture_output=True, text=True,
                           timeout=60)
        return p.returncode, p.stdout + p.stderr

    def kurulu_mu(self, yol):
        self.assertTrue(os.path.isfile(yol), f"kanca kurulmadı: {yol}")
        mod = os.stat(yol).st_mode
        self.assertTrue(mod & stat.S_IXUSR, f"kanca çalıştırılabilir değil: {yol}")

    def test_ana_depoya_kurar(self):
        with tempfile.TemporaryDirectory() as td:
            ana, ortam, _ = self.kur_depo(td)
            kod, cikti = self.calistir(ana, ortam)
            self.assertEqual(kod, 0, cikti)
            self.kurulu_mu(os.path.join(ana, ".git", "hooks", "pre-push"))

    def test_worktreeden_de_kurar(self):
        """Bulgu 2026-08-07: worktree'de `.git` bir DOSYADIR.

        Kurulum hedefi "$ROOT/.git/hooks" diye sabit yazılırsa worktree'den
        koşan kurulum çöker — kapı kurulamaz. Kancalar zaten worktree'ye
        değil, ana deponun ORTAK dizinine kurulur; worktree'ler onu paylaşır.
        """
        with tempfile.TemporaryDirectory() as td:
            ana, ortam, g = self.kur_depo(td)
            wt = os.path.join(td, "wt")
            g("-C", ana, "worktree", "add", "-q", "-b", "dal", wt)
            kod, cikti = self.calistir(wt, ortam)
            self.assertEqual(kod, 0, f"worktree'den kurulum çöktü:\n{cikti}")
            self.kurulu_mu(os.path.join(ana, ".git", "hooks", "pre-push"))

    def test_core_hookspath_onurlandirilir(self):
        """core.hooksPath varsa git .git/hooks'a BAKMAZ.

        Oraya kurmak sessiz bir hiçliktir: script "kuruldu" der, kapı hiç
        koşmaz. Kurulumun söylediği yer, git'in okuduğu yer olmalı.
        """
        with tempfile.TemporaryDirectory() as td:
            ozel = os.path.join(td, "ozel-hooks")
            ana, ortam, _ = self.kur_depo(td, hooks_path=ozel)
            kod, cikti = self.calistir(ana, ortam)
            self.assertEqual(kod, 0, cikti)
            self.kurulu_mu(os.path.join(ozel, "pre-push"))
            self.assertIn(ozel, cikti,
                          "kurulum hedefi çıktıda görünmeli — kullanıcı "
                          "kapının nereye kurulduğunu bilmeli")


if __name__ == "__main__":
    unittest.main()
