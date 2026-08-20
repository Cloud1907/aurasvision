#!/usr/bin/env python3
"""Capability profili → motorun GERÇEK izin politikası.

Denetimin P0'ı buydu: profil YAML'ındaki `filesystem: read-only` ve
`network.mode: allowlist` alanları hiçbir yerde uygulanmıyordu; `validate.py`
yalnız anahtarın varlığına bakıyordu. "İzin sınırı" denen şey model
talimatıydı — prompt injection ya da model hatasında hiçbir şey engellemezdi.

Bu modül profili motorun kendi mekanizmasına ÇEVİRİR:
  Claude Code → `.claude/settings.json` `permissions.deny` + skill
                `disallowed-tools`
  Codex       → `.codex/config.toml` (`sandbox_mode`, `approval_policy`)
  Copilot     → `.github/hooks/auras.json`

Kullanım:
    python3 bin/yetki.py --check     # politika güncel mi (CI/validate)
    python3 bin/yetki.py --uygula    # dosyaları üret/güncelle

KAPSAM DÜRÜSTLÜĞÜ — abartma yasak (AGENTS.md "Kapıların gerçek sınıfı"):
Bu katman MUTLAK yasakları engeller: secret/credential okuma-yazma, yetki
genişletme yüzeyi, bilinen yıkıcı kabuk komutları. ENGELLEMEDİĞİ şey, sınıf
başına değişen sınırlardır — Claude Code izinleri OTURUM genelindedir, tur
başına değişmez; `research` turunda dosya yazmayı yalnız skill'in
`disallowed-tools` alanı kapatır ve o da yalnız skill yüklüyken geçerlidir.
Kabuk üzerinden yazım hiç engellenmez; onun karşılığı önleme değil TESPİT'tir
(`bin/anlik.py`). Bu bir savunma katmanıdır, bütünlük sınırı değil.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mutlak yasak yüzeyi — gitignore deseni (Claude Code izin sözdizimi).
#
# Neden `Read(...)` VE `Edit(...)` birlikte: Read deny'ı Edit ve Write'ı da
# kapatır ama NotebookEdit'i KAPATMAZ (resmî sözleşme). Yalnız Read yazmak
# `.ipynb` üzerinden sessiz bir yol bırakırdı.
#
# Neden `Write(...)` YOK: Claude Code yalnız `Read`/`Edit` yol kurallarına
# danışır; `Write(path)` kabul edilir, uyarı basılır ve YOK SAYILIR. Yazmak,
# korunduğunu sanmaktır.
#
# Neden desenler DAR: deny kuralı istisna taşıyamaz. Geniş `**/.env.*`
# deseni `.env.example` şablonunu da kilitler (AGENTS.md onu açıkça muaf
# tutar) ve kilitlenen meşru dosya kullanıcıya kapıyı kapatmayı öğretir.
YASAK_YOLLAR = (
    "**/.env",
    # Ortam türevleri TEK TEK sayılır (öz-denetim bulgusu 2026-08-16:
    # `.env.staging` gibi yaygın bir dosya kapsam dışıydı; CLAUDE.md ise
    # "secret okuma-yazma engellenir" diyordu — vaat ile uygulama ayrışmıştı).
    # Geniş `**/.env.*` yazılamaz: `.env.example` şablonunu da kilitlerdi ve
    # deny kuralı istisna taşıyamaz.
    "**/.env.local",
    "**/.env.production",
    "**/.env.development",
    "**/.env.staging",
    "**/.env.test",
    "**/.env.prod",
    "**/.env.dev",
    "**/secrets/**",
    "**/secret/**",
    "**/credentials/**",
    "**/credential/**",
    "**/*.pem",
    "**/*.key",
    # Anahtar deposu biçimleri ve ed25519/ecdsa: id_rsa kapsanmışken
    # bunların açık kalması, aynı sınıf sırrı farklı biçimde serbest
    # bırakıyordu.
    "**/*.p12",
    "**/*.pfx",
    "**/*.jks",
    "**/*.keystore",
    "**/id_rsa",
    "**/id_ed25519",
    "**/id_ecdsa",
    "**/id_dsa",
)

# Yalnız yazma yasağı: okunması meşru, DEĞİŞTİRİLMESİ yetki genişletmedir.
YASAK_YAZMA = (
    "**/.claude/settings.json",
    "**/.claude/settings.local.json",
    "**/.agents/capability-profiles/**",
    "**/bin/hooks/**",
)

# Geri alınamaz kabuk komutları (AGENTS.md deny satırının kabuk ayağı).
YASAK_KOMUTLAR = (
    "Bash(rm -rf /*)",
    "Bash(rm -rf ~*)",
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Bash(chmod 777*)",
)

# `risk.risk_sinifi` ile aynı yüzeyi anlattığının bekçisi (tests/test_yetki).
YASAK_ORNEKLERI = (
    ".env", "config/secrets/db.yml", "certs/server.pem", "keys/app.key",
    ".claude/settings.json", ".agents/capability-profiles/research.yml",
    "bin/hooks/pre-push",
)

# Hiç dosya yazmayan skill'ler: turda yazma araçları kapatılır. Bu,
# `filesystem: read-only` beyanının tur-başına GERÇEK karşılığıdır
# (`disallowed-tools` yalnız o turda geçerlidir, sonraki mesajda düşer).
#
# `research-with-evidence` BİLİNÇLE dışarıda: profili ona `.agents/reports/`
# altına yazma izni verir (`report_path`) ve `disallowed-tools` YOL KAPSAMI
# ifade edemez — ya hepsini kapatır ya hiçbirini. Kapatmak raporu imkânsız
# kılardı. O sınırın karşılığı önleme değil tespittir: rapor dışına yazım
# tur kapısında görünür (bin/anlik.py). Sınırı olduğundan güçlü göstermemek
# için burada yazılıdır.
YAZMAYAN_SKILLER = ("security-review", "grilling")
SALT_OKUNUR_ARACLAR = "Write Edit NotebookEdit"


def profiller(kok=ROOT):
    """{task_class: profil} — profil yoksa boş sözlük."""
    try:
        import yaml
    except ImportError:
        return {}
    dizin = os.path.join(kok, ".agents", "capability-profiles")
    out = {}
    try:
        adlar = sorted(os.listdir(dizin))
    except OSError:
        return {}
    for ad in adlar:
        if not ad.endswith(".yml"):
            continue
        try:
            with open(os.path.join(dizin, ad), encoding="utf-8") as fh:
                veri = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            continue
        if veri.get("task_class"):
            out[veri["task_class"]] = veri
    return out


def salt_okunur_skiller(kok=ROOT):
    """Yalnız salt-okunur profillerde geçen skill'ler (yazma profili yok)."""
    prof = profiller(kok)
    yazanlar, okuyanlar = set(), set()
    for veri in prof.values():
        hedef = (okuyanlar if (veri.get("tools") or {}).get("filesystem")
                 == "read-only" else yazanlar)
        hedef.update(veri.get("skills") or [])
    return sorted(okuyanlar - yazanlar)


