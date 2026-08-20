#!/usr/bin/env python3
"""Sprint sonrası güvenlik denetiminin üç bulgusu — regresyon bekçisi.

Bulgular 2026-08-16'da kendi diff'imizde bulundu (öz-kontrol; hüküm bağımsız
incelemeye bırakıldı). Üçü de düzeltildi ve buraya kalıcı vaka olarak girdi:
ölçülen her kusur, bir daha aynı yoldan geri gelemesin diye teste bağlanır.
"""
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


yetki = _load("yetki")
anlik = _load("anlik")
kapi = _load("kapi")


class DenyKapsamiTest(unittest.TestCase):
    """MEDIUM: deny listesi .env türevlerini ve anahtar biçimlerini kaçırıyordu.

    CLAUDE.md "secret okuma-yazma engellenir" diyordu; `.env.staging` gibi
    yaygın bir dosya ENGELLENMİYORDU. Vaat edilen koruma ile uygulanan
    koruma arasındaki fark, tam da bu sistemin kapatmaya çalıştığı boşluk.
    """

    def setUp(self):
        self.deny = set(yetki.politika()["permissions"]["deny"])

    def test_env_turevleri_kapali(self):
        for orta in ("staging", "test", "prod", "dev", "local",
                     "production", "development"):
            desen = f"**/.env.{orta}"
            self.assertIn(f"Read({desen})", self.deny, desen)
            self.assertIn(f"Edit({desen})", self.deny, desen)

    def test_anahtar_bicimleri_kapali(self):
        for desen in ("**/*.p12", "**/*.pfx", "**/*.jks", "**/*.keystore",
                      "**/id_ed25519", "**/id_ecdsa", "**/id_dsa"):
            self.assertIn(f"Read({desen})", self.deny, desen)

    def test_ornek_sablon_hala_serbest(self):
        """`.env.example` meşrudur — geniş desen onu da kilitlemez."""
        for yasak in ("Read(**/.env.*)", "Edit(**/.env.*)",
                      "Read(**/.env.example)"):
            self.assertNotIn(yasak, self.deny)


class SessionYoluTest(unittest.TestCase):
    """LOW: session doğrulanmadan yol bileşeni olarak kullanılıyordu."""

    def test_traversal_denemesi_runtime_disina_cikamaz(self):
        with tempfile.TemporaryDirectory() as d:
            for kotu in ("../../ele", "../..", "a/b/c", "..", "./x"):
                yol = os.path.normpath(anlik._yol(d, kotu))
                beklenen = os.path.normpath(os.path.join(d, anlik.RUNTIME))
                self.assertTrue(
                    yol.startswith(beklenen + os.sep),
                    f"session={kotu!r} runtime dizininin dışına yazıyor: {yol}")

    def test_normal_session_bozulmaz(self):
        with tempfile.TemporaryDirectory() as d:
            yol = anlik._yol(d, "AB12cd34")
            self.assertTrue(yol.endswith("AB12cd34.json"))

    def test_bos_session_gecerli_ad_uretir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(anlik._yol(d, "///").endswith(".json"))


class RiskYuzeyiTest(unittest.TestCase):
    """LOW: kapı risk yüzeyini dosya ADINDAN çıkarıyordu, yüzeyden değil.

    Ölçüldü: `tests/test_session_izolasyonu.py` "risk yüzeyi" sayılıyor ve
    güvenlik incelemesi ZORUNLU kılınıyordu — bu turu bloklayan şey buydu.
    Yanlış pozitif kapının güvenilirliğini yakar: kullanıcı `--no-verify`
    alışkanlığı edinir, ki bu sistemin AGENTS.md'de yazılı en büyük korkusu.
    """

    def riskli(self, yol):
        return kapi.risk_yuzeyi_mi(yol)

    def test_gercek_risk_yuzeyleri_yakalanir(self):
        for yol in ("src/auth/login.py", "app/payment/checkout.py",
                    "db/migrations/001_add.sql", ".env",
                    "config/secrets/db.yml", ".claude/settings.json",
                    "bin/hooks/pre-push", "api/session_store.py",
                    "lib/token_service.ts"):
            self.assertTrue(self.riskli(yol), f"kaçırdı: {yol}")

    def test_test_ve_dokuman_yuzeyi_inceleme_zorunlu_kilmaz(self):
        for yol in ("tests/test_session_izolasyonu.py",
                    "tests/test_yetki.py",
                    "docs/token-notlari.md",
                    "docs/auth-tasarimi.md",
                    ".agents/reports/2026-08-15-denetim.md"):
            self.assertFalse(self.riskli(yol), f"yanlış pozitif: {yol}")

    def test_alt_dize_eslesmesi_yeterli_degil(self):
        """'session' geçen her yol risk yüzeyi değildir."""
        for yol in ("src/ui/SessionBanner.css", "README.md",
                    "docs/permission-notlari.md"):
            self.assertFalse(self.riskli(yol), f"yanlış pozitif: {yol}")

    def test_kapi_test_dosyasi_yuzunden_bloklamaz(self):
        """Uçtan uca: yalnız test dosyası değişen tur inceleme istemez."""
        bulgular, _sig = kapi.degerlendir([
            {"kind": "edit", "file": "tests/test_session_izolasyonu.py"},
            {"kind": "test", "cmd": "python3 -m unittest", "ok": True},
        ])
        self.assertNotIn("risk yüzeyi incelenmedi",
                         {b for _t, b, _a in bulgular})

    def test_gercek_risk_dosyasi_hala_bloklar(self):
        """Gevşetme test/doküman ile sınırlı; kaynak yüzeyi BLOK kalır."""
        bulgular, _sig = kapi.degerlendir([
            {"kind": "edit", "file": "src/auth/login.py"},
            {"kind": "test", "cmd": "python3 -m unittest", "ok": True},
        ])
        self.assertIn(("BLOK", "risk yüzeyi incelenmedi"),
                      {(t, b) for t, b, _a in bulgular})


if __name__ == "__main__":
    unittest.main()
