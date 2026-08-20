#!/usr/bin/env python3
"""Kanıt kendi kaynağını taşımalı — "bağımsız makine" bir iddia, alan değilse kanıt değil.

AGENTS.md CI kapısını şöyle tanımlar: *aynı doğrulamayı BAĞIMSIZ makinede
tekrarlar*. Actions kotası bitip iş self-hosted runner'a alındığında bu cümle
yanlışa döner: kanıtı üreten makine ile kodu yazan makine aynıdır, ortak güven
kökü kullanıcının kendisidir (2026-08-16, 4Flow).

Bu ayrım PR yorumunda ya da sohbette durursa kaybolur. `evidence.json`'ın
kendisinde durursa kaybolmaz. Test tam olarak bunu kilitler:

  - `runner.independent` YALNIZ github-hosted'da true olabilir,
  - alanın yokluğu "bağımsız" diye okunamaz (fail-closed),
  - self-hosted kanıt yine ÜRETİLİR — engellenmez, yalnız doğru etiketlenir.

Son madde bilinçli: köprü meşru bir ödündür, kanıt üretimini durdurmak
kullanıcıyı kanıtsız çalışmaya iter ve durumu iyileştirmez.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARAC = os.path.join(ROOT, "bin", "make_evidence.py")

spec = importlib.util.spec_from_file_location("_mkev", ARAC)
mkev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mkev)


def uret(ortam=None, ad=None):
    """Aracı alt süreçte koşturur; ortam değişkeni gerçek koşumdaki gibi verilir."""
    cikti = os.path.join(tempfile.mkdtemp(), "evidence.json")
    env = dict(os.environ)
    env.pop("RUNNER_ENVIRONMENT", None)
    env.pop("RUNNER_NAME", None)
    if ortam:
        env["RUNNER_ENVIRONMENT"] = ortam
    if ad:
        env["RUNNER_NAME"] = ad
    subprocess.run([sys.executable, ARAC, "--out", cikti, "--check", "test=passed"],
                   env=env, capture_output=True, check=True)
    with open(cikti) as f:
        return json.load(f)


class RunnerAlani(unittest.TestCase):
    def test_alan_her_zaman_yazilir(self):
        # Opsiyonel alan, olmayan alandır: unutulduğu an ayrım kaybolur.
        self.assertIn("runner", uret())

    def test_github_hosted_bagimsizdir(self):
        kanit = uret(ortam="github-hosted", ad="ubuntu-2")
        self.assertEqual(kanit["runner"]["environment"], "github-hosted")
        self.assertTrue(kanit["runner"]["independent"])

    def test_self_hosted_bagimsiz_degildir(self):
        kanit = uret(ortam="self-hosted", ad="mac-m4-bridge")
        self.assertEqual(kanit["runner"]["environment"], "self-hosted")
        self.assertFalse(kanit["runner"]["independent"])

    def test_self_hosted_kanit_yine_de_uretilir(self):
        # Köprü meşru bir ödün; üretimi durdurmak kullanıcıyı kanıtsız
        # çalışmaya iter. Doğru davranış engellemek değil, etiketlemektir.
        self.assertEqual(uret(ortam="self-hosted")["checks"][0]["status"], "passed")

    def test_ortam_yoksa_yereldir_ve_bagimsiz_degildir(self):
        kanit = uret()
        self.assertEqual(kanit["runner"]["environment"], "local")
        self.assertFalse(kanit["runner"]["independent"])

    def test_bilinmeyen_ortam_bagimsiz_sayilmaz(self):
        # Beyaz liste: yalnız "github-hosted" bağımsızdır. GitHub yarın yeni
        # bir değer eklerse varsayılan güvenli tarafa düşer.
        self.assertFalse(uret(ortam="acme-cloud")["runner"]["independent"])


class Sema(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "schemas", "evidence.schema.json")) as f:
            self.sema = json.load(f)

    def test_runner_semada_tanimli(self):
        self.assertIn("runner", self.sema["properties"])

    def test_environment_beyaz_listeli(self):
        alan = self.sema["properties"]["runner"]["properties"]["environment"]
        self.assertEqual(set(alan["enum"]), {"github-hosted", "self-hosted", "local"})

    def test_independent_zorunlu(self):
        self.assertIn("independent", self.sema["properties"]["runner"]["required"])


class BelgeGercegiSoylesin(unittest.TestCase):
    """AGENTS.md kapı tablosu bu sınırı YAZMALI — yazmazsa belge yanlış güven verir."""

    def test_agents_md_self_hosted_sinirini_yazar(self):
        with open(os.path.join(ROOT, "AGENTS.md")) as f:
            metin = f.read()
        self.assertIn("self-hosted", metin,
                      "AGENTS.md kapı tablosu self-hosted runner sınırını yazmıyor — "
                      "belge CI kanıtını koşulsuz 'bağımsız' diye tanıtıyor")


if __name__ == "__main__":
    unittest.main()
