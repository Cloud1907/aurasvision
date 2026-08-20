#!/usr/bin/env python3
"""Anma ayrımı — alıntı kullanıcının EMRİ mi, yoksa ANILAN bir metin mi?

Neden ayrı modül: `niyet.py` "bu istek mutasyon mu okuma mu" sorusunu
cevaplar; burası ondan ÖNCE gelen bir soruyu cevaplar — "bu cümlenin hangi
kısmı kullanıcının kendi emri?". İkisi ayrı değişme sebebi taşır ve ayrışma
niyet modülünü 400 satır sınırının üstüne itmişti.

Mekanik ve SINIRLI çare: cümleyi ANLAMAK bu katmanın işi değil (aynı gerekçe
grilling'in not_routed kararında da yazılı). Beyaz-liste yaklaşımı: anma
POZİTİF kanıt ister — alıntının neyin alıntısı olduğunu söyleyen bir ad ya
da fiil.
"""
import re

# route.tokenize ile aynı karakter kümesi — ayrışırlarsa eşleşme kayar.
_TOKEN_RE = re.compile(r"[0-9a-zçğıöşü_.]+")

# Tırnak/backtick içi metin ANILAN emirdir, niyet değil (inceleme 5. tur:
# "router çıktısındaki 'kodu düzelt' ifadesini incele"). Mekanik ve sınırlı
# çare — cümleyi ANLAMAK bu katmanın işi değil; aynı gerekçe grilling'in
# not_routed kararında da yazılıdır.
# Kesme işareti tuzağı: Türkçede ek ayracıdır ("router'ı", "endpoint'i").
# Açan tek tırnak bu yüzden yalnız harf/rakamla BİTİŞİK DEĞİLSE tırnak
# sayılır — yoksa "router'ı düzelt ve endpoint'i ekle" cümlesinin ortası
# alıntı sanılıp silinirdi.
_ALINTI = re.compile(
    r"(?<![0-9a-zçğıöşüA-ZÇĞİÖŞÜ])'[^']*'|\"[^\"]*\"|`[^`]*`|“[^”]*”"
    r"|‘[^’]*’")   # eğri tek tırnak (inceleme 9. tur): klavye farkı
                   # aynı cümleyi farklı sınıfa yollamamalı
# Tırnak tek başına "anma" demek DEĞİLDİR: kullanıcı kendi emrini de
# tırnaklayabilir ("auth açığını düzelt" ve yaptıklarını raporla) ve o
# istek yazmadır (inceleme 7. tur). Anma POZİTİF kanıt ister — alıntının
# neyin alıntısı olduğunu söyleyen bir ad ya da fiil. Modülün geri
# kalanıyla aynı ilke: beyaz-liste, kara-liste değil.
# Kelime SINIRI zorunlu (inceleme 8. tur): sınırsız arama "login"
# içindeki "log"u anma sanıp kullanıcının kendi emrini yok ediyordu.
# Kök + ek serbest ("ifadesini"), ama kök kelime başında olmalı; "log"
# tam kelime aranır çünkü çok kısa ve yaygın bir alt-dizedir.
# Ünlü düşmesi kökü kısaltır: metin + -i → "metni" (12. tur — kök olduğu
# gibi arandığı için anma hiç görülmüyordu). Liste tarandı: çekimde
# ünlüsünü düşüren tek ad "metin".
_ANMA_ISARETI = re.compile(
    r"\b(?:ifade|cümle|met(?:in|n)|çıktı|kelime|satır|mesaj|yorum|ibare|"
    r"terim|başlık|alıntı|diyor|geçiyor|yazıyor|deniyor)|\blog\b")


# Anma işareti alıntının KENDİ komşuluğunda aranır (inceleme 9. tur):
# tek bir işaretin metindeki bütün alıntıları silmesi, ikinci alıntıdaki
# gerçek emri yok ediyordu.
#
# Komşuluk KELİMEYLE ölçülür, karakterle değil (inceleme 10. tur):
# karakter penceresi bağlaç kısalınca ("ardından" → "sonra") işareti
# komşu alıntıya sızdırıyordu — eşik kullanıcının kelime seçimine göre
# oynayan bir kapı, kapı değildir. Ayrıca pencere noktalama sınırında
# kesilir: ";" sonrası yeni bir cümledir, önceki nitelemeyi taşımaz.
_KOMSU_KELIME = 2
# Nokta ancak kelimenin İÇİNDE değilse cümle sonudur (12. tur P1): sınır
# ham metinde arandığından "foo.py" cümleyi bölüp isteği yazmaya çeviriyordu.
_SINIR = re.compile(r"[;:!?\n]|\.(?![0-9a-zçğıöşü])")


def _anma_komsulugu(text, bas, son, sinirlar):
    """Alıntıyı niteleyebilecek komşuluk: sonrası + hemen öncesi.

    İKİ YÖN de aynı ölçüyle sınırlıdır: son/ilk iki kelime, cümle sınırı
    aşılmadan. 10. turda yalnız öncesi sınırlanmıştı; sonrası cümle
    sonuna kadar serbest kalınca uzaktaki bir işaret ("… ve yaptıklarını
    MESAJ olarak raporla") alıntıya bağlanıp kullanıcının emrini
    siliyordu (inceleme 11. tur). Niteleme yakınlıktır; asimetrik
    pencere, bir yönde sessiz bir açık demektir.
    """
    onceki_son = max((s for _b, s in sinirlar if s <= bas), default=0)
    sonraki_bas = min((b for b, _s in sinirlar if b >= son), default=len(text))
    oncesi = _kirp(text[onceki_son:bas], bas=False)
    sonrasi = _kirp(text[son:sonraki_bas], bas=True)
    return oncesi + " " + sonrasi


def _kirp(parca, bas):
    """Cümle sınırında kes, sonra baştan/sondan _KOMSU_KELIME kelime al."""
    if bas:
        kesme = _SINIR.search(parca)
        if kesme:
            parca = parca[:kesme.start()]
    else:
        son_sinir = None
        for m in _SINIR.finditer(parca):
            son_sinir = m
        if son_sinir:
            parca = parca[son_sinir.end():]
    kelimeler = [m.group() for m in _TOKEN_RE.finditer(parca)]
    secilen = kelimeler[:_KOMSU_KELIME] if bas else kelimeler[-_KOMSU_KELIME:]
    return " ".join(secilen)


def anma_var(text):
    """Metinde ANILAN (kullanıcının emri olmayan) bir alıntı var mı?"""
    return any(_anma_alintilari(text))


def _anma_alintilari(text):
    """Anma işaretiyle nitelenmiş alıntıların (başlangıç, bitiş) listesi.

    İşaret alıntının DIŞINDA aranır — alıntının kendi içindeki "ifade"
    kelimesi onu anma yapmaya yetmez, yoksa metin kendine izin verirdi
    (inceleme 8. tur).
    """
    sinirlar = [(m.start(), m.end()) for m in _ALINTI.finditer(text)]
    return [(bas, son) for bas, son in sinirlar
            if _ANMA_ISARETI.search(_anma_komsulugu(text, bas, son, sinirlar))]


def alintisiz(text):
    """ANILAN alıntıları boşlukla değiştirir (konumlar korunur).

    Anma işareti taşımayan alıntı korunur: kullanıcının kendi emrini
    tırnaklaması niyeti yok etmemeli.
    """
    parcalar = list(text)
    for bas, son in _anma_alintilari(text):
        for i in range(bas, son):
            parcalar[i] = " "
    return "".join(parcalar)
