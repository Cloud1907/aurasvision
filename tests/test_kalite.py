#!/usr/bin/env python3
"""Kalite ölçümü + ratchet — sayan şeyin kendisi de sayılabilir olmalı.

Ölçüm kapıya bağlı olduğu için sessizce bozulması sahte yeşil üretir:
"0 bulgu" ile "hiç ölçmedim" ayırt edilemez hâle gelir.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARAC = os.path.join(ROOT, "bin", "kalite.py")

spec = importlib.util.spec_from_file_location("_kalite", ARAC)
kalite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kalite)


def yaz(kok, rel, icerik):
    yol = os.path.join(kok, rel)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as fh:
        fh.write(icerik)


class OlcumTest(unittest.TestCase):
    def test_uzun_fonksiyon_sayilir(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.py", "def uzun():\n" + "    x = 1\n" * 60)
            r = kalite.olc(td)
            self.assertEqual(r["sayaclar"]["uzun_fonksiyon"], 1)

    def test_ic_ice_calisma_agaci_sayilmaz(self):
        """Repo içine açılan worktree/klon bu projenin borcu değildir.

        2026-08-07 vakası: arka plan görevi `.claude/worktrees/<ad>/`
        altına worktree açtı, kalite taraması onu da gezdi ve HER sayaç
        tam iki katına çıktı (28 dosya → 56). Ratchet gerçek borç büyümüş
        sanıp kırmızı yandı, merge bloklandı. `.git` adı ATLA listesinde
        vardı ama worktree'de `.git` bir DOSYA (gitdir işaretçisi).
        """
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.py", "def uzun():\n" + "    x = 1\n" * 60)
            # Kendi .git'i olan alt dizin — worktree biçimi (dosya)
            yaz(td, "wt/a.py", "def uzun():\n" + "    x = 1\n" * 60)
            yaz(td, "wt/.git", "gitdir: /baska/yer/.git/worktrees/wt\n")
            # Klon biçimi (dizin) de aynı kuralla dışlanmalı
            yaz(td, "klon/a.py", "def uzun():\n" + "    x = 1\n" * 60)
            os.makedirs(os.path.join(td, "klon", ".git"))
            r = kalite.olc(td)
            self.assertEqual(r["sayaclar"]["uzun_fonksiyon"], 1,
                             "iç içe çalışma ağaçları sayıma girmemeli")
            self.assertEqual(r["kapsam"]["kod_dosyasi"], 1)

    def test_kisa_fonksiyon_sayilmaz(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.py", "def kisa():\n    return 1\n")
            self.assertEqual(kalite.olc(td)["sayaclar"]["uzun_fonksiyon"], 0)

    def test_buyuk_dosya_sayilir(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.py", "x = 1\n" * 500)
            self.assertEqual(kalite.olc(td)["sayaclar"]["buyuk_dosya"], 1)

    def test_karmasik_fonksiyon_sayilir(self):
        with tempfile.TemporaryDirectory() as td:
            govde = "".join(f"    if x == {i}:\n        pass\n" for i in range(12))
            yaz(td, "a.py", "def dallı(x):\n" + govde)
            self.assertEqual(kalite.olc(td)["sayaclar"]["karmasik_fonksiyon"], 1)

    def test_borc_ve_debug_sayilir(self):
        # Fixture parçalı kurulur: düz yazılırsa bu test dosyası repo
        # sayacına gerçek borçmuş gibi girer (araç kendi testini sayar).
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.js", "// TO" + "DO: sonra\n" + "console" + ".log(x)\n")
            s = kalite.olc(td)["sayaclar"]
            self.assertEqual(s["borc_isareti"], 1)
            self.assertEqual(s["debug_artigi"], 1)

    def test_js_fonksiyonu_analiz_edilir(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.js", "function uzun() {\n" + "  var x = 1;\n" * 60 + "}\n")
            r = kalite.olc(td)
            self.assertEqual(r["sayaclar"]["uzun_fonksiyon"], 1)
            self.assertEqual(r["kapsam"]["fonksiyon_analizli"], 1)

    def test_kapsam_durust_raporlanir(self):
        # Fonksiyon analizi yapılamayan dil "analiz edildi" sayılmamalı
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.rb", "def x\nend\n")
            k = kalite.olc(td)["kapsam"]
            self.assertEqual(k["kod_dosyasi"], 1)
            self.assertEqual(k["fonksiyon_analizli"], 0)
            self.assertEqual(k["yalniz_satir_sayilan"], 1)

    def test_atlanan_dizin_olculmez(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "node_modules/b.js", "x = 1\n" * 500)
            self.assertEqual(kalite.olc(td)["kapsam"]["kod_dosyasi"], 0)

    def test_kendi_desenini_yakalamaz(self):
        # Tarayıcı kendi kaynağında debug artığı görmemeli (parçalı desen)
        r = kalite.olc(ROOT)
        kendi = [b for b in r["bulgular"]
                 if b["dosya"] == os.path.join("bin", "kalite.py")]
        self.assertEqual([b for b in kendi if b["tur"] == "debug_artigi"], [],
                         "araç kendi desenini bulgu sayıyor")


class RatchetTest(unittest.TestCase):
    def test_artan_sayac_regresyondur(self):
        self.assertEqual(
            kalite.regresyonlar({"a": 3, "b": 1}, {"a": 2, "b": 1}),
            [("a", 2, 3)])

    def test_azalan_sayac_regresyon_degildir(self):
        self.assertEqual(kalite.regresyonlar({"a": 1}, {"a": 5}), [])

    def test_tabanda_olmayan_sayac_sifir_sayilir(self):
        self.assertEqual(kalite.regresyonlar({"yeni": 1}, {}), [("yeni", 0, 1)])

    def test_check_regresyonda_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "a.py", "x = 1\n" * 500)
            taban = os.path.join(td, "taban.json")
            with open(taban, "w") as fh:
                json.dump({"sayaclar": {"buyuk_dosya": 0}}, fh)
            eski = kalite.TABAN_YOL
            try:
                kalite.TABAN_YOL = taban
                self.assertEqual(kalite.main(["--check", "--json",
                                              "--path", td]), 1)
            finally:
                kalite.TABAN_YOL = eski


class SozlesmeTest(unittest.TestCase):
    def test_json_beklenen_alanlari_uretir(self):
        p = subprocess.run([sys.executable, ARAC, "--json"],
                           capture_output=True, text=True, cwd=ROOT,
                           timeout=120, input="")
        veri = json.loads(p.stdout)
        for alan in ("sayaclar", "esikler", "kapsam", "bulgular"):
            self.assertIn(alan, veri)

    def test_taban_dosyasi_var_ve_gecerli(self):
        # Taban yoksa ratchet sessizce kapalıdır — kapı var sanılır, yoktur
        yol = os.path.join(ROOT, ".agents", "kalite-baseline.json")
        self.assertTrue(os.path.isfile(yol), "ratchet tabanı yok")
        with open(yol, encoding="utf-8") as fh:
            veri = json.load(fh)
        self.assertIn("sayaclar", veri)
        self.assertIn("buyuklukler", veri,
                      "taban ihlal BÜYÜKLÜKLERİNİ taşımıyor — mevcut borcun "
                      "büyümesi ölçülemez (M10)")


class BuyumeRatchetTest(unittest.TestCase):
    """Ratchet borcun SAYISINI değil BÜYÜKLÜĞÜNÜ de izlemeli.

    H. Demir denetimi (2026-08-15): `validate.py` ADR-0004 zamanında 601
    satırdı, ölçüm günü 952 — %58 büyüme. `buyuk_dosya` sayacı hep 1 kaldığı
    için kapı hiç kırmızı yanmadı. "Mevcut borç kabul, büyümesi bloklanır"
    iddiası borcun büyüklüğü için hiç çalışmıyordu.
    """

    def test_ayni_ihlal_buyurse_yakalanir(self):
        taban = {"bin/x.py#buyuk_dosya": 601}
        simdi = {"bin/x.py#buyuk_dosya": 952}
        self.assertEqual(kalite.buyumeler(simdi, taban),
                         [("bin/x.py#buyuk_dosya", 601, 952)])

    def test_kuculuyorsa_yakalanmaz(self):
        """Borcu azaltmak serbest ve teşvik edilir."""
        self.assertEqual(
            kalite.buyumeler({"a#buyuk_dosya": 500}, {"a#buyuk_dosya": 601}),
            [])

    def test_ayni_kalirsa_yakalanmaz(self):
        self.assertEqual(
            kalite.buyumeler({"a#buyuk_dosya": 601}, {"a#buyuk_dosya": 601}),
            [])

    def test_yeni_ihlal_burada_degil_sayacta_yakalanir(self):
        """İş bölümü: yeni ihlal sayaç kapısının, büyüme bunun."""
        self.assertEqual(kalite.buyumeler({"yeni#buyuk_dosya": 900}, {}), [])

    def test_eski_taban_bicimi_sessizce_gecmez(self):
        """Taban 'buyuklukler' taşımıyorsa boş döner — ama main UYARIR."""
        self.assertEqual(kalite.buyumeler({"a#x": 9}, None), [])

    def test_kimlik_satir_numarasi_tasimaz(self):
        """Fonksiyon birkaç satır kayınca sahte 'yeni ihlal' doğmamalı."""
        b = kalite.buyuklukler([("bin/a.py", 40, "uzun_fonksiyon", "", 60),
                                ("bin/a.py", 91, "uzun_fonksiyon", "", 55)])
        self.assertEqual(b, {"bin/a.py#uzun_fonksiyon": 60})


if __name__ == "__main__":
    unittest.main()
