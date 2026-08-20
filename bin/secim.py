#!/usr/bin/env python3
"""Seçim ilkeleri — soru/emir ayrımı, kural puanlama, sınıf eskalasyonu.

route.py'nin akış iskeletinden ayrı tutulur: burada POLİTİKA yaşar (neye
göre seçilir), orada akış (hangi sırayla denenir). Her ilke kendi ölçülmüş
gerekçesini docstring/yorumunda taşır — politika değişikliği gerekçesiz
yapılmaz.
"""
import re

TR_LOWER = str.maketrans("IİĞÜŞÖÇ", "iiğüşöç")


def _normalize(text):
    return text.translate(TR_LOWER).lower()


def _matches(trigger, text, tokens):
    if " " in trigger:
        return trigger in text
    return any(tok.startswith(trigger) for tok in tokens)


# --- Soru turu tespiti (2026-08-07) --------------------------------------
# Bulgu: bir oturumda 12+ tur yanlış sınıflandı. "bizim hafıza tarafı
# başarılı mı?" → code-change/approval + zorunlu kernel-work; "ne
# yapmalıyız?" → implement-change. Türkçe önek eşleşmesi DOĞRU çalışıyordu
# ("yapmalıyız" ile "yap" aynı fiildir); kusur tur TİPİNİN okunmamasıydı.
#
# Soru turunda zorunlu skill dayatmak iki zarar üretir: (1) her sohbet turu
# "onay riskli iş" görünür ve gerçek approval sinyali değersizleşir,
# (2) ajan atlama gerekçesini kayda geçirmek zorunda kalır — bürokrasi.
#
# Asimetri bilinçli: yanlış "soru" ucuzdur (router zaten bloklamaz, tur
# kapısı kanıtı yine ister), yanlış "code-change/approval" gürültülüdür.
SORU_SONU = re.compile(r"\?\s*$")
SORU_EKI = re.compile(
    r"(?:^|\s)(m[ıiuü]|m[ıiuü]s[ıi]n|m[ıiuü]y[ıi]m|m[ıiuü]sunuz)\b")
SORU_BASI = re.compile(
    r"^(ne|neden|niye|nas[ıi]l|hangi|kim|ka[çc]|nerede|sence|acaba)\b")


# Cümle sınırı: soru ölçüsü METNİN TAMAMINDA değil SON cümlede aranır.
CUMLE_SINIRI = re.compile(r"[.!?;\n]+")


def soru_turu(text):
    """Bu tur bir SORU mu, yoksa iş emri mi?

    Ölçü SON cümleye bakar. 2026-08-15 ölçümü: desen metnin HERHANGİ bir
    yerinde soru eki arıyordu, dolayısıyla uzun ve açık bir iş emri içinde
    geçen tek bir retorik soru ("… sence bu yapı son hâline yakın mı?")
    zorunlu skill'i SESSİZCE düşürüyordu. Aynı iş emri, o cümle olmadan
    `research-with-evidence` alıyor, cümleyle birlikte hiçbir skill almıyordu
    (koşturularak gösterildi). Türkçede soru eki çok yaygın olduğundan bu,
    en iyi yazılmış istekleri sistematik olarak muaf kılıyordu.

    Son cümle ölçüsü doğru olan: bir metin ne İLE BİTİYORSA onu ister.
    "Raporu yaz. Sence doğru mu?" → son cümle soru ama iş emri de var;
    bu durumda soru sayılır ve router zorunluluk dayatmaz — asimetri
    bilinçli (yanlış "soru" ucuz, yanlış "approval" gürültülü).
    """
    cumleler = [c.strip() for c in CUMLE_SINIRI.split(text) if c.strip()]
    son = cumleler[-1] if cumleler else text.strip()
    return bool(SORU_SONU.search(text.strip()) and _soru_isareti_sonda(text)
                or SORU_EKI.search(son) or SORU_BASI.match(son))


def _soru_isareti_sonda(text):
    """Metin soru işaretiyle mi bitiyor (tek cümlelik saf soru)."""
    return text.rstrip().endswith("?")


