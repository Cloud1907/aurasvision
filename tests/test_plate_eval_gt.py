"""Plaka yer-gerçeği süzgeci ve kümeleme — arşiv, model, TRASSIR bağlantısı İSTEMEZ.

En kritik davranış: TRASSIR'ın KENDİ hatalı okumaları (şablonsuz veya tek
seferlik) yer gerçeğine sızmamalı. 2026-09-02'de `LAAC413` (şablon `/`) tam
bunun örneğiydi — gerçek plaka `41ARC413` idi, TRASSIR'ın kendi hatasıydı.
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.plate_eval_gt import gt_gecisleri, levenshtein


def _yaz(satirlar: list[dict]) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                    encoding="utf-8")
    json.dump(satirlar, f)
    f.close()
    return f.name


class Levenshtein(unittest.TestCase):
    def test_ayni_dize_sifir(self):
        self.assertEqual(levenshtein("41ARC413", "41ARC413"), 0)

    def test_tek_karakter_eksik(self):
        """LAAC413 vakasındaki gibi: bir harf düşmüş."""
        self.assertEqual(levenshtein("41AC413", "41ARC413"), 1)

    def test_tamamen_farkli(self):
        self.assertEqual(levenshtein("ABC", "XYZ"), 3)

    def test_bos_dize(self):
        self.assertEqual(levenshtein("", "ABC"), 3)


class SablonSuzgeci(unittest.TestCase):
    def test_sablonsuz_okuma_disarida_kalir(self):
        """plaka_sablonu='/' TRASSIR'ın KENDİ hatasıdır — yer gerçeği değil."""
        yol = _yaz([
            {"plaka": "LAAC413", "plaka_sablonu": "/", "okuma_zamani": "2026-09-02T16:48:03Z"},
            {"plaka": "41ARC413", "plaka_sablonu": "tr/type1_5_1", "okuma_zamani": "2026-09-01T10:00:00Z"},
            {"plaka": "41ARC413", "plaka_sablonu": "tr/type1_5_1", "okuma_zamani": "2026-09-01T10:00:05Z"},
        ])
        g = gt_gecisleri(yol)
        plakalar = {x["plaka"] for x in g}
        self.assertNotIn("LAAC413", plakalar)
        self.assertIn("41ARC413", plakalar)
        Path(yol).unlink()

    def test_tek_okuma_yer_gercegi_sayilmaz(self):
        """Bir kez görülen plaka — TEKRAR_ESIGI=2 altında kalır, dışarıda kalır."""
        yol = _yaz([
            {"plaka": "34ABC12", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:00Z"},
        ])
        self.assertEqual(gt_gecisleri(yol), [])
        Path(yol).unlink()


class Kumeleme(unittest.TestCase):
    def test_yakin_okumalar_tek_gecis(self):
        """90 sn içindeki okumalar AYNI aracın geçişidir, ayrı geçiş sayılmamalı."""
        yol = _yaz([
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:00Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:30Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:01:15Z"},
        ])
        g = gt_gecisleri(yol)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["plaka"], "34XYZ99")
        Path(yol).unlink()

    def test_uzak_okumalar_ayri_gecis(self):
        """90 sn'den uzak okumalar İKİ ayrı geçiştir (aynı plaka, iki kez gelmiş)."""
        yol = _yaz([
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:00Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:10Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T12:00:00Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T12:00:10Z"},
        ])
        g = gt_gecisleri(yol)
        self.assertEqual(len(g), 2)
        Path(yol).unlink()

    def test_gecis_ortasi_ilk_son_arasinda(self):
        yol = _yaz([
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:00Z"},
            {"plaka": "34XYZ99", "plaka_sablonu": "tr/type1_3_1",
             "okuma_zamani": "2026-09-01T10:00:10Z"},
        ])
        g = gt_gecisleri(yol)
        self.assertTrue(g[0]["ilk"] <= g[0]["orta"] <= g[0]["son"])
        Path(yol).unlink()


if __name__ == "__main__":
    unittest.main()
