#!/usr/bin/env python3
"""Kapsam bekçisi — keşfe girmeyen test dosyası sessiz kapsam kaybıdır.

Bu bekçi beş inceleme turunda beş kez sızdırdı ve her seferinde kaçak bir
METİN DESENİ varsayımından geldi. Buradaki her test o turlardan birini
kilitler; hepsi düzeltmeden ÖNCE kırmızıydı.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import kapsam_bekcisi as kd  # noqa: E402


def yaz(kok, rel, icerik):
    yol = os.path.join(kok, rel)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as fh:
        fh.write(icerik)


class TekModulImportTest(unittest.TestCase):
    """`python3 -m unittest tests.test_x` de çalışmalı — yalnız keşif değil.

    Keşif `tests/`i sys.path'e koyar; noktalı çağrı KOYMAZ. Paylaşılan
    yardımcıyı (`ortam.py`) yol kurmadan import eden modül yalnız keşifle
    koşar, tek modül çağrısında `ModuleNotFoundError: No module named 'ortam'`
    verir. Bu kapsam kaybı değildir ama aynı aileden bir yanıltmadır: okuyan
    "test bozuk" sanar ve kırmızıya güvenmemeyi öğrenir.

    Ölçüm 2026-08-09: `ortam.py` paylaşılan yardımcıya dönüştükten sonra dört
    modül bu hâle düşmüştü ve süit yeşil olduğu için kimse görmedi.
    """

    def test_her_test_modulu_tek_basina_import_edilebilir(self):
        # HER MODÜL KENDİ SÜRECİNDE. Tek süreçte toplu import etmek bekçiyi
        # yalancı yapar (Codex bulgusu, PR #35): önce import edilen modülün
        # `sys.path.insert`i süreç boyunca kalır ve yolu EKSİK olan sonraki
        # modül de import edilebilir görünür. Ölçüldü — test_route'un yol
        # eklemesi silindiğinde modül gerçekten kırıktı ama bekçi "OK" dedi.
        #
        # `sys.path`i geri almak yetmez: ilk başarılı import'tan sonra `ortam`
        # `sys.modules`ta önbelleklenir ve sonraki modül yolu hiç kullanmadan
        # onu bulur. Tek dürüst izolasyon ayrı süreçtir.
        hatali = []
        for m in sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "tests"))
                        if f.startswith("test_") and f.endswith(".py")):
            p = subprocess.run([sys.executable, "-c", f"import tests.{m}"],
                               capture_output=True, text=True, cwd=ROOT)
            if p.returncode != 0:
                son = (p.stderr.strip().splitlines() or ["<çıktı yok>"])[-1]
                hatali.append(f"{m} → {son}")
        self.assertEqual(
            hatali, [],
            "tek modül çağrısında import edilemeyen test dosyası var; "
            "paylaşılan yardımcıdan önce tests/ dizinini sys.path'e ekle:\n  "
            + "\n  ".join(hatali))


class ModulAtlamaHukmuTest(unittest.TestCase):
    """Modül düzeyinde atlama, ortam kaydıyla DOĞRULANMADAN meşru sayılamaz.

    Codex bağımsız incelemesi (PR #47, P1): bekçi çökme ile görünür atlamayı
    ayırdı ama atlamanın gerekçesini hiç sınamadı. Modül başına yazılan tek
    bir `raise unittest.SkipTest("...")` testleri süitten çıkarıyor, bekçi
    bunu ortam bağımlılığı sanıyordu. Beyan kanıt değildir.
    """

    KAYIT = {"yok": True, "var": False}

    def test_ortam_dogrularsa_mesru(self):
        self.assertEqual(kd.atlama_hukmu([["m", "yok"]], self.KAYIT),
                         [("m", "yok", "ortam")])

    def test_kayitsiz_sebep_mesru_degil(self):
        self.assertEqual(kd.atlama_hukmu([["m", "canim istedi"]], self.KAYIT),
                         [("m", "canim istedi", "kayitsiz")])

    def test_on_kosul_saglaniyorsa_mesru_degil(self):
        # Kayıtlı bir sebebi kopyalamak muafiyet satın almaz: ortam o
        # bağımlılığı sağlıyorsa atlamayı açıklayan bir şey yoktur.
        self.assertEqual(kd.atlama_hukmu([["m", "var"]], self.KAYIT),
                         [("m", "var", "yanlis")])

    def test_kayit_okunamazsa_fail_closed(self):
        # None = kayıt OKUNAMADI. "Okunamadı" ile "meşru" aynı şey değildir.
        self.assertEqual(kd.atlama_hukmu([["m", "yok"]], None),
                         [("m", "yok", "okunamadi")])

    def test_her_bloklayan_hukmun_gerekcesi_var(self):
        # Mesajsız hüküm kapıyı KeyError ile çökertir — ve çöken kapı,
        # koruduğunu sandığın kapıdır.
        hukumler = {h for _, _, h in kd.atlama_hukmu(
            [["m", "yok"], ["m", "canim istedi"], ["m", "var"]], self.KAYIT)}
        hukumler |= {h for _, _, h in kd.atlama_hukmu([["m", "yok"]], None)}
        self.assertEqual(sorted(hukumler - {"ortam"}),
                         sorted(kd.ATLAMA_MESAJI))


class TestKapsamiTest(unittest.TestCase):
    """Keşfe hiç girmeyen test dosyası sessizce kapsam kaybıdır.

    2026-08-07 bulgusu: PyYAML'sız yorumlayıcıda üç modül import'ta çöktü;
    süite `Ran 186` yazdı, PyYAML'lı yorumlayıcıda `Ran 220`. Eksilen 34 test
    "koşmadı" diye DEĞİL, hiç sayılmadığı için görünmedi. Aynı sessizlik
    yanlış adlandırılmış (`route_test.py`) ya da hiç test üretmeyen dosyada da
    olur — ve orada çıkış kodu bile 0'dır.
    """

    def test_kesfe_girmeyen_dosya_yakalanir(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/route_test.py",       # `test*.py` desenine uymaz
                "import unittest\n"
                "class X(unittest.TestCase):\n    pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, {"test_a"}),
                             ["route_test.py"])

    def test_dolayli_taban_sinifi_da_yakalanir(self):
        # Codex bulgusu (PR #26): taban sınıf takma adla gelirse `TestCase`
        # sözcüğü `class` satırında GEÇMEZ. Sözcüğe bakan bekçi burada kör
        # kalırdı — ve kör bekçi, olmayan korumaya güvendirir.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/route_test.py",
                "import unittest\n"
                "Taban = unittest.TestCase\n"
                "class X(Taban):\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["route_test.py"])

    def test_async_test_metodu_da_yakalanir(self):
        # Codex bulgusu (PR #26, ikinci tur): IsolatedAsyncioTestCase alt
        # sınıfları `async def test_*` yazar. Takma adlı tabanla birleşince
        # her iki imza da ıskalanırdı.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/async_test.py",
                "import unittest\n"
                "Taban = unittest.IsolatedAsyncioTestCase\n"
                "class X(Taban):\n"
                "    async def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["async_test.py"])

    def test_toplanan_dosya_sorun_degil(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/test_a.py",
                "import unittest\n"
                "class X(unittest.TestCase):\n    pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, {"test_a"}), [])

    def test_dis_taban_sinifi_da_yakalanir(self):
        # Codex bulgusu (PR #26, üçüncü tur): taban BAŞKA dosyadan gelirse
        # `unittest` adı bu dosyada hiç geçmez. Kural üçüncü kez aynı yerden
        # sızdı — çare deseni bir kez daha genişletmek değil, VARSAYILANI
        # çevirmek: test metodu varsa dosya toplanmalıdır, aksi açıkça yazılır.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/dis_test.py",
                "from ortak_taban import Taban\n"
                "class X(Taban):\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["dis_test.py"])

    def test_toplanmaz_isareti_gerekceyle_muaf_tutar(self):
        # Kasıtlı yardımcı (paylaşılan mixin) susturulabilir — ama GÖRÜNÜR
        # ve gerekçeli. Gerekçesiz işaret muafiyet saymaz.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/ortak.py",
                "# toplanmaz: paylasilan mixin, alt siniflar uzerinden kosar\n"
                "class Ortak:\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()), [])

    def test_string_icindeki_isaret_muaf_tutmaz(self):
        # Codex bulgusu (PR #30): işaret ham metinde arandığı için bir
        # fixture string'i dosyayı muaf tutuyordu. Tarayıcının kendi test
        # dosyasını görmemesi kapının en kötü kör noktasıdır — muafiyet
        # yalnız satır başındaki GERÇEK yorumla verilir.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/sahte_test.py",
                "import unittest\n"
                'ORNEK = "# toplanmaz: bu bir fixture, gercek isaret degil"\n'
                "class X(unittest.TestCase):\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["sahte_test.py"])

    def test_bu_dosya_kendini_muaf_tutmuyor(self):
        # Bu dosya fixture'larında '# toplanmaz:' metnini TAŞIYOR; bekçi
        # onu muafiyet sayarsa kendi test dosyasına kör kalır.
        #
        # Ad `__file__`den okunur, elle yazılmaz: bu sınıf bir kez taşındı ve
        # sabit ad geride kalsaydı test YANLIŞ SEBEPLE yeşil kalırdı — işareti
        # taşımayan bir dosyayı denetliyor olurdu.
        self.assertIn(os.path.basename(__file__),
                      kd.toplanmayan_testler(ROOT, set()))

    def test_uc_tirnak_icindeki_isaret_muaf_tutmaz(self):
        # Codex bulgusu (PR #30, ikinci tur): satır başı kuralı ham metinde
        # uygulanınca docstring/fixture içindeki satır da "yorum" sayılıyordu.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/sahte_test.py",
                'ORNEK = """\n'
                "# toplanmaz: bu bir fixture govdesi, gercek yorum degil\n"
                '"""\n'
                "import unittest\n"
                "class X(unittest.TestCase):\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["sahte_test.py"])

    def test_self_olmayan_ilk_parametre_de_yakalanir(self):
        # Codex bulgusu (PR #30, ikinci tur): ilk parametre adı sözleşme
        # değildir; `cls`, `_` ya da başka bir ad da geçerli test metodudur.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/dis_test.py",
                "from ortak_taban import Taban\n"
                "class X(Taban):\n"
                "    def test_a(cls):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["dis_test.py"])

    def test_satir_ici_isaret_muaf_tutmaz(self):
        # Codex bulgusu (PR #30, üçüncü tur): tokenize'a geçerken sütun
        # bilgisi düşmüştü. Muafiyet dosya düzeyinde bir BEYANDIR; bir kod
        # satırının kuyruğunda ya da metot gövdesinde kazara doğamaz.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/kuyruk_test.py",
                "import unittest\n"
                "X = 1  # toplanmaz: kuyrukta, beyan degil\n"
                "class Y(unittest.TestCase):\n"
                "    def test_a(self):\n"
                "        # toplanmaz: govdede, beyan degil\n"
                "        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["kuyruk_test.py"])

    def test_kosul_icinde_tanimlanan_test_de_yakalanir(self):
        # Codex bulgusu (PR #30, dördüncü tur): yalnız doğrudan sınıf gövdesi
        # geziliyordu; `if`/`try` içinde tanımlanan metot görünmüyordu.
        # Sınıf gövdesi düz bir liste değil, bir AĞAÇTIR.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/kosul_test.py",
                "import sys\n"
                "Taban = __import__('unittest').TestCase\n"
                "class X(Taban):\n"
                "    if sys.version_info >= (3, 8):\n"
                "        def test_a(self):\n            pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()),
                             ["kosul_test.py"])

    def test_metot_icindeki_yerel_fonksiyon_test_sayilmaz(self):
        # Codex bulgusu (PR #32): `ast.walk` metot gövdesine de iniyordu,
        # yani yerel bir `def test_*` yardımcısı dosyayı "test taşıyor"
        # yapıyordu. Bu yanlış POZİTİF — önceki sekiz turun tersi yön.
        # Gürültü sessizlikten iyidir ama kapı yine de doğru olmalı:
        # sürekli sahte kırmızı, insana kapıyı yok saymayı öğretir.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/yardimci.py",
                "class Yardimci:\n"
                "    def kur(self):\n"
                "        def test_ic():\n            return 1\n"
                "        return test_ic\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()), [])

    def test_match_ve_except_star_altindaki_test_de_yakalanir(self):
        # Codex bulgusu (PR #32): `_BLOK` `match/case`i kapsamıyordu.
        # `except*` (TryStar) aynı ailedendir ve bir sonraki tura kalmasın
        # diye birlikte kapatıldı — gövde taşıyan her ifade aynı kural.
        for ad, govde in (
            ("match_test.py",
             "import sys\n"
             "Taban = __import__('unittest').TestCase\n"
             "class X(Taban):\n"
             "    match sys.platform:\n"
             "        case _:\n"
             "            def test_a(self):\n                pass\n"),
            ("star_test.py",
             "Taban = __import__('unittest').TestCase\n"
             "class X(Taban):\n"
             "    try:\n        pass\n"
             "    except* ValueError:\n"
             "        def test_a(self):\n            pass\n"),
        ):
            with self.subTest(dosya=ad), tempfile.TemporaryDirectory() as td:
                yaz(td, "tests/" + ad, govde)
                self.assertEqual(kd.toplanmayan_testler(td, set()), [ad])

    def test_gerekcesiz_toplanmaz_isareti_muaf_tutmaz(self):
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/ortak.py",
                "# toplanmaz:\n"
                "class Ortak:\n"
                "    def test_a(self):\n        pass\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()), ["ortak.py"])

    def test_testcase_tasimayan_yardimci_denetlenmez(self):
        # tests/ortam.py gibi paylaşılan yardımcılar test üretmez; keşfe
        # girmemeleri normaldir, kapsam kaybı değildir.
        with tempfile.TemporaryDirectory() as td:
            yaz(td, "tests/ortam.py", "YAML = None\n")
            self.assertEqual(kd.toplanmayan_testler(td, set()), [])

    def test_bu_reponun_her_test_dosyasi_toplaniyor(self):
        toplanan = {f[:-3] for f in os.listdir(os.path.join(ROOT, "tests"))
                    if f.startswith("test_") and f.endswith(".py")}
        self.assertEqual(kd.toplanmayan_testler(ROOT, toplanan), [])


if __name__ == "__main__":
    unittest.main()
