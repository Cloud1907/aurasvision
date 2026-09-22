# Yangın hattı — saha videosu denemesi (TRASSIR dışa aktarması, 2026-09-02)

Koşu: 2026-09-05 13:49-14:07, RTX 3050, `models/fire.pt` (RF-DETR-Small, D-Fire),
`scripts/fire_video_dene.py`. Kaynak: `TRASSIR-4.9.9.0-1308508 2026-09-02 09-22-42.mp4`
(1920×1032 @ 30 fps, 952 sn, TRASSIR istemcisinin **ekran kaydı** — kamera görüntüsü
kadrajın sağ ~%70'inde, solda olay listesi). Yapılandırma varsayılan: conf 0,35,
stride 3, pencere 6 sn / 4 kare, alarm 3 sn.

## Videoda ne var (elle bakıldı)

| Video sn | Saat (kayıt saati) | Gerçek |
|---|---|---|
| 0-455 | 09:22:42-09:30:16 | Atölye, normal çalışma; alev/duman yok |
| ~450-605 | 09:30:12-09:32:47 | Yerde kovada **açık alev**, sonra söndürme dumanı |
| 605-725 | 09:32:47-09:34:47 | Alev yok |
| ~728-900 | 09:34:50-09:37:42 | Kova yeniden yakılıyor, **açık alev**, sonra duman |

TRASSIR'ın kendi olay listesinde (ekranda görünen) yalnız **09:27:47 "Alan 4 · Duman
algılandı"** var — bu, alevden 3 dakika ÖNCE ve o anda kamerada duman görünmüyor.
İki gerçek yanma aralığında TRASSIR listesine yeni olay düşmedi. (Kullanıcı beyanı:
"TRASSIR başarısız oldu" — video bunu doğruluyor.)

## AurasVision sonucu (conf 0,35, varsayılan)

| Ölçüm | Değer |
|---|---|
| İşlenen kare | 9.527 (8,9 kare/sn; kutulu video yazımı CPU'da, gerçek hızı düşürdü) |
| Ham tespit | 2.203 |
| 1. yangın: ilk tespit / alarm | 467 sn (alev, conf 0,50) / **473 sn** — görünür tutuşmadan ~15-20 sn sonra |
| 2. yangın: ilk tespit / alarm | 730 sn / **733 sn** |
| Yangın aralıklarında alarm | 19 (aynı odak tekrarları; cooldown 120 sn odak bazında) |
| Yangın DIŞI alarm | **1** — 4,4 sn'de "duman": açık kapıdaki aşırı pozlanmış beyaz alan (kutu 1066-1613 × 260-546, conf 0,35-0,36) |
| Tekil sahte tespitler (olaya dönüşmedi) | 30-50, 140-150, 250-260, 930-940 sn'de 1-2 tespit — zamansal doğrulama eledi |

Kutulu çıktı: `output/fire_dene/kutulu.mp4` (tam), kısa kesitler
`alarm-1-yangin-455-505sn.mp4`, `alarm-2-yangin-725-765sn.mp4`,
`yanlis-alarm-0-12sn.mp4`. Ham tespitler: `output/fire_dene/tespitler.json`.

## Eşik yeniden puanlama (aynı tespitler, yalnız `fire.conf` değişti)

| conf | Toplam alarm | 1. yangın ilk alarm | 2. yangın ilk alarm | Yangın dışı alarm |
|---|---|---|---|---|
| 0,35 | 20 | 473 sn | 733 sn | 1 |
| **0,45** | 8 | 489 sn | 736 sn | **0** |
| 0,55 | 6 | 489 sn | 736 sn | 0 |
| 0,65 | 7 | 491 sn | 737 sn | 0 |

**Karar önerisi:** `fire.conf: 0.45`. D-Fire ölçümünde (docs/olcumler-yangin-modeli.md)
0,45'te kare-recall %85, negatif alarm %0,3; burada sahte alarm sıfırlanıyor, ilk
yangında alarm 16 sn gecikiyor (473 → 489), ikincide 3 sn. Alternatif: eşiği 0,35'te
bırakıp kapı/pencere alanına `firemask` çizmek (ISO/TS 7240-30 zaten bunu ister).

## Sınırlar

- Bu bir ekran kaydıdır: model TRASSIR arayüzünü de gördü, kamera görüntüsü kadrajın
  bir kısmıydı (alev ~35×30 piksel). Gerçek RTSP akışında kadraj tam olur; sonuç
  daha iyi olmalıdır, ölçülmedi.
- Tek kamera, tek gün, kontrollü test. Sahanın kendi yanlış tetikleyicileri (kaynak
  arkı, egzoz, güneş) için ayrı toplama gerekir.
- Feragat: video tabanlı tespit EN 54 kapsamında değildir; mevcut yangın sistemini
  tamamlar (`src/fire.py` başlığı).

## Ek — 20 sn gecikmenin kök nedeni ve 2×2 karo çözümü (2026-09-05 15:30-16:10)

Gecikme dağılımı (1. yangın): tutuşma 452 sn, alev net 458 sn, **modelin ilk
görüşü 467 sn** (dedektör 512'ye küçültüyor; alev ~10 piksel), doğrulama +6 sn
→ alarm 473. Kayıp modelde, doğrulamada değil.

445-500 sn kesitinde deneme (aynı model, aynı eşik 0,35):

| Yöntem | İlk alev tespiti | Tespitli kare / 550 | Tutuşma öncesi sahte |
|---|---|---|---|
| Tam kare (ekran kaydı) | 467,3 | 77 | 0 |
| Kamera kadrajı kırpılmış | 466,1 | 100 | 0 |
| Kırpılmış, eşik 0,20 | 463,7 | 169 | 0 |
| Kırpılmış, 2× büyütme | 466,1 | 105 | 0 |
| **Kırpılmış, 2×2 karo** (`fire.tiles: 2`) | **455,4** | **349** | 0 |

Tam video (952 sn), kırpılmış kadraj + 2×2 karo, `scripts/fire_video_dene.py
--kirp 230,60,1380,900 --karo 2`: 9.527 kare, 3.247 tespit, 33 dk (4× inference).

| conf | onay / alarm | 1. yangın ilk alarm | 2. yangın ilk alarm | Yangın dışı alarm |
|---|---|---|---|---|
| 0,35 | 4 kare / 3 sn (varsayılan) | **453,3** (tutuşmadan ~1 sn) | **731,5** (~3 sn) | **0** |
| 0,35 | 3 kare / 1 sn | 451,2 | 729,5 | 0 |
| 0,45 | 4 kare / 3 sn | 460,7 | 731,5 | 0 |
| 0,55 | 4 kare / 3 sn | 460,7 | 735,6 | 0 |

Sonuç: karo bölme ile alarm gecikmesi **20 sn → 1-3 sn**; tam videoda hiçbir
eşikte yangın dışı alarm yok (karosuz koşudaki kapı parlaması sahte alarmı da
kayboldu — muhtemelen karoda kapı bölgesi bağlamıyla değerlendirildi).
`config.yaml`: `fire.tiles: 2` varsayılan yapıldı, `fire.conf` 0,35'te bırakıldı;
parlak kapı/pencere olan sahada 0,45 güvenli marj (alarm +7 sn).
Kod: `src/fire.py:tespit_karolu`, test: `tests/test_fire_karo.py`.
Ham çıktı: `output/fire_dene_karo/tespitler.json`.
