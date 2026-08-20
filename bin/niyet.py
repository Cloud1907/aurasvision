#!/usr/bin/env python3
"""Niyet ayrımı: istek OKUMA mı MUTASYON mu? (route.py'nin 2. aşaması)

Bulgu (bağımsız inceleme, 2026-08-12, iki turda doğrulandı): tek aşamalı
kelime puanlaması salt-okunur inceleme isteğini ALAN ADLARI yüzünden yazma
yetkili işe çeviriyordu — "router, kanıt kapıları ve hafıza sistemini
eleştirel incele" 3 kernel-work tetiğiyle code-change/approval oldu;
inceleme istemindeki "düzelt" implement-change'i zorunlu kıldı.

Tasarım (incele.py iki P1 turu sonrası, PR #43): karar KONUMA değil
BİÇİME bakar ve ek analizi KARA-liste değil BEYAZ-listedir — fiil kökü
ancak bilinen POZİTİF emir/istek ekiyle sürüyorsa işaret sayılır. Böylece
isim gövdeleri ("yapısını" ≠ yap), olumsuz emir ("kod yazma"), edilgen
("eklenmesi", "düzeltilmesi") ve fiil-isimler kendiliğinden dışarıda
kalır. İki zayıf kanal ancak GÜÇLÜ okuma emri yokken mutasyon sayılır:
-mA fiil-ismi + gerek/lazım ("düzeltmemiz gerekiyor") ve şikâyet/kurulum
adları ("login çalışmıyor"). Kapı yalnız POZİTİF okuma emrinde devreye
girer; niyet BELİRSİZSE ("devreye al" gibi sözlük dışı fiil) tetik
tablosunun otoritesi aynen korunur (tur 3).

Asimetri bilinçli (soru turu kararıyla aynı, route.py): yanlış "okuma"
ucuzdur — router bloklamaz, ajan gerekirse skill'i öneriden yine yükler,
kapılar kanıtı yine ister. Yanlış "yazma" pahalıdır: approval gürültüsü
gerçek approval sinyalini değersizleştirir.

Regresyon bekçisi: tests/test_route.py (ölçülen vakalar kalıcı vakadır).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Anma ayrımı ("alıntı kullanıcının emri mi") ayrı modülde: farklı soru,
# farklı değişme sebebi (bin/anma.py).
from anma import _SINIR, alintisiz, anma_var  # noqa: E402,F401

# İngilizce işaretler AYNI listede: sistem cross-engine (Codex, Copilot)
# olduğunu iddia ediyor ve o motorların kullanıcısı İngilizce yazar. Ölçüm
# 2026-08-15: "review the security of the login endpoint" → implement-change
# + code-change/approval alıyordu (salt-okunur inceleme YAZMA sınıfına
# giriyor, security-review hiç seçilmiyordu). İngilizce çekim eki almadığı
# için kök eşleşmesi doğrudan çalışır (_POZ_EK boş devamı kabul eder).
OKU_ISARETLERI = ("incele", "araştır", "karşılaştır", "kıyasla",
                  "değerlendir", "denetle", "eleştir", "analiz", "rapor",
                  "raporla", "gözden geçir", "keşfet", "öğren", "açıkla",
                  "özetle", "listele",
                  "review", "audit", "analyze", "analyse", "investigate",
                  "compare", "explain", "summarize", "summarise", "inspect",
                  "evaluate", "explore", "document")
# Pozitif biçimde görülmesi tek başına mutasyon sayılan yazma fiilleri.
# routing.yml yazma kurallarının fiil tetikleriyle ve yaygın eş
# anlamlılarla uyumlu tutulur (incele.py P1 ×2: güzelleştir, iyileştir).
# Çok kelimeli deyimler alt-dize aranır (incele.py P1, tur 4: sözlük dışı
# "devreye al", yanındaki okuma fiiline yeniliyordu).
YAZ_FIILLERI = ("yap", "uygula", "ekle", "yaz", "düzelt", "kodla",
                "refactor", "taşı", "kaldır", "sil", "implement", "fix",
                "oluştur", "geliştir", "değiştir", "güncelle", "tasarla",
                "güzelleştir", "bağla", "çöz", "iyileştir", "hızlandır",
                "optimize", "düzenle", "birleştir", "kur", "yükselt",
                "temizle", "devreye al", "devreye sok", "hayata geçir",
                "canlıya al", "ayağa kaldır",
                # İngilizce yazma fiilleri (gerekçe: OKU_ISARETLERI notu)
                "add", "create", "build", "write", "update", "change",
                "remove", "delete", "rename", "migrate", "deploy",
                "install", "upgrade", "rewrite", "extract", "introduce",
                "enable", "disable", "replace")
# Zayıf işaretler: şikâyet/kurulum adları. Fiil çekimi taşımazlar; güçlü
# okuma işareti varsa okuma kazanır ("bu bug'ın nedenini araştır").
ZAYIF_ISARETLER = ("bug", "hata", "çalışmıyor", "bozuk", "kurulum",
                   "onboard", "sisteme al")
# route.tokenize ile aynı karakter kümesi — ayrışırlarsa eşleşme kayar.
_TOKEN_RE = re.compile(r"[0-9a-zçğıöşü_.]+")

# Kök sonrası POZİTİF emir/istek ekleri (beyaz-liste; incele.py P1:
# kara-liste "yapısını"yı yap sanıyordu). Sırayla: yalın emir, -(y)AlIm,
# -(y)AyIm, -(y)In(Iz), -mAlI…, -mAk, -sIn…, -(y)Abil…
#
# Eşleşmeyen her devam işaret DEĞİLDİR. Bilinçli olarak DIŞARIDA:
# geçmiş zaman -DI ve sıfat-fiil -DIğ ("eklediğimiz kod" tamamlanmış işi
# anlatır, tur 3) ile 3. şahıs şimdiki/gelecek zaman ("dosya oluşturuyor",
# "config'i değiştirecek" kodu TARİF eder, tur 4). Şimdiki/gelecek zaman
# yalnız 1. şahısta iş beyanıdır: "cache ekliyoruz", "yeniden yazacağız".
_POZ_EK = re.compile(
    r"^(?:"
    r"|y?[ae]l[ıi]m(?:[ıi]z)?"
    r"|y?[ae]y[ıi]m"
    r"|y?[ıiuü]n(?:[ıiuü]z)?"
    r"|[ıiuü]yor(?:um|uz)"
    r"|y?[ae]c[ae]ğ[ıi][zm]"
    r"|m[ae]l[ıi]\w*"
    r"|m[ae]k"
    r"|s[ıiuü]n\w*"
    r"|y?[ae]bil\w*"
    r")$")
# Ünlüyle biten kök -Iyor önünde son ünlüsünü düşürür: ekle → "ekliyoruz".
# Kök eşleşmesi bunu görmezse 1. şahıs biçimi hiç yakalanmaz.
_UNLU = "aeıioöuü"
_DUSMUS_EK = re.compile(r"^[ıiuü]yor(?:um|uz)$")
# -mA fiil-ismi + iyelik: "düzeltmem(iz)", "düzeltmesi", "düzeltmeleri".
# Tek başına işaret değildir; gerek/lazım ile birlikte iş talebidir.
# Çıplak -ma/-me (olumsuz emir "yazma") bilinçli olarak DIŞARIDA.
_VN_EK = re.compile(r"^m[ae](?:m|m[ıiuü]z|n|n[ıiuü]z|s[ıi]|l[ae]r[ıi])$")


# Birleşik fiil: "analiz yap" gibi kalıplarda anlamı AD taşır, "yap"
# yalnız yardımcıdır — istek okumadır (inceleme 6. tur: "login akışının
# güvenlik analizini yap" yazma sayılıp approval üretiyordu). Yalnız
# yardımcının ÖNÜNDEKİ ad okuma adıysa geçerlidir: "stres testi yap" ve
# "düzeltmeyi yap" iş emri olarak kalır.
HAFIF_FIILLER = ("yap", "gerçekleştir")
OKUMA_ADLARI = ("analiz", "inceleme", "denetim", "araştırma",
                "değerlendirme", "tarama", "karşılaştırma", "kıyaslama",
                "gözden geçirme", "keşif", "özet")
# Ad kökünden sonra YALNIZ ad çekimi gelebilir (hâl/iyelik/çoğul). Önek
# eşleşmesi yetmez: "analizör" türemiş bir ADDIR, "analiz" değil — ve
# "statik analizör yap" gerçek bir geliştirme emridir (inceleme 7. tur).
# Kaynaştırma ünsüzü (y/n/s) ünlüyle biten adda zorunludur: araştırma +
# -ı → "araştırmayı" (inceleme 8. tur — onsuz salt-okunur istek yazma
# sayılıyordu). Türemiş ad hâlâ dışarıda kalır: "analizör" → "ör".
_AD_EK = re.compile(
    r"^(?:[yns]?[ıiuü]n?[ıiuü]?|"
    r"[ıiuü]?[mn][ıiuü]z[ıiuü]?|l[ae]r[ıiuü]?(?:n[ıiuü])?)?$")
#            ^ -imiz/-imizi, -iniz/-inizi (ünsüzle biten: "analizinizi")
#              ve ünlüyle bitende kaynaştırmalı -niz/-nizi
#              ("incelemenizi", "araştırmanızı" — 9. ve 10. tur)
#
# Ayrılma/bulunma/yönelme hâli (-dAn/-dA/-A) BİLİNÇLİ olarak dışarıda
# (inceleme 11. tur): birleşik fiilin nesnesi yalın ya da belirtme
# hâlindedir. "analizDEN sonra düzeltmeyi yap" cümlesinde ad, "yap"ın
# nesnesi değil zaman belirtecidir — istek gerçek bir iş emridir.


def _okuma_adi_mi(tokenlar, i):
    """tokenlar[i] (ve gerekirse öncesi) bir okuma adı mı?

    Çok kelimeli ad ("gözden geçirme") tek token'la karşılaştırılamaz;
    kural yazılmıştı ama HİÇ eşleşmiyordu (inceleme 7. tur). Ad, son
    kelimesiyle eşleşir ve önceki kelime(ler) birebir aranır.
    """
    tok = tokenlar[i].group()
    for ad in OKUMA_ADLARI:
        *bas, son_kelime = ad.split()
        if not (tok.startswith(son_kelime)
                and _AD_EK.match(tok[len(son_kelime):])):
            continue
        if not bas:
            return True
        if i >= len(bas) and all(
                tokenlar[i - len(bas) + k].group() == bas[k]
                for k in range(len(bas))):
            return True
    return False


# Ad ile yardımcı fiil arasına niteleyici girebilir ("analizini DETAYLI
# yap") — hemen-ardındalık şartı bu doğal cümleyi yazma sayıyordu
# (inceleme 10. tur). Pencere dar tutulur: uzaktaki fiil birleşik fiil
# değildir ("analiz raporunu oku ve testleri yap" iş emri kalır).
_ARAYA_GIREN = 2


def _hafif_fiil_yerleri(text):
    """Okuma adının ardındaki yardımcı fiillerin (başlangıç, bitiş).

    Ad ile yardımcı AYNI cümlede olmalıdır (inceleme 12. tur): pencere
    noktalamayı aşınca "araştırma tamam; migration yap" okuma sayılıyordu.
    Ölçü alıntı bağlamasıyla aynı (_SINIR) ve HAM metin diliminde aranır —
    nokta token'a yapışır ("tamam."), token aralığı onu kaçırırdı.
    """
    tokenlar = list(_TOKEN_RE.finditer(text))
    yerler = []
    for i in range(1, len(tokenlar)):
        simdi = tokenlar[i]
        if not any(simdi.group().startswith(f) and
                   _POZ_EK.match(simdi.group()[len(f):])
                   for f in HAFIF_FIILLER):
            continue
        if any(_okuma_adi_mi(tokenlar, j)
               and not _SINIR.search(text[tokenlar[j].end():simdi.start()])
               for j in range(max(0, i - 1 - _ARAYA_GIREN), i)):
            yerler.append((simdi.start(), simdi.end()))
    return yerler


def _hafif_fiil_maskesi(text):
    """Okuma adının ardından gelen yardımcı fiili taramadan çıkarır."""
    parcalar = list(text)
    for bas, son in _hafif_fiil_yerleri(text):
        for i in range(bas, son):
            parcalar[i] = " "
    return "".join(parcalar)


def _deyim_gecer(text, deyim):
    """Çok kelimeli deyim POZİTİF emir biçiminde mi geçiyor?

    Alt-dize eşleşmesi yetmez: "devreye alınması" edilgen addır, emir
    değil (inceleme 5. tur). Son kelime fiildir; ona kök+ek analizinin
    aynısı uygulanır, öncesi birebir aranır.
    """
    *bas, fiil = deyim.split()
    onek = " ".join(bas)
    for m in re.finditer(re.escape(onek) + r"\s+([0-9a-zçğıöşü_.]+)", text):
        tok = m.group(1)
        if tok.startswith(fiil) and _POZ_EK.match(tok[len(fiil):]):
            return True
    return False


def _tara(text, isaretler):
    """(güçlü, fiil_ismi) — işaretlerin pozitif biçimde görülme bayrakları."""
    guclu = fiil_ismi = False
    for im in isaretler:
        if " " in im and _deyim_gecer(text, im):
            guclu = True
    for m in _TOKEN_RE.finditer(text):
        tok = m.group()
        for im in isaretler:
            if " " in im:
                continue
            if tok.startswith(im):
                kalan = tok[len(im):]
                if _POZ_EK.match(kalan):
                    guclu = True
                elif _VN_EK.match(kalan):
                    fiil_ismi = True
            elif (im[-1] in _UNLU and tok.startswith(im[:-1])
                  and _DUSMUS_EK.match(tok[len(im) - 1:])):
                guclu = True   # ünlü düşmesi: ekle + -iyoruz → ekliyoruz
    return guclu, fiil_ismi


def _zayif_var(text):
    """Şikâyet/kurulum adı geçiyor mu (ad — fiil morfolojisi uygulanmaz)."""
    tokens = [m.group() for m in _TOKEN_RE.finditer(text)]
    for im in ZAYIF_ISARETLER:
        if " " in im:
            if im in text:
                return True
        elif any(tok.startswith(im) for tok in tokens):
            return True
    return False


def mutasyon_niyeti(text):
    """Bu tur kod/dosya DEĞİŞTİRMEK mi istiyor? Biçim karar verir."""
    text = alintisiz(text)
    yaz, yaz_fiil_ismi = _tara(_hafif_fiil_maskesi(text), YAZ_FIILLERI)
    if yaz:
        return True
    if okuma_niyeti(text):
        return False  # güçlü okuma emri: zayıf kanallar okumaya yenilir
    if yaz_fiil_ismi and ("gerek" in text or "lazım" in text):
        return True   # "auth kontrolünü düzeltmemiz gerekiyor"
    return _zayif_var(text)


def okuma_niyeti(text):
    """Pozitif okuma emri var mı? Kapı yalnız bu doğrulanınca devreye
    girer (incele.py P1, tur 3): niyet belirsizken ("devreye al" gibi
    tanınmayan fiil) tetik tablosunun otoritesi korunur — sözlüğün
    kapsamadığı her fiili okumaya saymak zorunlu skill'i yutar.

    Birleşik fiil ("analizini yap") de POZİTİF okuma emridir: anlamı ad
    taşır, ad ise fiil morfolojisine uymaz — ayrıca sorulur.
    """
    temiz = alintisiz(text)
    return bool(_tara(temiz, OKU_ISARETLERI)[0]
                or _hafif_fiil_yerleri(temiz))


SALT_OKUNUR_VARSAYILAN = ("research",)


def kural_niyeti(rule, salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Kuralın niyet sınıfı. SALT-OKUNUR sınıf okur, gerisi yazar sayılır;
    tablo `intent` alanıyla ezer (security-review: denetim okur). Alan
    bekçisi: bin/validate.py test_routing (geçersiz değer kesilir).

    `salt_okunur` dışarıdan gelir (route.py → skill_kayit.salt_okunur_siniflar)
    çünkü kaynak profillerin KENDİ beyanıdır. Sabit "research" varsayılanı
    yalnız geriye uyum ve ölçüm yokluğu içindir — EN KISITLI hâl."""
    return rule.get("intent") or (
        "read" if rule.get("task_class") in salt_okunur else "write")


