#!/usr/bin/env python3
"""Görünürlük katmanı testleri — olay kaydı ve tur tablosu.

Sözleşme: hook'lar hiçbir koşulda isteği bloklamaz (her zaman exit 0),
secret asla diske yazılmaz, yönlendirilen skill ile gerçekten yüklenen
skill karşılaştırılabilir olur.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_event = _load("run_event")
durum = _load("durum")


class AppendTest(unittest.TestCase):
    def test_olay_jsonl_satiri_olarak_eklenir(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            run_event.append({"kind": "skill", "skill": "kernel-work"}, log)
            run_event.append({"kind": "stop"}, log)
            with open(log, encoding="utf-8") as fh:
                lines = fh.read().strip().split("\n")
            self.assertEqual(len(lines), 2)
            first = json.loads(lines[0])
            self.assertEqual(first["skill"], "kernel-work")
            self.assertIn("ts", first)  # zaman damgası eklenir

    def test_secret_diske_yazilmaz(self):
        # Sahte token kaynakta literal durmasın (secret tarayıcı kapısı).
        sahte = "gh" + "p_" + "abcdefghij0123456789"
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            run_event.append(
                {"kind": "route", "intent": f"token {sahte} ile dene"}, log)
            with open(log, encoding="utf-8") as fh:
                body = fh.read()
            self.assertNotIn(sahte, body)
            self.assertIn("[gizlendi]", body)

    def test_duz_metin_kimlik_bilgisi_maskelenir(self):
        """Sohbette geçen parola/TC/e-posta diske yazılmamalı."""
        vakalar = ("password: hunter2", "parolam hunter2", "şifre Aa123456!",
                   "tc 12345678901", "asil@ornek.com.tr", "api key abc123def456")
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            for v in vakalar:
                with self.subTest(v=v):
                    kayit = run_event.temizle(v)
                    self.assertIn("[gizlendi]", kayit, f"maskelenmedi: {v}")

    def test_bagli_olmayan_repoya_yazilmaz(self):
        """Global router yabancı repoya kayıt bırakmamalı (untracked sızıntı)."""
        with tempfile.TemporaryDirectory() as td:
            yol = run_event.log_path(pdir=td)
            self.assertNotIn(td, yol, "yabancı repoya yazıyor")
            self.assertIn(os.path.expanduser("~/.claude/auras/runtime"), yol)

    def test_bagli_projede_yerel_kayit(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, ".agents"))
            with open(os.path.join(td, ".agents", "routing.yml"), "w") as fh:
                fh.write("schema_version: 1\n")
            yol = run_event.log_path(pdir=td)
            self.assertTrue(yol.startswith(td), "bağlı projede yerel yazmalı")

    def test_ayni_skill_turda_bir_kez_kaydedilir(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            for _ in range(3):
                subprocess.run(
                    [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                     "--kind", "skill", "--log", log],
                    input=json.dumps({"tool_input": {"skill": "kernel-work"}}),
                    capture_output=True, text=True, cwd=ROOT)
            with open(log, encoding="utf-8") as fh:
                self.assertEqual(len(fh.readlines()), 1, "tekrar kaydedildi")

    def test_gerekce_kodu_zorunlu(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            # sebep kodu yoksa olay yazılmaz
            subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "skipped", "--skill", "implement-change",
                 "--log", log],
                input="{}", capture_output=True, text=True, cwd=ROOT)
            self.assertFalse(os.path.exists(log))
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "skipped", "--skill", "implement-change",
                 "--reason", "misroute", "--note", "sohbet turu", "--log", log],
                input="{}", capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(p.returncode, 0)
            with open(log, encoding="utf-8") as fh:
                self.assertIn("misroute", fh.read())

    def test_intent_kapatilabilir(self):
        os.environ["AURAS_LOG_INTENT"] = "0"
        try:
            with tempfile.TemporaryDirectory() as td:
                log = os.path.join(td, "events.jsonl")
                run_event.append({"kind": "route", "routed": "auras",
                                  "intent": "gizli kalsın"}, log)
                with open(log, encoding="utf-8") as fh:
                    body = fh.read()
                self.assertNotIn("gizli", body)
                self.assertIn("auras", body)
        finally:
            os.environ.pop("AURAS_LOG_INTENT", None)

    def test_intent_kisaltilir(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            run_event.append({"kind": "route", "intent": "x" * 300}, log)
            with open(log, encoding="utf-8") as fh:
                rec = json.loads(fh.read())
            self.assertLessEqual(len(rec["intent"]), run_event.INTENT_MAX + 1)

    def test_bozuk_stdin_bloklamaz(self):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "skill", "--log", os.path.join(td, "e.jsonl")],
                input="bu json değil", capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(proc.returncode, 0)

    def test_adsiz_skill_olayi_yazilmaz(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "skill", "--log", log],
                input=json.dumps({"tool_input": {}}),
                capture_output=True, text=True, cwd=ROOT)
            self.assertFalse(os.path.exists(log), "gürültü olayı yazıldı")

    def test_yazilamayan_yol_bloklamaz(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
             "--kind", "skill", "--log", "/kok/dizin/yok/events.jsonl"],
            input=json.dumps({"tool_input": {"skill": "auras"}}),
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0)

    def test_skill_adi_hook_payloadindan_okunur(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "skill", "--log", log],
                input=json.dumps({"tool_name": "Skill",
                                  "tool_input": {"skill": "security-review"}}),
                capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(proc.returncode, 0)
            with open(log, encoding="utf-8") as fh:
                self.assertIn("security-review", fh.read())


class TestOracleTest(unittest.TestCase):
    """Testin geçtiği ÇIKIŞ KODUNDAN bilinir, çıktı sözcüğünden değil.

    2026-08-07 ölçümü (bu repoda, canlı hook üstünde): `exit 1` ile dönen ama
    çıktısında "passed" geçen komut eski oracle'a göre GEÇTİ sayılıyordu.
    Kapı bu sinyale dayandığı için "test kanıtı var" demek, "çıktıda 'OK'
    sözcüğü geçti" demekten ibaretti.
    """

    def test_yaniltici_cikti_geciyor_sayilmaz(self):
        # Komut çöktü ama çıktısında 'passed' var → geçti DEĞİL.
        self.assertIsNot(
            run_event.test_gecti({"stdout": "3 tests passed", "exit_code": 1}),
            True)

    def test_cikis_kodu_sifir_gecti(self):
        self.assertIs(
            run_event.test_gecti({"stdout": "her şey yolunda", "exit_code": 0}),
            True)

    def test_cikis_kodu_sifirdan_farkli_kaldi(self):
        self.assertIs(
            run_event.test_gecti({"stdout": "OK OK OK", "exit_code": 2}), False)

    def test_iptal_edilen_komut_gecti_sayilmaz(self):
        # Kullanıcı iptal etti: sonuç bilinmiyor, "geçti" değil.
        self.assertIsNot(
            run_event.test_gecti({"stdout": "passed", "interrupted": True}),
            True)

    def test_kanit_yoksa_belirsiz_doner(self):
        # Ne çıkış kodu ne platform sinyali → None. ASLA True.
        self.assertIsNone(run_event.test_gecti({}))
        self.assertIsNone(run_event.test_gecti("dict degil"))

    def test_basarisizlik_olayi_kirmizi_yazar(self):
        """PostToolUseFailure = komut çöktü. Kayda 'kaldı' diye girmeli.

        Bulgu (Codex, PR #15 incelemesi): Claude Code başarısız araç
        çağrısında PostToolUse'u DEĞİL PostToolUseFailure'ı tetikliyor.
        Yalnız PostToolUse dinlendiği için başarısızlık kayda hiç
        girmiyordu — kapının 'testler kırmızı' dalı ölü koddu.
        """
        ok, src = run_event.bash_sonucu(
            {"stdout": "12 failed"},
            olay="PostToolUseFailure")
        self.assertIs(ok, False)
        self.assertEqual(src, "event")

    def test_cikis_kodu_maskeleyen_komut_gecti_sayilmaz(self):
        """`pytest || true` kabuktan 0 döner ama testler kalmıştır.

        Çıkış kodu oracle'ı ancak çıkış kodu TESTİN kodu ise geçerlidir.
        Test çağrısından sonra gelen `||`, `|`, `;` onu kabuğun koduyla
        değiştirir — bu durumda cevap 'geçti' değil 'bilinmiyor'dur.
        """
        for cmd in ("pytest || true",
                    "python3 -m unittest 2>&1 | tail -5",
                    "pytest; echo bitti",
                    "npm test || echo 'sorun yok'"):
            with self.subTest(cmd=cmd):
                self.assertTrue(run_event.kod_maskelendi(cmd), cmd)
                ok, src = run_event.bash_sonucu({"stdout": "OK"}, cmd=cmd)
                self.assertIsNone(ok, f"{cmd} → geçti sayılmamalı")

    def test_maskelemeyen_komut_normal_degerlendirilir(self):
        for cmd in ("pytest tests/",
                    "cd repo && python3 -m unittest discover",
                    "set -o pipefail; pytest | tail -3",
                    "dotnet test --no-build"):
            with self.subTest(cmd=cmd):
                self.assertFalse(run_event.kod_maskelendi(cmd), cmd)

    def test_sonuc_kaynagi_kayda_girer(self):
        """'ok' değerinin nereden geldiği denetlenebilir olmalı.

        Platform davranışına dayanan çıkarım ile gerçek exit code aynı
        güvende değildir; kayıt hangisi olduğunu söylemezse ayırt edilemez.
        """
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
                 "--kind", "bash", "--log", log],
                input=json.dumps({
                    "tool_name": "Bash",
                    "tool_input": {"command": "python3 -m unittest"},
                    "tool_response": {"stdout": "OK", "exit_code": 0}}),
                capture_output=True, text=True, cwd=ROOT)
            with open(log, encoding="utf-8") as fh:
                kayit = json.loads(fh.read().strip())
            self.assertIs(kayit["ok"], True)
            self.assertEqual(kayit["src"], "exit")


class TurTablosuTest(unittest.TestCase):
    def turlar(self, olaylar):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            for o in olaylar:
                run_event.append(o, log)
            return durum.turlari_cikar(durum.olaylari_oku(log))

    def test_yonlendirilen_ve_yuklenen_eslesirse_uyumlu(self):
        turlar = self.turlar([
            {"kind": "route", "routed": "kernel-work", "task_class": "code-change",
             "intent": "bekçi testi ekle"},
            {"kind": "skill", "skill": "kernel-work"},
            {"kind": "stop"},
        ])
        self.assertEqual(len(turlar), 1)
        self.assertEqual(turlar[0]["durum"], "uyumlu")

    def test_yonlendirilip_yuklenmezse_atlandi(self):
        turlar = self.turlar([
            {"kind": "route", "routed": "implement-change", "intent": "cache ekle"},
            {"kind": "stop"},
        ])
        self.assertEqual(turlar[0]["durum"], "ATLANDI")

    def test_yonlendirme_yoksa_sohbet(self):
        turlar = self.turlar([
            {"kind": "route", "routed": None, "intent": "merhaba"},
            {"kind": "stop"},
        ])
        self.assertEqual(turlar[0]["durum"], "sohbet")

    def test_farkli_skill_yuklenirse_sapma(self):
        turlar = self.turlar([
            {"kind": "route", "routed": "implement-change", "intent": "ekle"},
            {"kind": "skill", "skill": "research-with-evidence"},
            {"kind": "stop"},
        ])
        self.assertEqual(turlar[0]["durum"], "SAPMA")

    def test_subagent_sayilir(self):
        turlar = self.turlar([
            {"kind": "route", "routed": "kernel-work", "intent": "x"},
            {"kind": "skill", "skill": "kernel-work"},
            {"kind": "subagent", "agent": "qa-engineer"},
            {"kind": "stop"},
        ])
        self.assertEqual(turlar[0]["subagent"], ["qa-engineer"])

    def test_bozuk_satir_atlanir_digerleri_okunur(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "events.jsonl")
            run_event.append({"kind": "route", "routed": "auras", "intent": "a"}, log)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("{bozuk satır\n")
            run_event.append({"kind": "stop"}, log)
            self.assertEqual(len(durum.olaylari_oku(log)), 2)

    def test_tablo_render_edilir(self):
        turlar = self.turlar([
            {"kind": "route", "routed": "kernel-work", "task_class": "code-change",
             "intent": "görünürlük katmanı"},
            {"kind": "skill", "skill": "kernel-work"},
            {"kind": "stop"},
        ])
        out = durum.tablo(turlar)
        self.assertIn("kernel-work", out)
        self.assertIn("YÜKLENEN", out)

    # route.py yönlendirme tablosunu (yaml) okuyamazsa sessizce exit 0 verir
    # ve hiç olay yazmaz; bu test o boş kaydı FileNotFoundError olarak görürdü.
    @pyyaml_gerekir
    def test_env_override_izolasyon_saglar(self):
        # validate/test koşumları kullanıcının aktivite kaydını kirletmemeli
        with tempfile.TemporaryDirectory() as td:
            hedef = os.path.join(td, "izole.jsonl")
            os.environ["AURAS_EVENT_LOG"] = hedef
            try:
                self.assertEqual(run_event.log_path(), hedef)
                proc = subprocess.run(
                    [sys.executable, os.path.join(ROOT, "bin", "route.py")],
                    input=json.dumps({"prompt": "cache ekle"}),
                    capture_output=True, text=True, cwd=ROOT,
                    env=dict(os.environ, AURAS_EVENT_LOG=hedef))
                self.assertEqual(proc.returncode, 0)
                with open(hedef, encoding="utf-8") as fh:
                    self.assertIn("implement-change", fh.read())
            finally:
                os.environ.pop("AURAS_EVENT_LOG", None)

    def test_log_yoksa_bos_liste(self):
        self.assertEqual(durum.olaylari_oku("/olmayan/yol.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
