# Plaka doğruluk ölçümü

> Depoda daha önce plaka modülü için **hiçbir doğruluk ölçümü yoktu** — yalnız
> `docs/olcumler-gb10.md`'de hız ölçülmüştü. Bu belge o boşluğu kapatır.
> Yöntem: `scripts/plate_eval_gt.py`.

## Yer gerçeği kaynağı

TRASSIR'ın aynı kameradan (`kamera-204` / `tN9q9YqX`) ürettiği kendi okumaları
kullanıldı — sentetik veri değil. TRASSIR'ın kendi hataları yer gerçeğine
sızmasın diye iki süzgeç uygulandı:

1. `plaka_sablonu` `tr/` ile başlamalı (TRASSIR'ın kendi format doğrulaması
   geçmiş olmalı — `plaka_sablonu="/"` olanlar TRASSIR'ın kendi hatasıdır,
   bkz. `LAAC413` vakası 2026-09-02: gerçek plaka `41ARC413`).
2. Aynı plaka en az 2 kez okunmuş olmalı.

## Ölçüm (2026-09-03, GPU'lu — CUDAExecutionProvider)

Pencere: 07:00–16:53 UTC, `kamera-204` arşivinin tamamı. 42 güvenilir geçiş,
42'si arşivde bulundu (kapsama %100).

| | |
|---|---|
| Tam isabet | **25 / 42 (%59,5)** |
| Ortalama karakter mesafesi | **0,93** (yanlış okumaların çoğu 1 karakter kayıyor) |
| Sessiz segmentte üretilen plaka | **0 / 15** — yanlış pozitif yok |

Ham dosya: `output/plate_eval_gt/plate_eval_gt.json`.

### Hataların örüntüsü

Yanlış okumaların büyük kısmı **tek karakter** farkla kayıyor
(`06EOC262→06EDC262`, `34UE1700→34UE1780`, `34TC6303→34TE6303`). Bu,
2026-09-02'de tek bir geçişte ölçülen kök nedenle tutarlı: araç uzaklaşırken
plaka 77–140 piksele düşüyor ve bulanıklaşıyor — model karakterleri
birbirine yakın harflerle (0↔D, 7↔8, C↔E) karıştırıyor.

Birkaç okuma (`34EY2333→34PMK153`, `34CPC920→34MLL972`) tamamen farklı —
muhtemelen segmentte birden fazla araç geçtiği ya da OCR'ın tümüyle
tutunamadığı bir kare.

### Sıfır sonuç veren 2 geçiş

`34BT7027` iki ayrı geçişte (16:25, 18:25) **hiç plaka üretmedi** — aynı
plaka aynı gün başka üç geçişte tam doğru okunmuştu. Muhtemel neden: o
anki kare açısı/hız farkı. Tek başına endişe verici değil (aynı plaka
başka geçişlerde çalışıyor), ama izlenmeye değer.

## Yorum

%59,5 tam isabet, ortalama <1 karakter hata ile birlikte okunduğunda "neredeyse
doğru" bir sistemi işaret ediyor — kaba bir arama/eşleştirmede (örn. "34TC630*"
gibi kısmi eşleşme) pratik kullanılabilirlik daha yüksek olabilir. Sıfır yanlış
pozitif, sistemin olmayan plaka uydurmadığını gösteriyor — güvenilirlik
açısından bu, tam isabet oranından daha kıymetli bir sonuç.

**Sınır:** Bu ölçüm tek kameranın (`kamera-204`) tek günlük trafiğidir ve
GPU'ya geçişten hemen sonra alınmıştır — GPU'nun kendisi doğruluğu değiştirmez
(aynı model ağırlıkları, yalnız hız değişir), bu yüzden CPU'daki 2026-09-02
ölçümüyle (0/1) doğrudan karşılaştırılabilir değildir; örneklem büyüklüğü
farklı. Kalıcı bir iyileştirme için kamera açısı/mesafesi veya OCR fine-tune'u
gerekir (bkz. sohbet geçmişi, 2026-09-03 "eğitime ihtiyaç var mı" analizi).

## OCR modeli A/B denemesi (2026-09-04, SONUÇSUZ — nedeni aşağıda)

`fast-plate-ocr`'ın sunduğu 3 hazır ağırlık aynı 42 güvenilir geçiş + 15
sessiz segment üzerinde karşılaştırılmak istendi: `global-plates-mobile-vit-v2-model`
(mevcut varsayılan), `european-plates-mobile-vit-v2-model`,
`cct-s-v2-global-model`. Yöntem: `scripts/plate_eval_gt.py --ocr <model>`,
her model kendi sürecinde bir kez yüklenip 42+15 geçişin tamamında
tekrar kullanıldı (yeniden yükleme maliyetinden kaçınmak için).

**Sonuç güvenilir değil — kapsama çöktü:** Yer gerçeği penceresi
(2026-09-03 07:00–16:53 UTC) ölçüm anında (2026-09-04 ~01:00–03:30 UTC)
zaten **~18-20 saat eskiydi**. `record.max_size_gb=100` ve 6 kameranın
toplam ~11,3 GB/saat kayıt hızıyla gerçek saklama penceresi **~8,8 saat** —
yani orijinal ölçümdeki 42/42 (%100) kapsama, bu denemeye gelindiğinde
modelden modele **9/42 (%21) → 12/42 (%29) → 6/42 (%14)** arasına düşmüştü
(kota arka planda sürekli budadığı için modeller sırayla çalıştıkça kapsama
daha da eridi). Ayrıca `segment_bul()` hedef zamana **en yakın hâlâ diskte
olan** segmenti seçtiğinde, kota ilerledikçe bu "en yakın" segment gerçek
segmentten kayıyor — bir örnekte (`34EY2333`, 17:09) geç çalışan model başka
bir geçişin (`34PMK153`) segmentiyle eşleşti; bu OCR hatası değil, zamana
bağlı segment kayması.

**Tek temiz karşılaştırma — üç modelin de AYNI segmenti gördüğü 5 ortak
geçiş:** `global` 3/4 tam isabet, `cct-s-v2-global` 3/4, `european` 2/4
(1 geçiş üçünde de okunamadı). 15 sessiz segmentin hiçbirinde hiçbir model
yanlış pozitif üretmedi (0/15 × 3) — üçü de "yok"u "yok" olarak bırakıyor.

**Karar:** Bu örneklem (n=5 temiz, n=6-12 kirli) `config.yaml`'ın
varsayılanını (`global-plates-mobile-vit-v2-model`) değiştirmek için yeterli
kanıt DEĞİL — hiçbir model, mevcut varsayılanın belgelenmiş %59,5'lik
(n=42, %100 kapsama) sonucunu geçersiz kılacak güçte üstünlük göstermedi.
Varsayılan değiştirilmedi.

**Kök neden ve takip:** Asıl bulgu OCR modeli değil, **saklama penceresi
kısalığı** — 8,8 saat, ertesi gün yapılan doğrulamayı (ve olası adli/kanıt
talebini) imkânsız kılıyor. Adil bir 3 model karşılaştırması için ya (a)
GT penceresi hâlâ canlı saklama içindeyken (aynı gün, birkaç saat içinde)
ölçülmeli, ya da (b) test süresince kota geçici yükseltilmeli. Kalıcı
`record.max_size_gb` artışı ayrı bir disk-kapasite kararı gerektirir,
burada yapılmadı.
