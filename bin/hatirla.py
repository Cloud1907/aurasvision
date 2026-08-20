#!/usr/bin/env python3
"""Hafıza çağrısı — "bunu ne zaman, neden böyle yapmıştık?"

Kullanım:
    python3 bin/hatirla.py grilling router
    python3 bin/hatirla.py --sinir 5 "kalite ratchet"

Kaynaklar otorite sırasıyla taranır (AGENTS.md hafıza hiyerarşisi):
  1. docs/decisions/ (ADR) — kanonik kararlar
  2. git log — commit konuları, tarihli iş kaydı
  3. .agents/reports/ — araştırma raporları

Bu bir KAPI değil yardımcı araçtır (ADR-0003: check_/scan_ öneki yok).
Amaç, karşılama katmanının "geçmiş kararı TARİHİYLE hatırlat" adımına
mekanizma vermek: hatırlama modelin belleğine değil kayda dayanmalı.
Eşleşme kaba (kelime-başı, Türkçe küçük harf) — sinyal aracıdır, hakem
değil: boş sonuç "geçmişte yok" DEMEK DEĞİLDİR, yalnız bu aramada
bulunamadı demektir; çıktı bunu açıkça söyler.
"""
import argparse
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR_LOWER = str.maketrans("IİĞÜŞÖÇ", "iiğüşöç")
TARIH = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def normalize(metin):
    return metin.translate(TR_LOWER).lower()


def eslesiyor(sorgu_kelimeleri, metin):
    """Sorgunun TÜM kelimeleri metinde kelime-başı geçiyorsa True."""
    m = normalize(metin)
    parcalar = re.split(r"[^0-9a-zçğıöşü_.-]+", m)
    return all(any(p.startswith(k) for p in parcalar) or k in m
               for k in sorgu_kelimeleri)


def git_kayitlari(kelimeler, sinir):
    """Eşleşen commit'ler: (tarih, 'commit kısa-sha konu')."""
    try:
        p = subprocess.run(
            ["git", "log", "--date=short", "--pretty=%ad\t%h\t%s"],
            capture_output=True, text=True, cwd=ROOT, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if p.returncode != 0:
        return []
    hits = []
    for satir in p.stdout.splitlines():
        try:
            tarih, sha, konu = satir.split("\t", 2)
        except ValueError:
            continue
        if eslesiyor(kelimeler, konu):
            hits.append((tarih, f"commit {sha}  {konu}"))
        if len(hits) >= sinir:
            break
    return hits


def _md_dosyalari(dizin):
    """Dizindeki (ad, içerik) çiftleri — okunamayan sessizce atlanır."""
    tam = os.path.join(ROOT, dizin)
    try:
        adlar = sorted(os.listdir(tam))
    except OSError:
        return
    for ad in adlar:
        if not ad.endswith(".md"):
            continue
        try:
            with open(os.path.join(tam, ad), encoding="utf-8") as fh:
                yield ad, fh.read()
        except OSError:
            continue


def _kayit(kelimeler, etiket, ad, icerik):
    """Tek dosyadan (tarih, satır) kaydı."""
    tarih_m = TARIH.search(ad) or TARIH.search(icerik)
    tarih = tarih_m.group(1) if tarih_m else "????-??-??"
    ilk = next((s.strip() for s in icerik.splitlines()
                if s.strip() and eslesiyor(kelimeler, s)), "")
    return tarih, f"{etiket} {ad}" + (f" — {ilk[:80]}" if ilk else "")


def dosya_kayitlari(kelimeler, dizin, etiket, sinir):
    """Eşleşen markdown dosyaları: (tarih, 'etiket ad — ilk eşleşen satır')."""
    hits = [_kayit(kelimeler, etiket, ad, icerik)
            for ad, icerik in _md_dosyalari(dizin)
            if eslesiyor(kelimeler, ad + "\n" + icerik)]
    return hits[:sinir]


def hatirla(sorgu, sinir=8):
    """[(tarih, satır)] — tarihe göre yeniden eskiye."""
    kelimeler = [k for k in re.split(r"\s+", normalize(sorgu)) if k]
    if not kelimeler:
        return []
    hepsi = (dosya_kayitlari(kelimeler, "docs/decisions", "ADR", sinir)
             + git_kayitlari(kelimeler, sinir)
             + dosya_kayitlari(kelimeler, ".agents/reports", "rapor", sinir))
    return sorted(hepsi, key=lambda h: h[0], reverse=True)[:sinir]


# Cümlede sık geçen ama hiçbir kaydı ayırt etmeyen kelimeler. Kısa liste
# bilinçli: eşleşme zaten kaba bir sinyal aracı, tam bir dilbilgisi değil.
DURAK = frozenset("""
ayrıca sanki olacak bence şöyle böyle başka önce sonra biraz zaten artık
yine tekrar hangi nasıl neden şimdi kadar için ile ama veya yani gibi daha
bunu şunu bunun olsun yapalım diye hepsi bütün falan filan
""".split())


def anahtarlar(metin, tetikler=(), en_fazla=3):
    """Hatırlama sorgusuna girecek kelimeler.

    Router "bu istek neyle ilgili" hesabını zaten yaptı; tetik varsa o
    kullanılır — tekrar tahmin etmek o hesabı çöpe atmaktır. Tetik yoksa
    cümlenin uzun kelimelerine düşülür: cümlenin TAMAMINI sorgu yapmak
    hiçbir şey bulmaz, çünkü hatirla() kelimelerin HEPSİNİ arar.
    """
    if tetikler:
        return list(tetikler)[:en_fazla]
    kelimeler = {k for k in re.split(r"[^0-9a-zçğıöşü]+", normalize(metin))
                 if len(k) >= 5 and k not in DURAK}
    return sorted(kelimeler, key=len, reverse=True)[:en_fazla]


def hatirla_coklu(kelimeler, sinir=3):
    """Anahtarların BİRLEŞİK sonucu — herhangi biri eşleşirse kayıt alınır.

    hatirla() kesişim arar (tüm kelimeler geçmeli); karşılama katmanı ise
    cümleyle gelir ve kesişim hep boş çıkar. Ayrı bir VEYA kapısı gerekli.
    """
    gorulen, hepsi = set(), []
    for kelime in kelimeler:
        for tarih, satir in hatirla(kelime, sinir):
            if satir in gorulen:
                continue
            gorulen.add(satir)
            hepsi.append((tarih, satir))
    return sorted(hepsi, key=lambda h: h[0], reverse=True)[:sinir]


def karsilama_kayitlari(prompt, tetikler=(), sinir=3):
    """Karşılamaya enjekte edilecek tarihli kayıtlar; hata hâlinde boş liste.

    Geniş yakalama bilinçlidir: router ASLA bloklamaz (kernel sözleşmesi).
    Hatırlama bir kolaylıktır, kapı değil — çökerse tur durmaz, hafıza susar.
    """
    try:
        return hatirla_coklu(anahtarlar(prompt, tetikler), sinir)
    except Exception:                     # noqa: BLE001 — sus, çökme
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sorgu", nargs="+", help="aranacak kelimeler")
    ap.add_argument("--sinir", type=int, default=8)
    args = ap.parse_args(argv)

    hits = hatirla(" ".join(args.sorgu), args.sinir)
    if not hits:
        print("Bu aramada kayıt bulunamadı — 'geçmişte yok' demek değildir; "
              "farklı kelimelerle dene ya da 'kaydı yok' de.")
        return 1
    for tarih, satir in hits:
        print(f"{tarih}  {satir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
