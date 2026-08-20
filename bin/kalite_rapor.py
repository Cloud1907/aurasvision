#!/usr/bin/env python3
"""Kalite ölçümünün İNSAN raporu — ölçmek ile anlatmak ayrı işlerdir.

Neden `kalite.py`'den ayrı: orası ÖLÇER ve ratchet hükmünü verir; burası o
hükmü anlatır. Ayrım ölçüyle geldi — eşiğe yakınlık uyarısı eklenince
`kalite.py` 353'ten 381 satıra çıktı ve kendi uyardığı %95 bandına girdi.
Kendi ölçüsüne göre regresyon üreten bir araç, ölçüsünü savunamaz.

Buradaki hiçbir fonksiyon karar vermez ve çıkış kodu döndürmez; girdi
`kalite.olc()` raporudur, çıktı stdout'tur.
"""
import marj

def sayac_yaz(rapor, taban):
    """Kapsam + sayaç tablosu (ratchet kararından bağımsız)."""
    kap = rapor["kapsam"]
    print(f"KALİTE: {kap['kod_dosyasi']} kod dosyası "
          f"({kap['fonksiyon_analizli']} fonksiyon-analizli, "
          f"{kap['yalniz_satir_sayilan']} yalnız satır sayıldı)")
    for k, v in sorted(rapor["sayaclar"].items()):
        t = "—" if taban is None else taban.get(k, 0)
        isaret = "✗" if (taban is not None and v > taban.get(k, 0)) else " "
        print(f"  {isaret} {k:20} {v:4}   (taban: {t})")


def ratchet_yaz(taban, taban_b, kotu, buyuyen):
    """Ratchet hükmü — ne ihlal edildi, okuyucu ne yapmalı."""
    if taban is None:
        print("\n  Taban yok — ratchet kapalı. Kur: python3 bin/kalite.py --baseline")
    elif kotu:
        print("\n  RATCHET İHLALİ — sayaç tabanın üstüne çıktı:")
        for k, a, b in kotu:
            print(f"    {k}: {a} → {b}")
        print("  Ya borcu geri al ya da tabanı bilinçli yükselt "
              "(gerekçesini commit mesajına yaz).")
    if buyuyen:
        print("\n  RATCHET İHLALİ — mevcut borç BÜYÜDÜ (sayaç değişmese de):")
        for k, a, b in buyuyen:
            print(f"    {k}: {a} → {b}")
        print("  Borcu büyütmek, onu kabul etmekle aynı şey değildir.")
    elif taban is not None and taban_b is None:
        # Sessiz korumasızlık yok: eski taban biçimi büyüme kontrolünü
        # kapatır ve bunu SÖYLEMEK zorundayız.
        print("\n  UYARI: taban 'buyuklukler' alanını taşımıyor — mevcut "
              "borcun BÜYÜMESİ ölçülemiyor. Tazele: python3 bin/kalite.py --baseline")


def bulgu_yaz(rapor):
    """İhlaller, sonra eşiğe yakın olanlar (ikincisi UYARI, ihlal değil)."""
    for b in rapor["bulgular"][:12]:
        print(f"    {b['dosya']}:{b['satir']}  [{b['tur']}]  {b['detay']}")
    if len(rapor["bulgular"]) > 12:
        print(f"    … {len(rapor['bulgular']) - 12} bulgu daha (--json)")
    for satir in marj.satirlar([tuple(y.values()) for y in rapor["yaklasan"]]):
        print(satir)