def mcp_kaydi(kok=ROOT):
    """`.agents/mcp.yml` — MCP sunucularının kanonik kaydı (yoksa boş)."""
    try:
        import yaml
    except ImportError:
        return {}
    try:
        with open(os.path.join(kok, ".agents", "mcp.yml"), encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, Exception):                          # noqa: BLE001
        return {}


def mcp_politikasi(kok=ROOT):
    """Profil sınırının İZİN VERDİĞİ sunucular → `.mcp.json` gövdesi.

    Skill'lerle aynı ilke (AGENTS.md): profil izin sınırıdır, kayıt o sınır
    içinden seçim yapar. Kayıtta olup hiçbir profilde geçmeyen sunucu
    ÜRETİLMEZ — ulaşılamayan izin, olmayan sınırdır.

    Sınır dürüstçe: Claude Code MCP yapılandırması OTURUM genelindedir, tur
    başına değişmez. Yani `mcp:` alanı hangi sınıfın hangi sunucuyu
    kullanmasının DOĞRU olduğunu söyler; motor bunu tur başına zorlayamaz.
    Zorlanan tek şey, hiçbir profilde geçmeyen sunucunun hiç üretilmemesidir.
    """
    kayit = mcp_kaydi(kok)
    izinli = set()
    for veri in profiller(kok).values():
        izinli.update(veri.get("mcp") or [])
    sunucular = {}
    for s in kayit.get("sunucular") or []:
        # UZAK sunucu ÜRETİLMEZ ve bu artık AÇIKÇA söylenir. Önceden aynı
        # sonuç KAZAYLA çıkıyordu: uzak connector'ın `komut` alanı yok, o
        # yüzden alttaki koşula takılmıyordu. Sessiz doğruluk, sözleşme
        # değildir — `komut` alanı bir gün varsayılan alırsa kimlik
        # doğrulamalı bir SaaS sessizce `.mcp.json`'a düşerdi.
        if s.get("tur", "yerel") != "yerel":
            continue
        # Taşınamayan sunucu ÜRETİLMEZ: başlatma komutu makineye özel mutlak
        # yoldur ve bu repo public'tir. Kayıtta durur (yönetim + gerekçe),
        # kurulum kullanıcının global yapılandırmasında kalır.
        if s.get("ad") in izinli and s.get("tasinabilir") and s.get("komut"):
            komut = list(s["komut"])
            sunucular[s["ad"]] = {"command": komut[0], "args": komut[1:]}
    return {"mcpServers": sunucular}


