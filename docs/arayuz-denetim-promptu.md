# Arayüz denetim promptu

Her görünür değişiklikten sonra bu listeyle geç. "Güzel duruyor" cevap değildir:
her madde ya ölçülür ya ekran görüntüsüyle gösterilir.

## 1. Doğallık
- Ekran bir ürün gibi mi duruyor, yoksa bileşen vitrini gibi mi?
- Her öğe neden orada? Kaldırınca kullanıcı bir şey kaybetmiyorsa kaldır.
- Kaç kat kart yuvalaması var? Kart içinde kart içinde kart doğallığı bozar.
- Dar + uzun + çok yuvarlak yüzey, içerik ne olursa olsun "telefon maketi" gibi
  okunur. Yüzeyi içeriğe göre biçimlendir.
- Kocaman kart + tek küçük sayı = boşluk israfı. Yoğunluk premium, boşluk değil.
- CSS katman çürümesi: aynı bileşen beş ayrı sürüm katmanında yeniden
  tanımlanıyorsa ekran "toplama" görünür. Katmanları birleştir.

## 2. Hiyerarşi
- Göz ilk nereye gidiyor? Ekranın işi bu mu?
- En doygun renk, ekranın asıl eylemi mi? Değilse vurgu yanlış yerde.
- Başlık üç satırdan fazla kırılıyorsa kolon dar ya da punto büyüktür.

## 3. Hareket
- Hareket bilgi mi taşıyor, süs mü?
- Kaç öğe aynı anda animasyonlu? Karo başına animasyon kabul edilemez;
  tek kapsayıcı animasyonu kabul edilir.
- `prefers-reduced-motion` altında gerçekten duruyor mu? Ölç.

## 4. Dürüstlük
- Ekrandaki her şey doğru mu? Sahte "REC", sahte saat, temsili veriyi gerçek
  gibi gösteren rozet = yalan.
- Boş durum boş görünüyor mu, yoksa "çalışıyor" izlenimi mi veriyor?

## 5. Ölçülebilir kapılar
- Metin/zemin kontrastı gerçek piksellerden ölçülür; eşik 4.5 (büyük başlık 3.0).
- Yatay taşma yok: `document.documentElement.scrollWidth === viewport`.
- Görünmeyen ama klavyeyle odaklanabilen öğe sayısı 0.
- Konsol hatası 0; eksik istek 0.
- Projenin e2e paketi yeşil; kırmızıysa nedeni yazılır.

## 6. Ekran geçişi performansı
Ölçüm: `npx playwright test -c playwright.ui.config.ts -g "tüm ekran geçişleri"`
(`e2e/ui-gecis-performansi.spec.ts` — her ekranı gezer, tabloyu basar).

- Tıklamadan boyanmış ekrana kadar **600 ms** üstü geçiş kabul edilmez.
- Geçiş sırasında **250 ms**'yi aşan tek bir uzun görev bile olmamalı;
  uzun görev ana iş parçacığını kilitler, ekran donmuş hissedilir.
- Geçiş başına düzen kayması 0.1'in altında kalmalı. Üstüne çıkan ekran,
  veri geldikçe içeriği zıplatıyor demektir: yer tutucu ayır.
- Ölçüm taklit veriyle yapılır; gerçek kurulumda ağ gecikmesi eklenir.
  Bu yüzden eşikler tavan değil, taban kabul edilir.

## 7. Teslim
- Önce/sonra ekran görüntüsü.
- Ne değişti, neden değişti — tek paragraf.
- Bilerek yapılmayanlar ve sebebi.
