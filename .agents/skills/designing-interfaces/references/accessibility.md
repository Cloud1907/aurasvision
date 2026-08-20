# Erişilebilirlik — kalite, dekorasyon değil

## İçindekiler
- Kontrast eşikleri
- Klavye ve odak
- Hareket
- Anlamsal yapı

## Kontrast eşikleri (WCAG 2.2)
- Normal metin: en az 4.5:1
- Büyük metin (>=24px veya >=19px bold): en az 3:1
- UI bileşen sınırı / ikon: en az 3:1
Bunu gözle tahmin etme; `scripts/contrast_check.py` ile ölç.

## Klavye ve odak
Her etkileşimli öğe klavyeyle erişilebilir; görünür focus ring (kaldırma).
Dokunma hedefi en az 44×44px.

## Hareket
Yalnız transform/opacity animasyonu (layout/paint tetikleyen top/left/width
değil) → 60fps. `prefers-reduced-motion: reduce` sorgusuyla kapat.

## Anlamsal yapı
Doğru element (button için <button>, div değil), başlık sırası (h1→h2→h3),
ikon-only butona aria-label, dekoratif ikona aria-hidden.
