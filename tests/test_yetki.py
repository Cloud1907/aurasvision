#!/usr/bin/env python3
"""Capability profili → gerçek motor politikası.

Denetim bulgusu (2026-08-15, iki bağımsız rapor da aynı P0'ı buldu):
`.agents/capability-profiles/*.yml` içindeki `filesystem`, `commands` ve
`network` alanları YALNIZCA şema düzeyinde doğrulanıyordu (`validate.py`
anahtarın varlığına ve `network.mode` enum'una bakıyor, başka hiçbir şeye).
Repoda tek bir `permissions` bloğu, tek bir `PreToolUse` hook'u, tek bir
skill `disallowed-tools` alanı yoktu. CLAUDE.md ise "deny path'leri bağlam
değil mekanizmadır — hook/permission katmanında uygulanır" diyordu.

Bu testler o boşluğun kapandığını ve KAPANMIŞ KALDIĞINI zorlar.

Kapsam dürüstlüğü (bu dosyanın da sınırı): izin katmanı MUTLAK yasakları
engeller (secret/credential okuma-yazma, yetki genişletme). Kabuk üzerinden
yazımı ENGELLEMEZ — onun karşılığı önleme değil TESPİT'tir (bin/anlik.py,
M2). Bunu "capability enforcement tamamlandı" diye sunmak, tam da
düzeltmeye çalıştığımız hatanın kendisi olurdu.
"""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


yetki = _load("yetki")
risk = _load("risk")


class PolitikaTest(unittest.TestCase):
    def setUp(self):
        self.deny = set(yetki.politika()["permissions"]["deny"])

    def test_secret_yollari_hem_read_hem_edit_kapatir(self):
        """Read deny Edit/Write'ı kapsar ama NotebookEdit'i KAPSAMAZ.

        Resmî sözleşme (code.claude.com/docs/en/permissions): "A Read deny
        rule also blocks the Edit and Write tools on the same path…
        NotebookEdit isn't covered, so add an Edit deny rule." Yalnız Read
        yazmak, .ipynb üzerinden sessiz bir yol bırakırdı.
        """
        for desen in ("**/.env", "**/secrets/**", "**/*.pem"):
            self.assertIn(f"Read({desen})", self.deny)
            self.assertIn(f"Edit({desen})", self.deny)

    def test_write_kurali_YAZILMAZ(self):
        """`Write(path)` kuralı kabul edilir ama HİÇ DANIŞILMAZ.

        Claude Code onu okur, uyarı basar ve yok sayar. Yazmak, korunduğunu
        sanmak demektir — bu dosyanın var oluş sebebi tam olarak budur.
        """
        for kural in self.deny:
            self.assertFalse(kural.startswith("Write("),
                             f"{kural}: Write(path) kuralı danışılmaz, "
                             "Edit(path) kullan")

    def test_ornek_env_dosyasi_engellenmez(self):
        """`.env.example` meşrudur (AGENTS.md); deny onu kapsamamalı.

        Deny kuralı istisna TAŞIYAMAZ (resmî: "a deny rule can't carry
        allowlist exceptions"), bu yüzden desenler dar yazılır. Geniş
        `.env.*` deseni şablonu da kilitler ve kullanıcı kapıyı kapatır.
        """
        self.assertNotIn("Read(**/.env.*)", self.deny)
        self.assertNotIn("Edit(**/.env.*)", self.deny)

    def test_yetki_genisletme_yuzeyi_kapali(self):
        self.assertIn("Edit(**/.claude/settings.json)", self.deny)
        self.assertIn("Edit(**/.agents/capability-profiles/**)", self.deny)

    def test_yikici_kabuk_komutlari_kapali(self):
        for kural in ("Bash(rm -rf /*)", "Bash(git push --force*)"):
            self.assertIn(kural, self.deny)

    def test_deny_yollari_risk_py_ile_ayni_yuzeyi_anlatir(self):
        """Tek sözleşme: izin katmanı ile risk sınıflandırması ayrışamaz.

        İki liste ayrı yaşarsa biri güncellenir diğeri unutulur ve sistem
        "deny" dediği yolu merge kararında approval sayar (H. Demir'in
        çelişen-liste bulgusunun aynısı).
        """
        for ornek in yetki.YASAK_ORNEKLERI:
            self.assertEqual(risk.risk_sinifi([ornek]), "deny", ornek)


class UygulamaTest(unittest.TestCase):
    def test_settings_json_politikayi_tasiyor(self):
        """Üretilen politika repoda GERÇEKTEN kurulu olmalı."""
        with open(os.path.join(ROOT, ".claude", "settings.json"),
                  encoding="utf-8") as fh:
            veri = json.load(fh)
        deny = set((veri.get("permissions") or {}).get("deny") or [])
        beklenen = set(yetki.politika()["permissions"]["deny"])
        eksik = beklenen - deny
        self.assertFalse(eksik, f"settings.json politikadan geride: {eksik}")

    def test_hooklar_korunur(self):
        """Politika yazımı mevcut hook kaydını EZMEMELİ."""
        with open(os.path.join(ROOT, ".claude", "settings.json"),
                  encoding="utf-8") as fh:
            veri = json.load(fh)
        self.assertIn("UserPromptSubmit", veri.get("hooks", {}))
        self.assertIn("Stop", veri.get("hooks", {}))

    def _frontmatter(self, skill):
        yol = os.path.join(ROOT, ".agents", "skills", skill, "SKILL.md")
        with open(yol, encoding="utf-8") as fh:
            return fh.read().split("---")[1]

    def test_yazmayan_skiller_yazma_araclarini_kapatir(self):
        """Hiç dosya yazmayan skill turda yazma araçlarını kapatır."""
        for skill in yetki.YAZMAYAN_SKILLER:
            fm = self._frontmatter(skill)
            self.assertIn("disallowed-tools:", fm, skill)
            for arac in ("Write", "Edit", "NotebookEdit"):
                self.assertIn(arac, fm, f"{skill}: {arac} kapatılmamış")

    def test_rapor_yazan_skill_kapatilmaz(self):
        """`research-with-evidence` rapor yazar; toptan kapatmak onu kırar.

        `disallowed-tools` YOL KAPSAMI ifade edemez — ya hepsi ya hiçbiri.
        Profilinin `report_path` sınırı bu katmanda uygulanamaz; karşılığı
        tespittir (tur kapısı). Bu testin varlığı, sınırın olduğundan güçlü
        gösterilmesini engeller.
        """
        fm = self._frontmatter("research-with-evidence")
        self.assertNotIn("disallowed-tools:", fm)

    def test_grilling_model_tarafindan_tetiklenemez(self):
        """Kural metinde değil mekanizmada: /grilling tek giriş (M5).

        routing.yml `not_routed` gerekçesi "giriş yalnız /grilling" diyor ama
        Claude'un model-invocation yolu ayrı bir kanaldır ve frontmatter
        olmadan açık kalır.
        """
        self.assertIn("disable-model-invocation: true",
                      self._frontmatter("grilling"))

    def test_codex_ve_copilot_adaptorleri_uretilir(self):
        """Aynı profil kaynağından diğer motorların politikası da çıkar."""
        cikti = yetki.uret_motorlar()
        self.assertIn(".codex/config.toml", cikti)
        self.assertIn("sandbox_mode", cikti[".codex/config.toml"])
        self.assertIn("approval_policy", cikti[".codex/config.toml"])
        self.assertIn(".github/hooks/auras.json", cikti)
        json.loads(cikti[".github/hooks/auras.json"])   # geçerli JSON olmalı


if __name__ == "__main__":
    unittest.main()
