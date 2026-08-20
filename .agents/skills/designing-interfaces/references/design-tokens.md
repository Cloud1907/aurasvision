# Design token'ları — sihirli sayı yerine sistem

## İçindekiler
- Tipografi ölçeği
- Renk rolleri
- Boşluk birimi
- Köşe ve yükseklik

## Tipografi ölçeği
İki ağırlık yeter (400 + 500/600). Boyutları rastgele değil, bir orandan türet
(ör. 1.25×): 12 · 14 · 16 · 20 · 25 · 31. Gövde 16px, satır yüksekliği 1.5–1.7.
Başlık ağırlıkla değil boyut+boşlukla ayrışsın.

## Renk rolleri (renk değil, ROL tanımla)
- surface (zemin katmanları: page/card/raised)
- text (primary/secondary/muted)
- accent (tek marka rengi — her yere değil, eyleme)
- semantic (success/warning/danger — yalnız durum, dekorasyon değil)
Kural: en fazla 1 nötr rampa + 1 aksan + semantik. 6 renk = gürültü.

## Boşluk birimi
Tek taban seç (4px veya 8px), her boşluk katı olsun: 4·8·12·16·24·32·48.
Rastgele 13px, 7px yok. Tutarlı ritim premium hissin yarısıdır.

## Köşe ve yükseklik
Köşe: kontroller için tek değer (ör. 8px), kartlar 12px. Pill yalnız kasıtlıysa.
Gölge: en fazla iki seviye (hover + modal). Blur+gradient+gölge yığma.
