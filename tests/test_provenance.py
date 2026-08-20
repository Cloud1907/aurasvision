#!/usr/bin/env python3
"""Provenance — "hangi sürüm, nereden, ne zaman" makinece cevaplanmalı.

H. Demir denetimi (2026-08-15): kurulum manifesti yalnız `rel → sha256`
kayıtları taşıyordu; kaynak commit ya da kernel sürümü yazmıyordu. Bağlı bir
repoya bakıp "hangi Auras sürümü kurulu?" sorusunu manifestten cevaplamak
mümkün değildi — uyumluluk, kaynak klonunun erişebildiği git geçmişine
emanetti.

İkinci ayak (M13): `evidence.json` da aynı soruyu cevaplamıyordu. Şema
`task_class`, `risk`, `engine.skills_used`, `digests` ve `approvals`
alanlarını tanımlıyordu ama CI hiçbirini doldurmuyordu; `make_evidence.py`
desteği vardı, workflow argüman vermiyordu. Kanıt manifesti, tasarımın
öngördüğü provenance kaydından zayıftı.
"""
import importlib.util
import json
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


kd = _load("kernel_dosyalari")


class ManifestProvenanceTest(unittest.TestCase):
    def test_manifest_surum_ve_kaynak_tasir(self):
        veri = kd.manifest_govde({"bin/x.py": "abc"}, kaynak=ROOT)
        self.assertEqual(veri["schema_version"], 2)
        self.assertIn("kernel", veri)
        for alan in ("commit", "repo", "kurulum"):
            self.assertIn(alan, veri["kernel"], alan)

    def test_dosya_ozetleri_ayri_alanda(self):
        veri = kd.manifest_govde({"bin/x.py": "abc"}, kaynak=ROOT)
        self.assertEqual(veri["dosyalar"], {"bin/x.py": "abc"})

    def test_eski_duz_bicim_okunabilir(self):
        """Geriye uyum: v1 manifest düz {yol: hash} sözlüğüydü.

        Okuyamamak, kurulu projeyi 'hiç kurulmamış' saymak olurdu ve /auras
        her dosyayı yeniden yazardı.
        """
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, ".agents", ".kernel-manifest.json")
            os.makedirs(os.path.dirname(yol))
            with open(yol, "w", encoding="utf-8") as fh:
                json.dump({"bin/x.py": "abc"}, fh)
            self.assertEqual(kd.manifest_dosyalari(d), {"bin/x.py": "abc"})

    def test_yeni_bicim_okunabilir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, ".agents", ".kernel-manifest.json")
            os.makedirs(os.path.dirname(yol))
            with open(yol, "w", encoding="utf-8") as fh:
                json.dump(kd.manifest_govde({"bin/y.py": "def"}, ROOT), fh)
            self.assertEqual(kd.manifest_dosyalari(d), {"bin/y.py": "def"})

    def test_manifest_yoksa_bos(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(kd.manifest_dosyalari(d), {})

    def test_surum_sorusu_tek_komutla_cevaplanir(self):
        """`kd.kurulu_surum` bağlı projede sürümü döndürmeli."""
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, ".agents", ".kernel-manifest.json")
            os.makedirs(os.path.dirname(yol))
            with open(yol, "w", encoding="utf-8") as fh:
                json.dump(kd.manifest_govde({}, ROOT), fh)
            bilgi = kd.kurulu_surum(d)
            self.assertTrue(bilgi.get("commit"))
            self.assertTrue(bilgi.get("kurulum"))


class EvidenceProvenanceTest(unittest.TestCase):
    """M13 — evidence.json zinciri: sınıf, risk, skill, digest."""

    def kos(self, *args):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "evidence.json")
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "make_evidence.py"),
                 "--out", out, *args],
                capture_output=True, text=True, cwd=ROOT)
            if not os.path.isfile(out):
                return p.returncode, None
            with open(out, encoding="utf-8") as fh:
                return p.returncode, json.load(fh)

    def test_risk_alanlari_tasinir(self):
        _kod, ev = self.kos("--check", "tests=passed",
                            "--risk-provisional", "approval",
                            "--risk-final", "deny")
        self.assertEqual(ev["risk"], {"provisional": "approval",
                                      "final": "deny"})

    def test_skill_kaydi_tasinir(self):
        _kod, ev = self.kos("--check", "tests=passed",
                            "--skill", "implement-change",
                            "--skill", "security-review")
        self.assertEqual(ev["engine"]["skills_used"],
                         ["implement-change", "security-review"])

    def test_digest_dosya_ozeti_uretir(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("kanıt")
            rapor = fh.name
        try:
            _kod, ev = self.kos("--check", "tests=passed",
                                "--digest", f"test-report={rapor}")
            self.assertTrue(ev["digests"]["test-report"].startswith("sha256:"))
        finally:
            os.remove(rapor)

    def test_workflow_provenance_alanlarini_geciriyor(self):
        """CI gerçekten bu argümanları veriyor mu — şema desteği yetmez.

        Denetim bulgusu: `make_evidence.py` alanları destekliyordu ama
        workflow hiçbirini geçmiyordu; `engine.skills_used` her koşuda BOŞTU.
        """
        yol = os.path.join(ROOT, ".github", "workflows", "evidence.yml")
        with open(yol, encoding="utf-8") as fh:
            metin = fh.read()
        for bayrak in ("--risk-provisional", "--risk-final", "--digest"):
            self.assertIn(bayrak, metin,
                          f"workflow evidence'a {bayrak} geçmiyor")


if __name__ == "__main__":
    unittest.main()