def politika(kok=ROOT):
    """Claude Code izin politikası (deny listesi)."""
    deny = []
    for desen in YASAK_YOLLAR:
        deny.append(f"Read({desen})")
        deny.append(f"Edit({desen})")
    for desen in YASAK_YAZMA:
        deny.append(f"Edit({desen})")
    deny.extend(YASAK_KOMUTLAR)
    return {"permissions": {"deny": deny}}


def uret_motorlar(kok=ROOT):
    """{göreli yol: içerik} — Codex ve Copilot adaptörleri.

    Aynı profil kaynağından üretilir: politika tek yerde yaşar, motorlar
    onun çevirisidir. Elle tutulan ikinci bir liste, ayrışmanın kendisidir.
    """
    prof = profiller(kok)
    arastirma = prof.get("research", {})
    ag = ((prof.get("code-change") or {}).get("network") or {})
    izinli = ", ".join(f'"{d}"' for d in (ag.get("domains") or []))

    # SADECE proje düzeyinde GEÇERLİ anahtarlar yazılır. Ölçüldü 2026-08-16:
    # `[profiles.*]` bloğu Codex tarafından REDDEDİLİYOR —
    #   "Ignored unsupported project-local config keys ...: profiles.
    #    If you want these settings to apply, manually set them in your
    #    user-level config.toml."
    # Yok sayılan anahtarı yazmak, yapılandırdığını sanmaktır: tam da bu
    # sistemin kapatmaya çalıştığı hata sınıfı. Bekçi: tests/test_mcp_kaydi.py
    # (üretilen dosya UYARISIZ kabul edilmeli).
    codex = f"""# ÜRETİLDİ — elle düzenleme: bin/yetki.py --uygula
# Kaynak: .agents/capability-profiles/*.yml
#
# Burada YALNIZ proje düzeyinde geçerli anahtarlar var. `[profiles.*]` Codex
# tarafından proje-yerel olarak reddedilir (ölçüldü) ve bilinçle YAZILMAZ.
# Salt-okunur araştırma profilini istiyorsan KENDİ `~/.codex/config.toml`
# dosyana ekle — bu repo senin kullanıcı ayarını değiştiremez, değiştirmemeli:
#
#   [profiles.research]          # {arastirma.get("description", "")}
#   sandbox_mode = "read-only"
#   approval_policy = "on-request"

approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
# Profil ağ sınırı: code-change allowlist ({izinli or "yok"}). Codex bunu
# boolean olarak ifade eder; allowlist ≠ açık ağ olduğundan kapalı yazılır.
network_access = false
"""

    copilot = json.dumps({
        "_uretildi": "bin/yetki.py --uygula — elle düzenleme kaybolur",
        "hooks": [{
            "event": "preToolUse",
            "run": "python3 bin/yetki.py --dogrula-yol",
            "description": "Mutlak yasak yüzeyine yazımı reddeder",
        }],
    }, ensure_ascii=False, indent=2) + "\n"

    return {".codex/config.toml": codex,
            ".github/hooks/auras.json": copilot}


