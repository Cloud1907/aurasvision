"""memory_hygiene çekirdek mantığı — bekçinin bekçisi."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import memory_hygiene as mh  # noqa: E402


class TestMemoryHygiene(unittest.TestCase):
    def test_parse_date(self):
        import datetime as dt
        self.assertEqual(mh.parse_date("2026-07-24"), dt.date(2026, 7, 24))
        self.assertIsNone(mh.parse_date("tarih yok"))
        self.assertIsNone(mh.parse_date("2026-13-99"))  # geçersiz ay/gün

    def test_slug_machine_bagimsiz(self):
        # default_targets sabit /Users/... yolu ÜRETMEMELI
        src = mh.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("/Users/cloudsmac", text,
                         "hardcoded kullanıcı yolu geri gelmiş")
        self.assertIn("replace(\"/\", \"-\")", text, "slug dinamik türetilmeli")

    def test_bayat_kayit_isaretlenir(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "eski.md")
            with open(p, "w") as f:
                f.write("Karar: 2020-01-01 tarihli bir not. ADR yok.")
            findings = []
            mh.scan_file(p, mh.parse_date("2026-07-24"), 90, findings)
            levels = [f[0] for f in findings]
            self.assertIn("BAYAT", levels)

    def test_secret_yakalanir(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "sizinti.md")
            with open(p, "w") as f:
                f.write("token: ghp_" + "a" * 30)
            findings = []
            mh.scan_file(p, mh.parse_date("2026-07-24"), 90, findings)
            self.assertIn("KRİTİK", [f[0] for f in findings])

    def test_guclu_secret_desenleri(self):
        # Rapor bulgusu: AWS/JWT/Bearer/Google/Slack de yakalanmalı
        ornekler = [
            "AKIA" + "A" * 16,                          # AWS
            "AIza" + "b" * 35,                          # Google
            "xoxb-" + "1" * 20,                         # Slack
            "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,  # JWT
            "Authorization: " + "x" * 24,               # Bearer/Authorization
            "Authorization: Basic dXNlcjpwYXNzd29yZA==",  # Codex P1: base64 Basic auth
        ]
        for tok in ornekler:
            self.assertIsNotNone(mh.SECRET_RE.search(tok),
                                 f"yakalanmalı: {tok[:12]}...")
        # placeholder tetiklememeli
        self.assertIsNone(mh.SECRET_RE.search("password = kisa"))

    def test_okunamayan_dosya_yutulmaz(self):
        # Var olmayan dosya sessizce atlanmamalı — bulgu üretmeli
        findings = []
        mh.scan_file("/yok/boyle/bir/dosya.md",
                     mh.parse_date("2026-07-24"), 90, findings)
        self.assertIn("OKUNAMADI", [f[0] for f in findings])


if __name__ == "__main__":
    unittest.main()
