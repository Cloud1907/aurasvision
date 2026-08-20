#!/usr/bin/env python3
"""Kişisel veri kapısı — sır taramasından AYRI bir boyut.

Sır tarayıcısı "bu değer bir anahtar mı" diye sorar; bu tarayıcı "bu dosya
bir insan listesi mi" diye sorar. Üretimde iki ayrı script (scan_secrets.py /
scan_personal_data.py); testleri de ayrı durur — tek dosyada birikirse hangi
kapının neyi garanti ettiği okunmaz hâle gelir.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PII = os.path.join(ROOT, ".agents", "skills", "security-review",
                   "scripts", "scan_personal_data.py")


def kos(script, *arg):
    p = subprocess.run([sys.executable, script, *arg],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    return p.returncode, p.stdout + p.stderr


class MuafiyetKapsamiTest(unittest.TestCase):
    """Bir kapının muafiyeti BAŞKA kapıyı susturmamalı.

    Denetim bulgusu (2026-08-08, security-review): muafiyet dosyası iki kapı
    arasında ortaktı. `siparisler.json  # sir taramasi icin muaf` satırı
    kişisel veri kapısını da kapatıyordu — yazan kişi ikinci kapıyı
    kapattığını bilmeden. Gerekçe yanlış kapıyı tarif ediyordu.

    Yeni sözleşme: işaretsiz satır YALNIZ secret kapısına uygulanır (mevcut
    tüm muafiyetler onun için yazılmıştı — geriye dönük doğru). Başka kapı
    için `# kapı: pii` ya da `# kapı: hepsi` AÇIKÇA yazılır.
    """

    def kur(self, td, muafiyet):
        os.makedirs(os.path.join(td, ".agents"), exist_ok=True)
        with open(os.path.join(td, ".agents", "secret-allowlist.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(muafiyet)
        with open(os.path.join(td, "dump.json"), "w", encoding="utf-8") as fh:
            fh.write("[" + ",".join(
                f'{{"email":"k{i}@sirket.com.tr"}}' for i in range(20)) + "]")
        with open(os.path.join(td, "temiz.py"), "w") as fh:
            fh.write("x = 1\n")
        return td

    def test_secret_muafiyeti_pii_kapisini_susturmaz(self):
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "dump.json  # sir taramasi icin muaf\n")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 1,
                             f"secret muafiyeti PII kapısını kapatmamalı:\n{cikti}")

    def test_pii_isaretli_muafiyet_calisir(self):
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "dump.json  # kapı: pii — bilinçli demo verisi\n")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 0, cikti)
            self.assertIn("muaf:", cikti, "bastırılan bulgu görünür kalmalı")

    def test_hepsi_isareti_iki_kapiyi_da_kapatir(self):
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "dump.json  # kapı: hepsi — bilinçli demo verisi\n")
            self.assertEqual(kos(PII, td)[0], 0)

    def test_gerekce_hala_zorunlu(self):
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "dump.json  # kapı: pii\n")   # gerekçe yok
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 2, cikti)
            self.assertIn("gerekçe", cikti.lower())


class TcSaglamaTest(unittest.TestCase):
    """11 hane olmak TC kimlik yapmaz — sağlama yapar.

    Denetim bulgusu (2026-08-08, security-review): 30 sipariş numarası
    içeren sıradan bir seed dosyası "30 benzersiz TC kimlik no" diye
    bloklandı. Yanlış pozitif bir kapının en pahalı hatasıdır: birkaç kez
    tekrarlarsa insan kapıyı atlamayı öğrenir.

    TC kimlik no'nun kendi sağlama algoritması var; rastgele 11 hanelinin
    ~%99'unu eler. Kullanmamak bilinçli bir karardı ve yanlıştı.
    """

    def kur(self, td, satirlar, ad="veri.txt"):
        with open(os.path.join(td, ad), "w", encoding="utf-8") as fh:
            fh.write("\n".join(str(x) for x in satirlar))
        with open(os.path.join(td, "temiz.py"), "w") as fh:
            fh.write("x = 1\n")
        return td

    def test_is_kimlikleri_yanlis_pozitif_uretmez(self):
        # Sipariş no / barkod / hesap no: 11 hane ama TC değil.
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, [10000000000 + i * 137 for i in range(30)],
                     "siparisler.json")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 0, f"iş kimliği TC sanılmamalı:\n{cikti}")

    def test_gecerli_tc_hala_yakalanir(self):
        # Sağlaması tutan sahte kimlikler — isabet düşmemeli.
        import importlib.util
        spec = importlib.util.spec_from_file_location("_pii", PII)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        gecerli = []
        n = 10000000000
        while len(gecerli) < 10:
            if mod.tc_gecerli(str(n)):
                gecerli.append(n)
            n += 1
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, gecerli, "kimlikler.csv")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 1, f"geçerli TC yakalanmalı:\n{cikti}")
            self.assertIn("TC kimlik", cikti)

    def test_saglama_kurallari(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_pii2", PII)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertFalse(mod.tc_gecerli("01234567890"), "0 ile başlayamaz")
        self.assertFalse(mod.tc_gecerli("1234567890"), "10 hane geçersiz")
        self.assertFalse(mod.tc_gecerli("11111111111"), "sağlama tutmuyor")


class KisiselVeriTest(unittest.TestCase):
    """Toplu kişisel veri dökümü — sır değil ama repoda durmamalı.

    4Flow'da bulundu (2026-08-07): `users_list.json`, bir üretim API
    çıktısının dosyaya dökülmüş hâli — 20 kişinin adı, soyadı ve kurumsal
    e-postası. Tarayıcı "temiz" dedi ve DOĞRU davrandı: parola/anahtar
    arıyordu, kişisel veri aramıyordu. Yani kapıda bu boyut hiç yoktu.

    Ölçüt TEK e-posta değil TOPLU dökümdür: bir yorumdaki iletişim adresi
    ihlal değil, 20 kişilik liste dökümüdür. Tek adres eşiği yanlış pozitif
    üretir ve kapıyı güvenilmez yapar.
    """

    def kur(self, td, icerik, ad="dump.json"):
        with open(os.path.join(td, ad), "w", encoding="utf-8") as fh:
            fh.write(icerik)
        with open(os.path.join(td, "temiz.py"), "w") as fh:
            fh.write("x = 1\n")
        return td

    def test_toplu_eposta_dokumu_yakalanir(self):
        with tempfile.TemporaryDirectory() as td:
            kisiler = ", ".join(
                f'{{"email":"kisi{i}@sirket.com.tr","fullName":"Kisi {i}"}}'
                for i in range(20))
            self.kur(td, "[" + kisiler + "]")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 1, cikti)
            self.assertIn("dump.json", cikti)
            self.assertIn("kişisel veri", cikti)

    def test_tek_eposta_yanlis_pozitif_uretmez(self):
        # Bir yorumdaki iletişim adresi ihlal değildir.
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "# soru olursa: destek@sirket.com\n", "not.md")
            self.assertEqual(kos(PII, td)[0], 0)

    def test_bir_avuc_eposta_yanlis_pozitif_uretmez(self):
        # Eşiğin altı: CODEOWNERS/yazar listesi gibi meşru küçük kümeler.
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "\n".join(f"a{i}@x.com" for i in range(4)), "not.md")
            self.assertEqual(kos(PII, td)[0], 0)

    def test_katki_dosyalari_muaf(self):
        # AUTHORS/CONTRIBUTORS listesi TANIMI GEREĞİ kişi listesidir.
        with tempfile.TemporaryDirectory() as td:
            self.kur(td, "\n".join(f"Kisi {i} <k{i}@x.com>" for i in range(20)),
                     "AUTHORS")
            self.assertEqual(kos(PII, td)[0], 0)

    def test_toplu_tc_kimlik_yakalanir(self):
        with tempfile.TemporaryDirectory() as td:
            # Sağlaması TUTAN sahte kimlikler. Rastgele 11 hane artık
            # yeterli değil — o vaka test_is_kimlikleri_yanlis_pozitif_uretmez
            # tarafından "yakalanmamalı" diye kilitleniyor.
            import importlib.util
            spec = importlib.util.spec_from_file_location("_p", PII)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            gecerli, n = [], 10000000000
            while len(gecerli) < 12:
                if mod.tc_gecerli(str(n)):
                    gecerli.append(str(n))
                n += 1
            self.kur(td, "\n".join(gecerli), "kimlikler.csv")
            kod, cikti = kos(PII, td)
            self.assertEqual(kod, 1, cikti)
            self.assertIn("kişisel veri", cikti)


if __name__ == "__main__":
    unittest.main()
