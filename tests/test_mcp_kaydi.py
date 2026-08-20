#!/usr/bin/env python3
"""MCP sunucuları skill'lerle AYNI yönetime tabi olmalı.

Denetim ölçümü (2026-08-16): 5 MCP sunucusu `~/.claude.json`'da kuruluydu —
yani KULLANICININ MAKİNESİNE bağlı, repoya değil. Sonuçları:
  - bağlı projeye (`/auras`) hiçbiri gitmiyordu,
  - hangi görev sınıfının hangi sunucuyu kullanabileceği tanımsızdı,
  - profil `network.mode: allowlist` diyordu ama MCP ağ erişiminin ANA
    yoludur ve profillerde tek satır MCP yoktu,
  - `bin/araclar.py:35` tarayıcı MCP'sini tıklama kanıtı sayıyordu ama o
    sunucu hiç yapılandırılmamıştı — mimaride var, sistemde yok.

Skill'lerin üç katmanı vardı: kanonik kaynak · profil sınırı · bekçi.
Bu dosya aynı üçünü MCP için zorlar. Kural tek cümle: **kayıtsız sunucu
yapılandırılamaz, profilsiz sunucu kayıtta duramaz.**
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir, yaml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAYIT = os.path.join(ROOT, ".agents", "mcp.yml")


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


yetki = _load("yetki")
# Sınıf listesi TEK kaynaktan (bin/dogrula_sema.py) — bu dosya
# kümeyi ayrıca yazınca dördüncü kopya oluyordu.
dogrula_sema = _load("dogrula_sema")


@pyyaml_gerekir
class McpKaydiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(KAYIT, encoding="utf-8") as fh:
            cls.kayit = yaml.safe_load(fh) or {}
        cls.sunucular = cls.kayit.get("sunucular") or []

    def test_kayit_var_ve_bos_degil(self):
        self.assertTrue(self.sunucular,
                        ".agents/mcp.yml boş — MCP yönetilmiyor demektir")

    def test_her_sunucu_amac_tasir(self):
        """Amaçsız sunucu, niye bağlı olduğu unutulan sunucudur."""
        for s in self.sunucular:
            self.assertTrue((s.get("amac") or "").strip(),
                            f"{s.get('ad')}: 'amac' yok")

    def test_her_sunucu_gorev_sinifina_bagli(self):
        """Hangi sınıfın kullanabileceği yazılmadan izin sınırı olmaz."""
        gecerli = set(dogrula_sema.GOREV_SINIFLARI)
        for s in self.sunucular:
            sinif = set(s.get("task_class") or [])
            self.assertTrue(sinif, f"{s.get('ad')}: task_class yok")
            self.assertTrue(sinif <= gecerli,
                            f"{s.get('ad')}: geçersiz sınıf {sinif - gecerli}")

    def test_her_sunucu_calisma_bicimini_beyan_eder(self):
        """`tur`: yerel (stdio, repo üretir) mi, uzak (OAuth) mu.

        Ayrım 2026-08-16'da eklendi. Öncesinde uzak connector'lar
        `.mcp.json`'a KAZAYLA düşmüyordu: `komut` alanları olmadığı için
        üreticinin koşuluna takılmıyorlardı. Sessiz doğruluk sözleşme
        değildir — alan bir gün varsayılan alsa, kimlik doğrulamalı bir SaaS
        sessizce repo yapılandırmasına inerdi.
        """
        for s in self.sunucular:
            self.assertIn(s.get("tur"), ("yerel", "uzak"),
                          f"{s.get('ad')}: `tur` yerel|uzak olmalı")

    def test_uzak_sunucu_repo_yapilandirmasina_INMEZ(self):
        """Uzak connector oturum düzeyindedir; repo onu üretemez.

        Kayıt onu YÖNETİR (amaç, sınıf, ağ beyanı, profil sınırı) ama
        `.mcp.json`'a yazmaz — yazsaydı motor, kuramayacağı bir şeyi kurmuş
        gibi görünürdü.
        """
        uretilen = yetki.mcp_politikasi(ROOT)["mcpServers"]
        for s in self.sunucular:
            if s.get("tur") == "uzak":
                self.assertNotIn(s["ad"], uretilen,
                                 f"{s['ad']}: uzak sunucu .mcp.json'a düşmüş")

    def test_uzak_sunucu_tasinabilir_olamaz(self):
        """Taşınacak bir yapılandırma YOK — `tasinabilir: true` yalan olurdu."""
        for s in self.sunucular:
            if s.get("tur") == "uzak":
                self.assertFalse(s.get("tasinabilir"),
                                 f"{s['ad']}: uzak sunucu taşınabilir olamaz")

    def test_her_sunucu_ag_erisimini_beyan_eder(self):
        """`network.mode: allowlist` iddiasının MCP ayağı."""
        for s in self.sunucular:
            self.assertIn(s.get("ag"), ("yerel", "allowlist", "acik"),
                          f"{s.get('ad')}: geçersiz/eksik 'ag' beyanı")

    def test_kayitsiz_sunucu_kaydi_reddedilir(self):
        """not_kayitli girdisi GEREKÇE taşımak zorunda (routing.yml deseni)."""
        for s in self.kayit.get("not_kayitli") or []:
            self.assertTrue((s.get("reason") or "").strip(),
                            f"{s.get('ad')}: kasten dışarıda ama gerekçesiz")

    def test_profil_sinirinin_disinda_sunucu_yok(self):
        """Kayıttaki her sunucu en az bir profilde izinli olmalı."""
        izinli = set()
        for veri in yetki.profiller(ROOT).values():
            izinli.update(veri.get("mcp") or [])
        for s in self.sunucular:
            self.assertIn(s["ad"], izinli,
                          f"{s['ad']}: hiçbir capability profilinde yok — "
                          "ulaşılamayan izin, olmayan sınırdır")

    def test_profildeki_her_sunucu_kayitli(self):
        """Ters yön: profil kayıtta olmayan sunucu adı taşıyamaz."""
        kayitli = {s["ad"] for s in self.sunucular}
        for sinif, veri in yetki.profiller(ROOT).items():
            for ad in veri.get("mcp") or []:
                self.assertIn(ad, kayitli,
                              f"profil {sinif}: '{ad}' mcp.yml'de kayıtlı değil")

    def test_uretici_gecerli_mcp_json_uretir(self):
        """Tek kaynaktan motor yapılandırması — ve GEÇERLİ biçimde.

        Claude Code `command`/`args` bekler. Metadata yazmak, başlatılamayan
        bir sunucu tanımı üretirdi: "yapılandırdım" denip çalışmayan kurulum.
        """
        cikti = yetki.mcp_politikasi(ROOT)
        self.assertIn("mcpServers", cikti)
        kayitli = {s["ad"] for s in self.sunucular}
        for ad, tanim in cikti["mcpServers"].items():
            self.assertIn(ad, kayitli)
            self.assertTrue(tanim.get("command"), f"{ad}: command yok")
            self.assertIsInstance(tanim.get("args"), list, f"{ad}: args liste değil")

    def test_tasinamayan_sunucu_uretilmez(self):
        """Makineye özel mutlak yol PUBLIC repoya yazılmaz."""
        cikti = yetki.mcp_politikasi(ROOT)["mcpServers"]
        for s in self.sunucular:
            if not s.get("tasinabilir"):
                self.assertNotIn(s["ad"], cikti,
                                 f"{s['ad']}: taşınamaz ama üretildi")

    def test_uretilen_komutta_mutlak_yol_yok(self):
        """Sızıntı bekçisi: /Users/... gibi yol .mcp.json'a giremez."""
        for ad, tanim in yetki.mcp_politikasi(ROOT)["mcpServers"].items():
            hepsi = " ".join([tanim["command"], *tanim["args"]])
            self.assertNotIn("/Users/", hepsi, f"{ad}: mutlak yol sızıyor")
            self.assertNotIn(os.path.expanduser("~"), hepsi, ad)

    def test_tiklama_kaniti_ureten_sunucu_isaretli(self):
        """`araclar.py` tarayıcı MCP'sini kanıt sayıyor; kayıt bunu bilmeli.

        İşaret yoksa kapı "tıklama kanıtı yok" derken hangi sunucunun o
        kanıtı üretebileceğini kullanıcıya söyleyemez.
        """
        kanitci = [s["ad"] for s in self.sunucular if s.get("kanit") == "ui"]
        self.assertTrue(kanitci,
                        "hiçbir sunucu 'kanit: ui' taşımıyor — kapı tıklama "
                        "kanıtı isterken çareyi gösteremez")

    def test_codex_config_yok_sayilan_anahtar_tasimaz(self):
        """Üretilen Codex yapılandırması motorca KABUL edilmeli.

        Ölçüldü 2026-08-16: ilk üretim `[profiles.*]` bloğu yazıyordu ve
        Codex onu proje-yerel olarak REDDEDİYORDU —
          "Ignored unsupported project-local config keys ...: profiles."
        Yani dosya vardı, hiçbir şey yapmıyordu. Yok sayılan anahtar yazmak,
        yapılandırdığını sanmaktır; bu sistemin kapatmaya çalıştığı hata
        sınıfının ta kendisi.

        Bekçi metin düzeyinde: `profiles` bloğu üretilirse test düşer.
        (Codex CLI'ı testte koşturmak dış bağımlılık olurdu; ölçüm bir kez
        yapıldı ve sonucu buraya sabitlendi.)
        """
        icerik = yetki.uret_motorlar(ROOT)[".codex/config.toml"]
        for satir in icerik.splitlines():
            self.assertFalse(
                satir.strip().startswith("[profiles"),
                "üretilen config.toml proje-yerel reddedilen `[profiles.*]` "
                "bloğu taşıyor — yapılandırdığını sanmak")
        # Gerçekten geçerli olanlar duruyor mu (boş dosya da 'uyarısız'dır)
        for anahtar in ("approval_policy", "sandbox_mode",
                        "[sandbox_workspace_write]"):
            self.assertIn(anahtar, icerik)

    def test_hafiza_sunucusu_otorite_sanilmaz(self):
        """AGENTS.md hafıza hiyerarşisi: MCP hafızası 3. katmandır.

        Kayıt bunu AÇIKÇA söylemeli; yoksa dördüncü bir otorite doğar ve
        'kalıcılaştırma yalnız reviewed PR ile olur' kuralı sessizce delinir.
        """
        for s in self.sunucular:
            if "memory" in s["ad"] or "hafiza" in s["ad"]:
                self.assertIn("disposable", (s.get("amac") or "").lower(),
                              f"{s['ad']}: hafıza otoritesi sınırı yazılmamış")


if __name__ == "__main__":
    unittest.main()