def _okuma_sinifi(rule, salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Okuma niyetinde seçilen kural salt-okunur profile iner.

    incele.py P1 (PR #43): intent:read kural code-change sınıfını
    koruyunca salt-okunur denetim yazma profili açıyordu. Skill
    zorunluluğu ve `risk` etiketi kuraldan gelir; yalnız profil iner.
    Mutasyon turunda kuralın kendi sınıfı geçerlidir (kopya cfg'yi bozmaz).

    İki yönlü kural (ADR-0005 §5):
      · Kural ZATEN salt-okunur bir sınıftaysa KENDİ sınıfı korunur. `design`
        de read-only ama chrome-devtools/Figma taşır; onu `research`e indirmek
        kuralın aracını elinden alır ve yönlendirmeyi işlevsiz bırakır.
      · Yazma sınıfındaki kural EN KISITLI salt-okunur sınıfa (`research`)
        iner — `design`e indirmek, kısıtlama adı altında dış SaaS yetkisi
        vermek olurdu. İndirme daima kısıtlar, asla genişletmez.
    """
    if rule.get("task_class") in salt_okunur:
        return rule
    return dict(rule, task_class="research")


def niyet_kapisi(text, scored, extras,
                 salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Mutasyon doğrulanmadıysa yazma kurallarını zorunluluktan düşür.

    `scored`: route.py'nin (puan, özgüllük, kural, tetikler) listesi.
    Dönüş (scored, extras): okuma niyetinde okuma kuralları öne alınır ve
    salt-okunur profile indirilir; hiç okuma kuralı yoksa scored BOŞALIR
    (route fallback'e düşer, zorunlu skill üretilmez) ve yazma
    eşleşmeleri öneri olarak extras'a taşınır. Mutasyonda ve BELİRSİZ
    niyette scored'a dokunulmaz (tablo otoritesi).
    """
    if mutasyon_niyeti(text):
        return _mutasyonda(scored, salt_okunur), extras
    if not okuma_niyeti(text):
        return _belirsizde(scored, salt_okunur), extras
    return _okumada(scored, extras, salt_okunur)


def _mutasyonda(scored, salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Mutasyon DOĞRULANDI: okuma-niyetli kural birincil olamaz.

    Simetrik kusur (eval corpus, 2026-08-15): "auth akışını değiştirmemiz
    gerekiyor" security-review'ı BİRİNCİL yapıyordu çünkü specificity 2 ile
    kazanıyordu — oysa iş uygulamadır, denetim ona EŞLİK eder. Okuma kuralı
    sıranın altına iner ve öneri olarak görünür kalır (`always_add` zaten
    onu ek skill yapar).
    """
    yazan = [s for s in scored if kural_niyeti(s[2], salt_okunur) != "read"]
    okuyan = [s for s in scored if kural_niyeti(s[2], salt_okunur) == "read"]
    return yazan + okuyan if yazan else scored


def _belirsizde(scored, salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Ne doğrulanmış mutasyon ne pozitif okuma emri → YAZMA YETKİSİ YOK.

    Skill seçimi korunur, sınıf salt-okunur profile iner. Gerekçe: yalnız
    alan adı eşleşmesiyle ("endpoint", "migration") write profili açmak,
    izin sınırını kelimeye bağlamaktır. Asimetri bu modülün başından beri
    yazılı: yanlış "okuma" ucuzdur — router bloklamaz, ajan skill'i öneriden
    yine yükler, kapılar kanıtı yine ister. Yanlış "yazma" pahalıdır.
    """
    return [(p, sp, _okuma_sinifi(r, salt_okunur), h)
            for p, sp, r, h in scored]


def _okumada(scored, extras, salt_okunur=SALT_OKUNUR_VARSAYILAN):
    """Pozitif okuma emri: okuma kuralları öne alınır ve profile indirilir.

    Hiç okuma kuralı yoksa scored BOŞALIR (route fallback'e düşer, zorunlu
    skill üretilmez) ve yazma eşleşmeleri öneri olarak extras'a taşınır.
    """
    okunur = [(p, sp, _okuma_sinifi(r, salt_okunur), h) for p, sp, r, h in scored
              if kural_niyeti(r, salt_okunur) == "read"]
    if okunur:
        yazan = [s for s in scored if kural_niyeti(s[2], salt_okunur) != "read"]
        return okunur + yazan, extras
    for _p, _sp, rule, _h in scored:
        if rule["skill"] not in extras:
            extras.append(rule["skill"])
    return [], extras
