#!/usr/bin/env python3
"""Risk sözleşmesi: AGENTS.md ne diyorsa kod onu yapmalı.

Bağımsız incelemenin bulgusu (2026-08-15): politika veri silmeyi, prod
migration'ı ve permission genişletmeyi `deny` sayıyor (`AGENTS.md`), ama
`bin/risk.py` DENY listesinde yalnız secret/credential yolları vardı;
`migration` ve `permission` APPROVAL'a düşüyordu. Yani yazılı politika
koddan DAHA SERT'ti — belge, olmayan bir korumayı vaat ediyordu.

İkinci bulgu: Issue Form'dan gelen ÖN risk merge kararına hiç girmiyordu
(`incele.py` yalnız değişen yollara bakıyordu). Risk "yalnız yukarı eskale
olur" kuralı ancak iki kaynak BİRLEŞTİRİLİRSE geçerlidir.

Kapsam notu (dürüstlük): yol deseni bir AKSİYONU göremez. "Veri silme" ve
"prod migration" içerik sorularıdır; onların kapısı `bin/risk.py`
`yikici_aksiyon` fonksiyonudur (M15) ve testi bu dosyanın altındadır.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


risk = _load("risk")
incele = _load("incele")


class RiskYoluTest(unittest.TestCase):
    def test_secret_yolu_deny(self):
        self.assertEqual(risk.risk_sinifi([".env"]), "deny")
        self.assertEqual(risk.risk_sinifi(["config/secrets/db.yml"]), "deny")

    def test_yetki_genisletme_yolu_deny(self):
        """Permission genişletme yolları AGENTS.md'de deny — kodda da öyle."""
        for yol in (".claude/settings.json",
                    ".agents/capability-profiles/code-change.yml",
                    "bin/hooks/pre-push"):
            self.assertEqual(risk.risk_sinifi([yol]), "deny", yol)

    def test_migration_yolu_en_az_approval(self):
        """Migration yolu tek başına deny DEĞİL — aksiyon kapısı karar verir.

        Blanket deny bilinçle SEÇİLMEDİ: her `migrations/` dokunuşunu
        break-glass'a zorlamak, kullanıcıya kapıyı baştan atlamayı öğretir
        (bu sistemin en korktuğu sonuç). Yıkıcı olan migration'ı içerikten
        yakalayan kapı `yikici_aksiyon`dur.
        """
        self.assertEqual(risk.risk_sinifi(["db/migrations/001_add.sql"]),
                         "approval")

    def test_dokuman_auto(self):
        self.assertEqual(risk.risk_sinifi(["docs/x.md", "README.md"]), "auto")

    def test_bilinmeyen_yol_approval(self):
        """Eskalasyon yalnız yukarı: tanınmayan yol auto sayılmaz."""
        self.assertEqual(risk.risk_sinifi(["garip/dosya.xyz"]), "approval")


class RiskBirlesimTest(unittest.TestCase):
    def test_yukari_eskale_olur(self):
        self.assertEqual(risk.birlestir("auto", "approval"), "approval")
        self.assertEqual(risk.birlestir("approval", "auto"), "approval")
        self.assertEqual(risk.birlestir("approval", "deny"), "deny")
        self.assertEqual(risk.birlestir("deny", "auto"), "deny")

    def test_asagi_inmez(self):
        """Ön risk yüksekse diff düşük diye aşağı İNMEZ."""
        self.assertEqual(risk.birlestir("deny", "approval"), "deny")

    def test_bilinmeyen_deger_temkinli(self):
        """Bozuk/eksik contract riski auto'ya düşüremez."""
        self.assertEqual(risk.birlestir(None, "auto"), "approval")
        self.assertEqual(risk.birlestir("saçma", "auto"), "approval")


class YikiciAksiyonTest(unittest.TestCase):
    """M15 — yol değil İÇERİK: aksiyon farkındalığı."""

    def diff(self, *satirlar):
        return "\n".join("+" + s for s in satirlar)

    def test_tablo_dusurme_yakalanir(self):
        self.assertTrue(risk.yikici_aksiyon(self.diff("DROP TABLE users;")))

    def test_truncate_yakalanir(self):
        self.assertTrue(risk.yikici_aksiyon(self.diff("truncate table orders")))

    def test_kosulsuz_delete_yakalanir(self):
        self.assertTrue(risk.yikici_aksiyon(self.diff("DELETE FROM sessions;")))

    def test_kosullu_delete_yakalanmaz(self):
        """WHERE'li silme sıradan iştir; yanlış pozitif kapıyı yakar."""
        self.assertFalse(
            risk.yikici_aksiyon(self.diff("DELETE FROM sessions WHERE id = 1")))

    def test_kolon_dusurme_yakalanir(self):
        self.assertTrue(
            risk.yikici_aksiyon(self.diff("ALTER TABLE t DROP COLUMN eski;")))

    def test_guvenli_migration_yakalanmaz(self):
        self.assertFalse(risk.yikici_aksiyon(self.diff(
            "ALTER TABLE t ADD COLUMN yeni text;",
            "CREATE INDEX ix_t_yeni ON t(yeni);")))

    def test_yetki_genisletme_yakalanir(self):
        self.assertTrue(risk.yikici_aksiyon(self.diff('"allow": ["Bash(*)"]')))
        self.assertTrue(risk.yikici_aksiyon(self.diff("GRANT ALL ON db TO app")))

    def test_yetki_daraltma_yakalanmaz(self):
        self.assertFalse(risk.yikici_aksiyon(self.diff("REVOKE ALL ON db FROM app")))

    def test_silinen_satir_sayilmaz(self):
        """Yalnız EKLENEN satırlar; kaldırılan DROP zaten iyi haberdir."""
        self.assertFalse(risk.yikici_aksiyon("-DROP TABLE users;"))

    def test_yorum_satiri_sayilmaz(self):
        self.assertFalse(risk.yikici_aksiyon(self.diff("-- DROP TABLE users;")))


class KararRiskTest(unittest.TestCase):
    """Birleşik risk merge kararına gerçekten giriyor mu."""

    TEMIZ = {"P0": [], "P1": [], "P2": []}

    def test_on_risk_deny_ise_merge_yok(self):
        k, _g = incele.karar("deny", self.TEMIZ, True, True)
        self.assertEqual(k, "engel")

    def test_auto_temizse_merge(self):
        k, _g = incele.karar("auto", self.TEMIZ, True, True)
        self.assertEqual(k, "merge")

    def test_birlesim_auto_merge_i_kapatir(self):
        """Ön risk approval ise diff auto olsa bile otomatik merge olmaz."""
        birlesik = risk.birlestir("approval", "auto")
        k, _g = incele.karar(birlesik, self.TEMIZ, True, True)
        self.assertEqual(k, "insan")


if __name__ == "__main__":
    unittest.main()
