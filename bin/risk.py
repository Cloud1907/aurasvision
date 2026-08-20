#!/usr/bin/env python3
"""Değişikliğin KENDİSİNDEN okunan iki şey: risk sınıfı ve diff güvenilirliği.

Neden ayrı modül: `incele.py` merge KARARINI verir, `hukum.py` inceleyicinin
ne dediğini okur, `tur.py` kaçıncı turda olduğumuzu sayar; burası incelemeden
ÖNCE, yalnız diff'e bakarak cevaplanan iki soruyu ayırır — "bu ne sınıf bir
değişiklik" ve "bu diff'in hükmüne güvenilir mi". İkisi de dış dünyaya
dokunmaz, ikisi de AGENTS.md politikasının kod karşılığıdır.

Bu modül SAF: gh/Codex çağrısı yok, yalnız yol listesi ve diff metni.
"""
import re

# --- Risk sınıflandırma (AGENTS.md risk politikası, path kuralı) -----------
# Eskalasyon YALNIZ yukarı: bilinmeyen yol `approval` sayılır, `auto` değil.
#
# DENY, AGENTS.md'nin deny satırının YOLDAN görülebilen kısmıdır: secret /
# credential dosyaları ve PERMISSION GENİŞLETME yüzeyleri. Bağımsız inceleme
# bulgusu (2026-08-15): politika bunları deny sayıyordu, kod approval'a
# düşürüyordu — belge koddan daha sertti, yani olmayan bir korumayı vaat
# ediyordu.
#
# "Veri silme" ve "prod migration" YOLDAN GÖRÜLMEZ; onlar aksiyondur ve
# `yikici_aksiyon` ile içerikten okunur. `migrations/` yoluna blanket deny
# BİLİNÇLE konmadı: her migration dokunuşunu break-glass'a zorlamak
# kullanıcıya kapıyı baştan atlamayı öğretir.
DENY = re.compile(
    r"(^|/)(\.env($|\.)|secrets?/|credentials?/|id_rsa|.*\.pem$|.*\.key$)"
    r"|(^|/)\.claude/settings(\.local)?\.json$"
    r"|(^|/)\.agents/capability-profiles/"
    r"|(^|/)bin/hooks/", re.I)
APPROVAL = re.compile(
    r"(auth|kimlik|oturum|session|payment|odeme|ödeme|migration|permission"
    r"|/hooks/|settings\.json|token|deploy|^bin/|^\.agents/|^\.github/"
    r"|package(-lock)?\.json$|\.csproj$|requirements\.txt$)", re.I)
AUTO = re.compile(r"(^docs/|\.md$|^tests?/|^\.agents/reports/)", re.I)


def risk_sinifi(dosyalar):
    """Değişen yollardan nihai risk sınıfı. Boş liste → approval (temkinli)."""
    if not dosyalar:
        return "approval"
    if any(DENY.search(d) for d in dosyalar):
        return "deny"
    if any(APPROVAL.search(d) for d in dosyalar):
        return "approval"
    if all(AUTO.search(d) for d in dosyalar):
        return "auto"
    return "approval"


SIRA = ("auto", "approval", "deny")


def birlestir(*siniflar):
    """En yüksek risk sınıfı — eskalasyon YALNIZ yukarı (AGENTS.md).

    Issue Form'un ÖN riski ile diff'ten okunan NİHAİ risk birleştirilmeden
    merge kararı verilemez: ikisinden yalnız birine bakmak, politikanın
    "risk iki kez hesaplanır" kuralını yarısına indirir. `incele.py` yalnız
    diff'e bakıyordu (bağımsız inceleme bulgusu, 2026-08-15).

    Tanınmayan/eksik değer `approval` sayılır, `auto` DEĞİL: bozuk ya da
    okunamayan bir contract otomatik merge üretemez (fail-closed).
    """
    en = 1                                    # varsayılan: approval
    for s in siniflar:
        en = max(en, SIRA.index(s) if s in SIRA else 1)
    return SIRA[en]


# --- Yıkıcı aksiyon (M15): yol değil İÇERİK -------------------------------
# AGENTS.md'nin deny satırının kalan iki kalemi — veri silme ve prod
# migration — bir YOL değil bir AKSİYONDUR. Yalnız EKLENEN satırlara bakılır:
# kaldırılan bir `DROP TABLE` zaten iyi haberdir.
#
# Yanlış pozitif bu kapıyı yakar: `DELETE ... WHERE` sıradan iştir, `REVOKE`
# yetki DARALTMADIR, `ADD COLUMN` güvenlidir. Kapı yalnız geri alınamaz
# olanı arar.
_YIKICI = re.compile(
    r"\bdrop\s+(table|database|schema)\b"
    r"|\btruncate\b"
    r"|\balter\s+table\b[^;]*\bdrop\s+(column|constraint)\b"
    r"|\bgrant\s+all\b"
    r"|\bchmod\s+777\b"
    r"|\"allow\"\s*:\s*\[[^\]]*\*",           # izin listesinde joker
    re.I)
# WHERE'siz DELETE: tablo boşaltmanın diğer adı.
_KOSULSUZ_DELETE = re.compile(r"\bdelete\s+from\s+\S+\s*;?\s*$", re.I)
# SQL/kabuk/dil yorumları: metin kod değildir.
_YORUM = re.compile(r"^\s*(--|#|//|/\*|\*)")


def yikici_aksiyon(diff):
    """Eklenen satırlarda geri alınamaz bir aksiyon var mı (aksiyon → deny).

    Sınır dürüstçe: bu bir SQL ayrıştırıcısı değil, desen tarayıcısıdır.
    Gizlenmiş (dinamik SQL, string birleştirme) yıkımı görmez; gördüğünü
    kanıtlar, görmediğini kanıtlamaz.

    Test fixture'ı da yakalar ve bu KABUL EDİLMİŞ bir yanlış pozitiftir
    (ölçüldü 2026-08-15: `tests/test_yetki.py` içindeki `"allow": ["Bash(*)"]`
    örneği tetikledi). Yol bazlı muafiyet BİLİNÇLE eklenmedi: `test_` adlı bir
    dosyaya konan gerçek bir yıkıcı değişiklik o muafiyetin arkasına saklanırdı.
    Sonuç yalnız "karar insana gider"dir — fail-closed tarafta kalan ucuz bir
    hata, sessiz geçen pahalı bir hataya yeğdir.
    """
    for satir in (diff or "").splitlines():
        if not satir.startswith("+") or satir.startswith("+++"):
            continue
        icerik = satir[1:]
        if _YORUM.match(icerik):
            continue
        if _YIKICI.search(icerik) or _KOSULSUZ_DELETE.search(icerik.strip()):
            return True
    return False


# Diff, inceleyiciye TALİMAT veriyorsa hüküm güvenilmez. Yalnız EKLENEN
# satırlara bakılır; doğal dil kalıbı aranır (kod/regex tanımı değil).
ENJEKSIYON = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+"
    r"(instruction|rule|prompt)"
    r"|(?:sen|you)\s+bir\s+incele|you\s+are\s+(a\s+)?review"
    r"|TEM[İI]Z\s+(olarak\s+)?(yaz|raporla|d[öo]n)"
    r"|(output|report|respond)\s+(with\s+)?(TEMIZ|CLEAN|APPROVE)"
    r"|(approve|onayla)\s+(this|bu)\s+(pr|diff|change)", re.I)


def enjeksiyon_var_mi(diff):
    """Eklenen satırlarda inceleyiciye yönelik talimat var mı."""
    for satir in (diff or "").splitlines():
        if satir.startswith("+") and ENJEKSIYON.search(satir):
            return True
    return False
