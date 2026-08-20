#!/usr/bin/env python3
"""Keşif bekçisi: görünür atlama çökme değildir — ama her atlama meşru da değil.

Birinci tur (Agent Ofis kurulumu, 2026-08-12): pytest'siz yorumlayıcıda
`raise unittest.SkipTest` ile GÖRÜNÜR hâle getirilen modül, bekçide hâlâ
"import'ta çöktü" diye raporlandı. Sistemin kendi önerdiği çare ("ortam
bağımlılığıysa koşullu atlamaya çevir") uygulanınca bile kırmızı kalıyordu
— yani çare çalışmıyordu. unittest ikisini AYRI sınıflarla işaretler:
_FailedTest (çökme) ve ModuleSkipped (görünür atlama).

İkinci tur (Codex bağımsız incelemesi, PR #47, P1): ayrım yapıldı ama her
ModuleSkipped KOŞULSUZ meşru sayıldı. Bir modülün başına
`raise unittest.SkipTest("...")` yazmak testleri süitten çıkarmaya yetiyordu;
bekçi bunu "ortam bağımlılığı" sanıp bilgi satırı yazıyor, "Ran N" sessizce
daralıyordu — deponun kendi kuralının (eksilen test kırmızı testten
tehlikelidir) tam ihlali. Beyan kanıt değildir: atlama artık tests/ortam.py'nin
ilan ettiği ÖN-KOŞUL YOKLAMASIYLA doğrulanır.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import kapsam_bekcisi as kb  # noqa: E402


class KesifAtlamaTest(unittest.TestCase):
    # Temsilî ortam kaydı: bir sebebin yoklaması "bağımlılık gerçekten yok"
    # (atlama meşru), diğerininki "bağımlılık var" (atlamayı ortam açıklamaz).
    ORTAM = ("MESRU_ATLAMALAR = {\n"
             "    'kobay yok': lambda: True,\n"
             "    'kobay var': lambda: False,\n"
             "}\n")

    def kesfet(self, icerik, ortam=None):
        """Geçici tests/ dizininde keşfi koş, ham keşif sözlüğünü döndür."""
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location(
            "validate", os.path.join(ROOT, "bin", "validate.py"))
        val = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(val)
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "tests"))
            yazilacak = {"test_ornek.py": icerik}
            if ortam is not None:
                yazilacak["ortam.py"] = ortam
            for ad, govde in yazilacak.items():
                with open(os.path.join(td, "tests", ad), "w",
                          encoding="utf-8") as fh:
                    fh.write(govde)
            p = subprocess.run([sys.executable, "-c", val._KESIF_KODU],
                               capture_output=True, text=True, cwd=td)
            satir = next(s for s in reversed(p.stdout.splitlines())
                         if s.startswith(val._KESIF_ISARET))
            return json.loads(satir[len(val._KESIF_ISARET):])

    def hukumler(self, veri):
        return [h for _, _, h in kb.atlama_hukmu(veri["atlanan"],
                                                 veri["ortam"])]

    def test_gorunur_atlama_cokme_sayilmaz(self):
        veri = self.kesfet("import unittest\n"
                           "raise unittest.SkipTest('kobay yok')\n",
                           self.ORTAM)
        self.assertEqual(veri["hatali"], [],
                         "görünür atlama ÇÖKME olarak raporlandı")
        self.assertEqual(veri["atlanan"], [["test_ornek", "kobay yok"]],
                         "atlanan modül adıyla BİRLİKTE sebebiyle kayda "
                         "geçmeli — sebep olmadan meşruluk sınanamaz")

    def test_gercek_cokme_hala_yakalanir(self):
        veri = self.kesfet("import boyle_bir_modul_yok\n")
        self.assertIn("test_ornek", veri["hatali"],
                      "gerçek import çökmesi kaçtı")

    def test_ortam_dogrularsa_atlama_mesrudur(self):
        veri = self.kesfet("import unittest\n"
                           "raise unittest.SkipTest('kobay yok')\n",
                           self.ORTAM)
        self.assertEqual(veri["ortam"], {"kobay yok": True, "kobay var": False},
                         "ortam kaydı yoklanmış hâliyle raporlanmalı")
        self.assertEqual(self.hukumler(veri), ["ortam"])

    def test_kayitsiz_atlama_blok_uretir(self):
        # P1'in ta kendisi: koşulsuz atlama hiçbir ortam ön-koşuluna bağlı
        # değildir; bekçi onu meşru sayarsa kapsam beyanla daraltılabilir.
        veri = self.kesfet("import unittest\n"
                           "raise unittest.SkipTest('canim istedi')\n",
                           self.ORTAM)
        self.assertEqual(self.hukumler(veri), ["kayitsiz"])

    def test_ortam_saglaniyorsa_atlama_blok_uretir(self):
        # Sebep KAYITLI ama bu makinede bağımlılık var: atlamayı ortam
        # açıklamıyor. Kayıtlı bir sebebi kopyalamak muafiyet satın almaz.
        veri = self.kesfet("import unittest\n"
                           "raise unittest.SkipTest('kobay var')\n",
                           self.ORTAM)
        self.assertEqual(self.hukumler(veri), ["yanlis"])

    def test_ortam_kaydi_okunamazsa_fail_closed(self):
        # tests/ortam.py yok (ya da kayıt bozuk): "okunamadı" ile "meşru"
        # aynı şey değildir — susmak, kapının olduğu ama korumadığı hâldir.
        veri = self.kesfet("import unittest\n"
                           "raise unittest.SkipTest('kobay yok')\n")
        self.assertIsNone(veri["ortam"])
        self.assertEqual(self.hukumler(veri), ["okunamadi"])


if __name__ == "__main__":
    unittest.main()
