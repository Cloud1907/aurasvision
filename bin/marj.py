#!/usr/bin/env python3
"""Eşiğe YAKIN ölçümler — duvarı çarpmadan görmek.

Ratchet yalnız eşik AŞILDIĞINDA konuşur. Bu doğru bir kapı davranışıdır ama
kötü bir uyarı davranışıdır: katkıcının aldığı ilk sinyal, kırılmış kapı olur
ve bu neredeyse her zaman ilgisiz bir değişikliğin ortasına denk gelir.

ÖLÇÜM 2026-08-16 — bu modül tahminle değil, iki kazayla doğdu:
  · `bin/incele.py` 400/400'deyken bir kırpma düzeltmesi onu 407'ye çıkardı;
    acil hata düzeltmesi ile zorunlu refactor aynı PR'a sıkıştı.
  · Aynı gün `bin/kernel_dosyalari.py` 400/400'e dayandı — bu kez tek satırlık
    bir manifest kaydı yüzünden.
  · Tarama: 13 dosya %85-100 bandında, `bin/route.py` 399/400.

SINIF: bu bir PUSULADIR, kapı değil (AGENTS.md ayrımı). Çıkış kodunu asla
değiştirmez. Uyarıyı bloklamaya çevirmek, eşiği sessizce 380'e indirmek
demektir; o karar ADR ister. Bekçi: tests/test_marj.py.

Neden ihlal edenler LİSTEDE YOK: onları ratchet zaten söylüyor. İki kez
söylemek, uyarıyı gürültüye çevirir ve gürültü okunmaz.
"""
import os

# %95: ölçüldü. %85 bandı 36 öğe (okunmaz), %95 bandı 11 öğe verdi.
# Dosya için ~20 satırlık, fonksiyon için ~2 satırlık ön haber demek.
BANT = 0.95


def _olcumler(kok, esik):
    """(tur, kimlik, deger, limit) — dosya ve fonksiyon ölçüleri, ham.

    `kalite` GEÇ import edilir: `kalite.main` bu modülü çağırır, modül
    seviyesinde import etmek döngü kurardı.
    """
    import kalite

    for yol in sorted(kalite.kod_dosyalari(kok)):
        rel = os.path.relpath(yol, kok)
        try:
            with open(yol, encoding="utf-8", errors="replace") as fh:
                satirlar = fh.read().splitlines()
        except OSError:
            continue
        yield "buyuk_dosya", rel, len(satirlar), esik["max_dosya_satir"]

        uzanti = os.path.splitext(yol)[1]
        if uzanti == ".py":
            fonklar = kalite.py_fonksiyonlar(satirlar)
        elif uzanti in kalite.SUSLU:
            fonklar = kalite.suslu_fonksiyonlar(satirlar)
        else:
            continue
        for satir, uzunluk, dal in fonklar:
            kimlik = f"{rel}:{satir}"
            yield ("uzun_fonksiyon", kimlik, uzunluk,
                   esik["max_fonksiyon_satir"])
            yield "karmasik_fonksiyon", kimlik, dal, esik["max_dal"]


def bul(kok, esik, bant=BANT):
    """[(oran, tur, kimlik, deger, limit)] — banda giren, İHLAL ETMEYEN ölçümler.

    Sıra en acilden: tam eşikte duran (oran 1.0) başa gelir. Limit dâhildir —
    `deger == limit` ihlal DEĞİLDİR (kapı `> limit` arar) ama duvarın ta
    kendisidir; listeden düşürmek en kritik vakayı gizlerdi.
    """
    yakin = []
    for tur, kimlik, deger, limit in _olcumler(kok, esik):
        if not limit or deger > limit or deger < limit * bant:
            continue
        yakin.append((deger / limit, tur, kimlik, deger, limit))
    # Aynı orandakiler kimliğe göre: sıra makinede tekrarlanabilir olmalı.
    return sorted(yakin, key=lambda y: (-y[0], y[2]))


def satirlar(yakin, tur_basi=2):
    """İnsan raporu satırları — TÜR BAŞINA en acil `tur_basi` öğe.

    Neden düz orana göre değil: ölçülerin çözünürlüğü çok farklı. `max_dal`
    10 olduğu için oran %10'luk adımlarla hareket eder ve "tam limitte dal"
    sık görülür; `max_dosya_satir` 400'de ise 399 gerçekten bir satır uzaklık
    demektir. Düz sıralama denendi (2026-08-16): dört adet 10/10 dal, listeyi
    doldurup `bin/route.py 399/400`'ü kapağın altında bıraktı — yani uyarı,
    tam da kendisini doğuran vakayı gizledi.

    Tavanı aşan sayı GİZLENMEZ, sayılır: sessiz kırpma "hepsi bu" diye okunur.
    """
    if not yakin:
        return []
    grup = {}
    for oge in yakin:
        grup.setdefault(oge[1], []).append(oge)
    out = [f"\n  ⚠ EŞİĞE YAKIN ({len(yakin)} öğe, ihlal değil — bilgi):"]
    gosterilen = 0
    for tur in sorted(grup):
        for _oran, _t, kimlik, deger, limit in grup[tur][:tur_basi]:
            out.append(f"    {kimlik}  {deger}/{limit}  [{tur}]")
            gosterilen += 1
    if len(yakin) > gosterilen:
        out.append(f"    … {len(yakin) - gosterilen} öğe daha (--json)")
    return out
