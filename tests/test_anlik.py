#!/usr/bin/env python3
"""Tur başı anlık görüntüsü — kapı gerçek çalışma ağacı farkına bakmalı.

Neden: kapı "bu turda ne değişti" sorusunu TOOL OLAYLARINDAN çıkarıyordu ve
edit olayı yalnız `Edit|Write|NotebookEdit` matcher'ından geliyordu
(`.claude/settings.json`). Kabuk üzerinden yazım — `sed -i`, `>` yönlendirmesi,
`python3 -c "open(...,'w')"`, `tee`, `patch` — HİÇBİR edit olayı üretmez.
Yani kaynak değişir, kapı görmez: test yükümlülüğü, risk yüzeyi incelemesi ve
tıklama kanıtı hiç doğmaz (bağımsız incelemenin bulgusu, 2026-08-15).

Karşı-tuzak da gerçek: `git diff HEAD` kullanıcının KENDİ commit'lenmemiş
işini de görür. Ajanın hiç dokunmadığı bir dosya için test istenirse kullanıcı
kapıyı baştan yok saymayı öğrenir — bu sistemin en korktuğu şey. Bu yüzden
ölçü mutlak kirlilik değil, TUR BAŞINA GÖRE DELTA'dır.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


anlik = _load("anlik")


def _git(kok, *args):
    subprocess.run(["git", *args], cwd=kok, capture_output=True, check=False)


class AnlikTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.kok = self._tmp.name
        _git(self.kok, "init", "-b", "main", "-q")
        _git(self.kok, "config", "user.email", "t@example.com")
        _git(self.kok, "config", "user.name", "t")
        self.yaz("src/app.py", "print(1)\n")
        _git(self.kok, "add", "-A")
        _git(self.kok, "commit", "-qm", "ilk")

    def tearDown(self):
        self._tmp.cleanup()

    def yaz(self, rel, icerik):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as fh:
            fh.write(icerik)
        return yol

    # --- asıl delik: kabuk üzerinden yazım ---

    def test_kabuk_yazimi_gorunur(self):
        """`sed -i` benzeri yazım tur başı anlığına göre DEĞİŞMİŞ sayılır."""
        onceki = anlik.al(self.kok)
        self.yaz("src/app.py", "print(2)\n")     # tool olayı YOK
        self.assertIn("src/app.py", anlik.degisenler(self.kok, onceki))

    def test_yeni_dosya_gorunur(self):
        onceki = anlik.al(self.kok)
        self.yaz("src/yeni.py", "x = 1\n")
        self.assertIn("src/yeni.py", anlik.degisenler(self.kok, onceki))

    def test_silinen_dosya_gorunur(self):
        onceki = anlik.al(self.kok)
        os.remove(os.path.join(self.kok, "src/app.py"))
        self.assertIn("src/app.py", anlik.degisenler(self.kok, onceki))

    # --- karşı-tuzak: kullanıcının önceden kirli işi ---

    def test_onceden_kirli_dosya_yukumluluk_dogurmaz(self):
        """Tur başlamadan kirli olan ve turda DOKUNULMAYAN dosya sayılmaz."""
        self.yaz("src/app.py", "print(999)\n")   # kullanıcının kendi işi
        onceki = anlik.al(self.kok)              # tur BURADA başlıyor
        self.assertEqual(anlik.degisenler(self.kok, onceki), [])

    def test_onceden_kirli_dosya_turda_degisirse_sayilir(self):
        """Kirli dosyaya turda dokunulursa yükümlülük DOĞAR."""
        self.yaz("src/app.py", "print(999)\n")
        onceki = anlik.al(self.kok)
        self.yaz("src/app.py", "print(1000)\n")
        self.assertIn("src/app.py", anlik.degisenler(self.kok, onceki))

    def test_hicbir_sey_degismezse_bos(self):
        onceki = anlik.al(self.kok)
        self.assertEqual(anlik.degisenler(self.kok, onceki), [])

    # --- dayanıklılık: kapı çökmemeli ---

    def test_git_disinda_bos_doner(self):
        """Git deposu olmayan dizinde anlık boş döner, patlamaz."""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(anlik.al(d), {})
            self.assertEqual(anlik.degisenler(d, {}), [])

    def test_anlik_diske_yazilip_okunur(self):
        onceki = anlik.al(self.kok)
        self.yaz("src/app.py", "print(3)\n")
        yol = anlik.kaydet(self.kok, "SESS1234", onceki)
        self.assertTrue(os.path.isfile(yol))
        geri = anlik.getir(self.kok, "SESS1234")
        self.assertEqual(geri, onceki)
        self.assertIn("src/app.py", anlik.degisenler(self.kok, geri))

    def test_anlik_yoksa_none_doner(self):
        """Anlık yoksa kapı ESKİ davranışa düşer, uydurma delta üretmez."""
        self.assertIsNone(anlik.getir(self.kok, "YOKBOYLE"))


if __name__ == "__main__":
    unittest.main()
