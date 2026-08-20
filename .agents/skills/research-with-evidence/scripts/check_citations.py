#!/usr/bin/env python3
"""Kaba kaynak sinyali — bir markdown raporda iddia cümlelerinin kaynak
(URL veya dosya:satır) taşıyıp taşımadığını ölçer.

Bu bir HAKEM değil, SİNYAL'dir: düşük oran iyi kaynaklandırmayı garanti
etmez ama yüksek oran neredeyse kesin bir sorundur (ham/kaynaksız rapor).

Kullanım:
  python3 check_citations.py rapor.md
  python3 check_citations.py rapor.md --threshold 0.2   # eşik (varsayılan 0.2)
  python3 check_citations.py rapor.md --verbose         # kaynaksız satırları listele

Çıkış kodu: kaynaksız iddia oranı eşiği aşarsa 1, altındaysa 0.

Sezgi (kaba, kasıtlı basit):
- Rapor PARAGRAF (blok) bazında taranır, satır bazında değil — böylece
  sarılmış (wrapped) bir iddianın devam satırı yanlışlıkla "kaynaksız"
  sayılmaz. Blok sınırı: boş satır, başlık, kod çiti veya yeni liste öğesi.
- Şu bloklar iddia SAYILMAZ: başlıklar, kod blokları, alıntı (>) ve tablo
  satırları, checkbox (- [ ]) öğeleri, TL;DR özeti, açık soru/meta bölümleri.
- Bir blok şu işaretlerden birini taşıyorsa "kaynaklı" sayılır:
  URL (http/https), dosya:satır (foo.py:42), commit SHA (7-40 hex),
  PR/issue (#123), güven etiketi (doğrulanmış/ikincil/spekülatif),
  ya da satır-içi kaynak-yok işareti [kaynak?] (bilinçli işaretlenmiş).
"""
import argparse
import re

URL = re.compile(r"https?://\S+")
FILE_LINE = re.compile(r"\b[\w./-]+\.\w+:\d+")
COMMIT = re.compile(r"\b[0-9a-f]{7,40}\b")
PR_ISSUE = re.compile(r"(?<![\w])#\d+\b")
# 'yorum' da geçerli bir etikettir: açıkça "bu ölçüm değil, çıkarım" demek,
# kaynaksız iddiayı ölçümmüş gibi sunmanın tam tersidir — cezalandırılmamalı.
CONF_TAG = re.compile(r"doğrulanmış|ikincil|spekülatif|\[yorum\]", re.I)
NOSRC_MARK = re.compile(r"\[kaynak\?\]", re.I)

# Komut çıktısı da birincil kaynaktır: koşulmuş bir komut + gözlenen sonuç,
# dosya:satır kadar tekrarlanabilirdir. Yalnız komutu ANMAK yetmez — sonuç
# işareti (→ / -> / exit N / HTTP N) aranır, aksi halde her araç adı geçen
# cümle "kaynaklı" sayılırdı (4cast denetimi 2026-08-06 bulgusu).
CMD_RUN = re.compile(
    r"`\s*(?:git|gh|npm|npx|node|pnpm|yarn|python3?|pytest|dotnet|bash|sh|"
    r"curl|make|go|cargo|docker|kubectl|psql|terraform)\b[^`]*`")
CMD_RESULT = re.compile(r"(?:→|->|⇒)|(?<![\w])exit\s*[=:]?\s*\d|HTTP\s*\d{3}")

# İddia SAYILMAYAN blok başlangıçları (checkbox, alıntı, tablo).
SKIP_PREFIX = ("- [", "* [", ">", "|")
# Bu başlıkların altındaki bloklar iddia sayılmaz (özet/meta/açık uç).
# Özet bölümleri iddia sayılmaz: altındaki bulguları TEKRAR ederler, kaynak
# orada durur. TL;DR zaten hariçti; eş anlamlıları eksikti (4cast raporu
# "Yönetici özeti" başlığı kullanınca özet satırları kaynaksız sayıldı).
NONCLAIM_SECTIONS = ("açık soru", "open question", "meta", "kapsam", "tl;dr",
                     "yönetici özeti", "executive summary", "özet",
                     "yöntem", "hüküm")
