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

## Canlı olay kıyası (2026-09-16, 8 gün, TRASSIR ile yan yana)

Yukarıdaki iki ölçüm arşiv segmentini yeniden tarıyordu (model A/B için
doğru yol, ama saklama penceresine bağımlı). Bu ölçüm **üretimde zaten
yazılmış iki olay akışını** karşılaştırır: AurasVision canlı hattının
`plate_events` tablosu ile connector'ın TRASSIR'dan döktüğü
`C:\ProgramData\OneGateData\daily\<gün>\lpr.jsonl`. Model koşmaz, saniyeler
sürer, günler boyu biriken veriyle çalışır. Yöntem: `scripts/plate_live_kiyas.py`
(geçiş kümeleme 90 sn, eşleme penceresi ±60 sn, Levenshtein mesafesi).

Pencere: 2026-09-08 → 2026-09-16, `kamera-204`. 13 Eylül'de iki tarafta da
veri yok; 5-7 Eylül'de TRASSIR dökümü yok (connector 9 Eylül'de başladı),
o günler dışarıda. Ham: `output/plate_live_kiyas/plate_live_kiyas_0908_0916.json`.

| | |
|---|---|
| TRASSIR geçişi / AurasVision geçişi | 607 / 652 |
| Zamanca eşleşen | 455 (TRASSIR geçişlerinin %75'i; `tr/` şablonlu güvenilirlerin %77,6'sı) |
| Eşleşende **tam isabet** | **178 / 455 (%39,1)** |
| ≤1 karakter fark | 237 / 455 (%52) |
| AurasVision adaylarından biri tam | 211 / 455 (%46) |
| TRASSIR'ın kesik okuduğu, AurasVision'ın uzun okuduğu | 21 (`34JV369→34JV3699`, `34BBL48→34BBL483`) |
| Ortalama karakter mesafesi | 2,28 |
| AurasVision **kaçırdı** | 152 (45'i park etmiş aracın TRASSIR tekrarı → gerçek kaçırma ~107, %18) |
| AurasVision **fazla** | 197 (135'i park etmiş aracın tekrarı, 57'si tek karelik) |

### Bulgu 1 — canlı akış arşiv taramasından kötü, sebebi düşük kaliteli olaylar

Arşiv taramasında %59,5 çıkan tam isabet canlıda %39. Eşleşen geçişte
AurasVision olayının kalitesine göre kırılım:

| AurasVision olayı | n | tam isabet |
|---|---|---|
| `reads`=1 | 94 | %7 |
| `reads`=2 | 91 | %29 |
| `reads`≥3 | 270 | %54 |
| `conf`<0,90 | 171 | %9 |
| `conf`≥0,90 | 284 | %57 |
| `reads`≥3 **ve** `conf`≥0,90 | 212 | **%63** |

Tek karelik veya güveni 0,90 altı olaylar neredeyse hiç doğru değil; onları
panel/alarm tarafında süzmek tam isabeti %39'dan %57-63'e çıkarır, kaybedilen
171 eşleşmenin yalnız 15'i doğruydu. `plate.single_read_min_conf: 0.65` bu
sahada gevşek; kara liste alarmı zaten `alert_min_reads: 2` ile korunuyor.

### Bulgu 2 — park etmiş araç iki motoru da kandırıyor, AurasVision'ı daha çok

Görüş alanında duran araç gün boyu yeniden okunuyor. 16 Eylül'de tek araç
(`34NRL083`, okumalar `34NR4083/34MR4083/34KR4083...` arasında oynuyor)
AurasVision'da **107 olay** (ortalama 71 okuma/olay), TRASSIR'da 3 günde 61
olay üretti. 10 ve 12 Eylül'de `34NFU034` 61 + 33 olay. "Fazla"nın 197/135'i
budur — yanlış okuma değil, **aynı aracın yeniden olaylaştırılması**. Kök
neden `plate.track_rebirth_seconds: 30`: yaya/araç 30 sn'den uzun örtünce iz
kapanıp yeniden açılıyor. Ölçüm için betikte `--tekrar-dk` süzgeci var
(eşleştirmeyi değiştirmez, yalnız etiketler); üründe düzeltme ayrı iş.

### Bulgu 3 — TRASSIR yer gerçeği olarak kusurlu

Eşleşen 455 geçişin 21'inde TRASSIR plakayı kesik okumuş (7 karakter),
AurasVision tamını vermiş; 62 TRASSIR geçişi `tr/` şablonundan geçmiyor
(`2422`, `34YLA`, `34EZ`). Aynı park etmiş aracı TRASSIR da 6 farklı biçimde
okudu. Yani buradaki "%39" TRASSIR'a göre uyum oranıdır, mutlak doğruluk
değil; iki motorun uyuşmadığı 142 büyük-fark geçişinin (mesafe ≥4, 72'si
aynı saniyede) hangisinde kimin haklı olduğu kare görülmeden söylenemez.

### Sonuç

- Kaba uyum: TRASSIR'ın gördüğü 4 araçtan 3'ünü AurasVision da görüyor,
  bunların %39'unu birebir, %52'sini ≤1 karakterle okuyor.
- En etkili kısa vadeli iyileştirme model değil **olay eşiği**: `conf≥0,90` +
  `reads≥3` süzgeci tam isabeti %63'e taşır.
- İkinci iyileştirme park etmiş araç tekrarını kesmek (Bulgu 2).
- Tekrar ölçüm: `python scripts/plate_live_kiyas.py --bastan <gün> --sona <gün> --ayrinti`.