def _settings_yaz(kok, pol):
    """Politikayı settings.json'a birleştir — hook kaydını EZMEDEN."""
    yol = os.path.join(kok, ".claude", "settings.json")
    try:
        with open(yol, encoding="utf-8") as fh:
            veri = json.load(fh)
    except (OSError, ValueError):
        veri = {}
    if not isinstance(veri, dict):
        return False
    izin = veri.setdefault("permissions", {})
    mevcut = izin.get("deny") or []
    yeni = [k for k in pol["permissions"]["deny"] if k not in mevcut]
    if not yeni:
        return False
    izin["deny"] = mevcut + yeni
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as fh:
        json.dump(veri, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return True


def mcp_eksikleri(kok=ROOT):
    """`.mcp.json` politikadan geride mi (drift ölçüsü)."""
    beklenen = mcp_politikasi(kok)["mcpServers"]
    try:
        with open(os.path.join(kok, ".mcp.json"), encoding="utf-8") as fh:
            mevcut = (json.load(fh) or {}).get("mcpServers") or {}
    except (OSError, ValueError):
        mevcut = {}
    eksik = [a for a in beklenen if a not in mevcut]
    # Kayıtsız sunucu yapılandırılamaz — ters yön de drift'tir.
    fazla = [a for a in mevcut if a not in beklenen]
    return eksik, fazla


def eksikler(kok=ROOT):
    """Politikanın settings.json'da BULUNMAYAN kuralları (drift ölçüsü)."""
    try:
        with open(os.path.join(kok, ".claude", "settings.json"),
                  encoding="utf-8") as fh:
            veri = json.load(fh)
    except (OSError, ValueError):
        return list(politika(kok)["permissions"]["deny"])
    mevcut = set((veri.get("permissions") or {}).get("deny") or [])
    return [k for k in politika(kok)["permissions"]["deny"] if k not in mevcut]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--uygula", action="store_true",
                    help="politikayı dosyalara yaz")
    ap.add_argument("--check", action="store_true",
                    help="politika güncel mi (drift varsa exit 1)")
    ap.add_argument("--kok", default=ROOT)
    args = ap.parse_args(argv)

    eksik = eksikler(args.kok)
    mcp_eksik, mcp_fazla = mcp_eksikleri(args.kok)
    if args.check:
        if eksik or mcp_eksik or mcp_fazla:
            print("YETKİ POLİTİKASI GERİDE:")
            for k in eksik:
                print(f"  ✗ settings.json eksik kural: {k}")
            for k in mcp_eksik:
                print(f"  ✗ .mcp.json eksik sunucu: {k}")
            for k in mcp_fazla:
                print(f"  ✗ .mcp.json KAYITSIZ sunucu: {k} — .agents/mcp.yml'e "
                      "kaydet ya da yapılandırmadan çıkar")
            print("Düzelt: python3 bin/yetki.py --uygula")
            return 1
        print(f"YETKİ: politika güncel "
              f"({len(politika(args.kok)['permissions']['deny'])} deny kuralı, "
              f"{len(mcp_politikasi(args.kok)['mcpServers'])} MCP sunucusu)")
        return 0

    if args.uygula:
        degisti = _settings_yaz(args.kok, politika(args.kok))
        print(f"  .claude/settings.json: {'güncellendi' if degisti else 'zaten güncel'}")
        mcp = mcp_politikasi(args.kok)
        if mcp["mcpServers"]:
            with open(os.path.join(args.kok, ".mcp.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(mcp, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"  .mcp.json: {len(mcp['mcpServers'])} sunucu "
                  f"({', '.join(sorted(mcp['mcpServers']))})")
        for rel, icerik in uret_motorlar(args.kok).items():
            yol = os.path.join(args.kok, rel)
            os.makedirs(os.path.dirname(yol), exist_ok=True)
            with open(yol, "w", encoding="utf-8") as fh:
                fh.write(icerik)
            print(f"  {rel}: yazıldı")
        print(f"  salt-okunur skill'ler: {', '.join(salt_okunur_skiller(args.kok)) or 'yok'}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