LIST_MARKER = re.compile(r"^(\s*(?:[-*+]\s|\d+[.)]\s))")
TLDR = re.compile(r"^\**\s*tl;?dr", re.I)


def is_citationlike(text):
    return bool(
        URL.search(text)
        or FILE_LINE.search(text)
        or PR_ISSUE.search(text)
        or CONF_TAG.search(text)
        or NOSRC_MARK.search(text)
        or COMMIT.search(text)
        or bool(CMD_RUN.search(text) and CMD_RESULT.search(text))
    )


def is_claim_block(text):
    """Kaba: yeterince uzun, düz-metin blok; işaret/özet değil."""
    s = text.strip()
    if len(s) < 25:
        return False
    if s.startswith(SKIP_PREFIX):
        return False
    if TLDR.match(s):
        return False
    if set(s) <= set("-|: "):  # yalnız tablo/ayıraç
        return False
    return True


def analyze(text):
    """Rapor'u paragraf/liste-öğesi bloklarına böl, blok bazında ölç."""
    blocks = []          # (start_line, joined_text, is_nonclaim)
    cur, cur_start = [], 0
    in_code = False
    section_nonclaim = False

    def flush():
        nonlocal cur, cur_start
        if cur:
            blocks.append((cur_start, " ".join(cur), section_nonclaim))
        cur = []

    for i, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            low = stripped.lstrip("#").strip().lower()
            section_nonclaim = any(k in low for k in NONCLAIM_SECTIONS)
            continue
        # Yeni liste öğesi ya da alıntı/tablo satırı yeni blok başlatır.
        if LIST_MARKER.match(raw) or stripped.startswith((">", "|")):
            flush()
        if not cur:
            cur_start = i
        cur.append(stripped)
    flush()

    claims = 0
    uncited = []
    for start, joined, nonclaim in blocks:
        if nonclaim or not is_claim_block(joined):
            continue
        claims += 1
        if not is_citationlike(joined):
            uncited.append((start, joined))
    return claims, uncited


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kaba kaynak sinyali ölçer.")
    ap.add_argument("report", help="markdown rapor dosyası")
    ap.add_argument("--threshold", type=float, default=0.2,
                    help="kaynaksız iddia oranı eşiği (varsayılan 0.2)")
    ap.add_argument("--verbose", action="store_true",
                    help="kaynaksız görünen satırları listele")
    args = ap.parse_args(argv)

    try:
        text = open(args.report, encoding="utf-8").read()
    except OSError as e:
        print(f"HATA: dosya okunamadı: {e}")
        return 2

    claims, uncited = analyze(text)
    if claims == 0:
        print("İddia gibi görünen cümle bulunamadı — sinyal üretilemedi.")
        return 0

    ratio = len(uncited) / claims
    print(f"İddia cümlesi (kaba): {claims}")
    print(f"Kaynaksız görünen:    {len(uncited)}")
    print(f"Kaynaksız oranı:      {ratio:.0%}  (eşik {args.threshold:.0%})")

    if args.verbose and uncited:
        print("\nKaynaksız görünen satırlar:")
        for ln, s in uncited:
            snip = s if len(s) <= 90 else s[:87] + "..."
            print(f"  satır {ln}: {snip}")

    if ratio > args.threshold:
        print("\nSONUÇ: SİNYAL — kaynaksız iddia oranı yüksek. "
              "Kaynak ekle, 'spekülatif' etiketle ya da çıkar.")
        return 1
    print("\nSONUÇ: TEMİZ — kaynak sinyali eşiğin altında "
          "(bu bir garanti değil, kaba sinyaldir).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