def _puanla(cfg, text, tokens, explicit):
    """(tetik-puanlı kurallar, açık komutun kuralları) — ikisi de sıralı.

    Aynı skill birden çok kuralda olabilir (implement-change hem code-change
    hem incident). Açık /komut ilk eşleşende dururken diğeri ERİŞİLEMEZ
    kalıyordu; bağlam (tetik isabeti) seçsin.
    """
    scored, komut = [], []
    for rule in cfg.get("rules", []):
        hit = [t for t in rule.get("triggers", [])
               if _matches(_normalize(t), text, tokens)]
        spec = rule.get("specificity", 1)
        if explicit and explicit == rule.get("skill"):
            komut.append((len(hit), spec, rule, hit))
        if hit:
            scored.append((len(hit), spec, rule, hit))
    # Puan → özgüllük → routing.yml sırası (kararlı sonuç). Sınıf yarışı
    # burada ÇÖZÜLMEZ: olay sınıfı puanla değil eskalasyonla gelir
    # (_eskale) — sayı-tabanlı her formül ölçümde yenildi (2026-08-12).
    scored.sort(key=lambda s: (-s[0], -s[1]))
    komut.sort(key=lambda k: (-k[0], -k[1]))
    return scored, komut


def _eskale(sonuc, scored, olayda_izinli=None):
    """Olay tetiği görüldüyse sınıfı incident'a yükselt (yalnız yukarı).

    AGENTS.md: 'eskalasyon yalnız yukarı olur.' Olay, sınıflar içinde en
    yüksek bahisli olandır; tetiği varken kaç genel fiil eşleştiğinin önemi
    yoktur — sayı yarışı kazanılamaz (PR #40'ta üç turda ölçüldü). Soru
    biçimi zorunlu skill dayatmayı engeller ama SINIFI düşürmez: çökmüş
    prod hakkındaki soru da olay bağlamında ele alınır.

    Açık /komut SKILL seçimidir, SINIF seçimi değil — eskalasyon komutta da
    çalışır. Tek sınır izin sınırı: seçilen skill incident profilinde izinli
    değilse (grilling gibi read-only) kullanıcının sınıfı korunur — skill'e
    profili olmayan bir sınıf giydirilmez (inceleme bulgusu, 2026-08-12).
    """
    olay_var = any(r.get("task_class") == "incident" for _p, _s, r, _h in scored)
    if not olay_var:
        return sonuc
    task_class, primary, extras, hits, explicit = sonuc
    if task_class == "incident":
        return sonuc
    skill = (primary or {}).get("skill")
    if skill and olayda_izinli and not olayda_izinli(skill):
        return sonuc
    if primary:
        primary = dict(primary, risk="approval")
    return "incident", primary, extras, hits, explicit


def _sinirli(sonuc, profil_disi):
    """Turun NİHAİ sınıfının izin sınırını uygula (eskalasyondan sonra).

    Sınır hem ZORUNLU skill'e hem öneriye işler (inceleme 11. tur):
    süzme yalnız öneriye uygulanınca, profilinden çıkarılmış bir skill
    öneri olarak elenirken dayatma olarak geçebiliyordu — sınırın en çok
    gerektiği yerde en zayıf hâli. Profil dışı zorunluluk düşürülür
    (skill yok sayılır, istek BLOKLANMAZ: router kapı değildir).

    Profil "izin sınırı"dır (AGENTS.md); ÖNERİ de o sınıra tabidir.
    Salt-okunur tura düşen yazma kuralını "Ek skill" diye sunmak sınırı
    tavsiyeye çevirirdi (inceleme 5. tur, PR #43).

    Yalnız sistemin YÖNETTİĞİ skill süzülür: profillerde hiç geçmeyen ad
    kapsam dışıdır, dışlama değil — `profil_disinda`nın aynı üç-durum
    ayrımı. Eklenti skill'ini öneriden düşürmek router'ı kullanıcının
    aracına karşı çalıştırırdı.

    Yönetilenlik ayrımı çağırana bırakılır (`profil_disi(skill, sinif)`
    geri çağrısı) — `_eskale`nin `olayda_izinli`siyle aynı desen: politika
    burada, profil okuma route.py'de kalır.
    """
    task_class, primary, extras, hits, explicit = sonuc
    if profil_disi((primary or {}).get("skill"), task_class):
        primary = None
    extras = [s for s in extras if not profil_disi(s, task_class)]
    return task_class, primary, extras, hits, explicit
