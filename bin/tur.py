#!/usr/bin/env python3
"""İnceleme turu muhasebesi — sayaç, incelenen SHA, artımlı kapsam kararı.

Neden ayrı modül: `incele.py` merge KARARINI verir, `hukum.py` inceleyicinin
NE DEDİĞİNİ okur; burası "bu PR'da kaçıncı turdayız ve bu tur NEREYE bakmalı"
sorusunu cevaplar. Üçü ayrı değişme sebebi. (Aynı ayrım `surec.py` için de
400 satır sınırına dayanınca yapılmıştı — sınır, ayrılması gereken
sorumlulukları gösteriyor.)

Bu modül SAF: dış dünyaya dokunmaz, yalnız yorum gövdelerini okur/yazar.

Ölçüm 2026-08-12 — 9 PR'da 62 inceleme turu, tur arası medyan 16 dk, toplam
~17 saat; 62 hükmün yalnız 2'si temizdi. Her tur TÜM birikmiş diff yeniden
inceleniyordu: bir P1'i düzelten kod sonraki turun inceleme yüzeyi oluyor,
orada yeni bir P1 doğuyordu. Buradaki iki mekanizma o döngüyü kapatır.
"""
import os
import re

# Kaç tur sonra karar makinenin elinden alınır. Tavan `merge` ÜRETMEZ; yalnız
# ENGEL'i İNSAN'a çevirir — hızlandırdığı şey kararın kendisi değil, kararın
# SAHİBİNİN belirlenmesi. Ölçüm: PR #39 16 turda insan override'ıyla kapandı,
# PR #38 11 turda; ikisi de sistemin değil sabrın tavanıydı.
TUR_TAVANI = int(os.environ.get("INCELE_TUR_TAVANI", "3"))

# Sayaç ve incelenen SHA, PR yorumunun KENDİSİNDE taşınır. Yerel durum dosyası
# olsaydı agent onu silebilirdi; üstelik kapı farklı makinelerden koşuluyor.
# Marker okunamazsa sayaç SIFIRLANIR — tavan gecikir, erken gelmez: kaybolan
# kayıt fazladan inceleme yaptırır, merge açmaz.
MARKER = re.compile(
    r"<!--\s*incele\s+tur=(\d+)\s+sha=(\S+)\s+p0gecmis=([01])\s*-->")

SIFIR = {"tur": 0, "sha": "", "p0gecmis": False}


def marker_uret(tur, sha, p0gecmis):
    """Yorum gövdesine gömülen tek satırlık kayıt.

    `sha` = GERÇEKTEN incelenen commit; incelenmediyse boş geçilir ('-').
    Zaman aşımına uğrayan tur hiçbir şey incelemez, ama SHA'sı yazılırsa
    sonraki tur `degismedi_mi`'ye takılıp "önceki inceleme geçerli" der —
    OLMAYAN bir incelemeye atıf. O hâlde zaman aşımından sonra aynı commit
    bir daha incelenemez, çıkış yalnız boş commit atmaktır. Canlı ölçüm:
    kapı kendi PR'ında (#48) tur 1'de zaman aşımına uğradı, tur 2 bu yüzden
    Codex'i hiç çağırmadı. Bekçi: test_incelenmemis_sha_kaydedilmez.
    """
    return (f"<!-- incele tur={tur} sha={sha or '-'} "
            f"p0gecmis={1 if p0gecmis else 0} -->")


def marker_oku(govdeler):
    """Yorum gövdelerinden SON incele markerı (yoksa sıfır durumu)."""
    son = dict(SIFIR)
    for g in govdeler:
        m = MARKER.search(g or "")
        if m:
            son = {"tur": int(m.group(1)),
                   "sha": "" if m.group(2) == "-" else m.group(2),
                   "p0gecmis": m.group(3) == "1"}
    return son


def artimli_base(onceki):
    """Bu turun inceleyeceği diff'in başlangıcı ('' ise TAM diff).

    P0 görülmüş PR'da artımlı mod KAPALI: P0'ın gerçekten gittiğini görmek
    tam diff ister. Hız için doğruluktan vazgeçilmez — ölçümde P0, 62 turun
    yalnız 2'siydi, yani bu istisna pahalı değil.
    """
    if not onceki.get("sha") or onceki.get("p0gecmis"):
        return ""
    return onceki["sha"]


def degismedi_mi(onceki, head_sha):
    """Dal son incelemeden beri kıpırdadı mı.

    Kıpırdamadıysa yeniden inceleme YENİ bilgi üretmez; üstelik artımlı modda
    boş diff 'temiz' görünüp önceki turun bulgusunu sessizce silerdi.
    """
    return bool(onceki.get("tur") and head_sha
                and onceki.get("sha") == head_sha)
