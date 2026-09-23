# Davranış tespiti — telefonla konuşma ve sigara içme

Modül: `src/davranis.py` · görev anahtarları: `telefon` ve `sigara` (AYRI görev, AYRI alarm türü; tek poz hattını paylaşırlar) · yapılandırma: `config.yaml` → `davranis:`

## Ne yapar, ne yapmaz

Kameradaki kişinin **telefonla konuştuğunu** veya **sigara içtiğini** zaman içinde
doğrulayıp uyarı üretir. Kimlik eşlemesi yapmaz, yüz vektörü üretmez; çıktı
"bir kişi, şu kamerada, şu kadar süre" bilgisidir. Kanıt karesi kişiyi içerir
ve `evidence.davranis` ile kapatılabilir; saklama `evidence.keep_days`.

Sınır: baş genişliği (kulaklar arası) 16 pikselin altındaysa kişi değerlendirilmez
(`min_bas_px`). 720×1280 karede tüm vücut görünen sokak klibi (baş 22 px) `imgsz: 960`
ile yakalandı; daha uzak kişi için karar verilmez. Kapı, kasa, sigara yasağı olan koridor ağzı gibi
yakın plan sahneler hedeftir.

## Neden iki katman

Sigara birkaç piksel, telefon kulakta elin arkasında. Tek kare nesne dedektörü
sahada kalem, bardak, saç düzeltme gibi hareketleri alarm yapar. Literatürde
işe yarayan yol poz + nesne birleşimidir:

| Kaynak | Bulgu |
|---|---|
| [DAHD-YOLO (2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11902441/) | Tek kare sigara tespiti YOLOv8s tabanla %81 mAP50; zorluk: sigara ince, elle bütünleşik, parmak/kalemle karışıyor |
| [SPIE 2025 anahtar nokta + YOLOv8](https://ui.adsabs.harvard.edu/abs/2025SPIE13688E..04Z/abstract) | El-ağız mesafesi, eklem açısı ve süre + sigara dedektörü birleşimi |
| [GD-YOLO (2024)](https://www.sciencedirect.com/science/article/abs/pii/S1051200424001799) | Sigara ve telefon kullanımı tek modelde, gerçek zamanlı |
| [TACR-YOLO / PABD (2025)](https://arxiv.org/html/2508.11478v1) | 8.529 görüntü; telefon 3.413, sigara 3.300 etiket; metro/AVM sahneleri |
| [FPI-Det (2025)](https://arxiv.org/pdf/2509.09111) | Telefon kullanımı "yüzle ilişkili" tanımlanınca doğruluk artıyor |

### 1. Poz sezgiseli (her zaman açık)

Ultralytics YOLO11n-pose (COCO-17 anahtar nokta, GPU'da ~20 ms/kare). Her kişi
için baş ölçeği (kulaklar arası) hesaplanır, mesafeler buna bölünür:

- **telefon pozu**: bilek en yakın kulağın 0,5–2,0 baş ALTINDA, yatayda kulağa
  `kulak_oran × baş` yakın, burun hizasından en az 0,3 baş dışarıda (çeneye dayanan
  el sayılmaz), dirsek bileğin altında. Ölçüm: telefon kulaktayken bilek kulakta
  değil, çene/boyun hizasındadır.
- **el ağızda**: bilek tahmini ağız noktasına (burnun 0,5 baş altı) `agiz_oran × baş`
  (1,4) yakın; telefon pozundaki el dokunuş sayılmaz.

Zaman içinde:

- **telefon**: son `telefon_sn` (4 sn) penceresinde karelerin `telefon_oran`ı (%70) el kulakta → ön uyarı.
- **sigara**: el ağza `dokunus_min_sn`–`dokunus_max_sn` (0,3–6 sn) arası temaslarla
  `sigara_pencere_sn` (40 sn) içinde `sigara_tekrar` (2) kez gidip geliyor → ön uyarı.
  Uzun temas (çene sıkma, düşünme pozu) dokunuş sayılmaz.

### 2. Nesne doğrulama

- **telefon**: stok COCO "cell phone" (67) kutusu baş bölgesinde. Akis motorunda
  sayım batch'inden bedava gelir; dosya/Test yolunda `detect.model` ile ayrıca bakılır.
- **sigara**: isteğe bağlı ayrı ağırlık `davranis.sigara_model` (ultralytics `.pt`),
  baş kırpması üzerinde. Önerilen hazır ağırlık:
  [Beehzod/smoke_cigarette-detection2-yolo11m](https://huggingface.co/Beehzod/smoke_cigarette-detection2-yolo11m)
  (MIT; 1.636 eğitim görüntüsü, kendi test setinde mAP50 0,99 — sahada çok daha
  düşük beklenmeli). `best.pt` dosyasını `models/sigara.pt` olarak koyup
  `sigara_model: models/sigara.pt` yazın. Ağırlık yoksa hat yalnız pozla çalışır.

Doğrulama kipi (`telefon_dogrulama` / `sigara_dogrulama`):

| kip | davranış |
|---|---|
| `tercih` (varsayılan) | doğrulayan kutu varsa hemen alarm; yoksa poz tek başına: telefon `telefon_sn × telefon_poz_kat` (12 sn) sürerse, sigara bir nefes daha (`sigara_tekrar`+1) görülürse |
| `zorunlu` | kutu görülmeden alarm yok, ön uyarı panelde kalır |
| `kapali` | yalnız poz |

## Kademeler ve çıktı

`izle → on_uyari → alarm` (yangın hattıyla aynı). Ön uyarı yalnız log ve Test
ekranı; alarm kanıt karesi + klip (`clip_seconds`) + `alerts` satırı
(`kind='telefon'` veya `kind='sigara'`) + webhook (`tur: telefon|sigara`). Kanıt türü
de ayrıdır: `evidence.telefon`, `evidence.sigara`.
Aynı kişi + aynı davranış `cooldown_seconds`, aynı kamera + aynı davranış
`camera_cooldown_seconds` ile sınırlanır.

## Nerede çalışır

- **akis motoru** (canlı RTSP): `_DavranisKademe`, kendi iş parçacığı, `davranis.fps`
  (4) tempo, meşgulse kare atılır. Kamera görevlerinde "Telefon" ve/veya "Sigara" açılınca;
  ikisi de açıksa poz bir kez koşar, yalnız sigara açıksa sayım batch'ine girilmez.
- **ultralytics motoru / CLI**: `run_davranis(source, cfg, ...)`.
- **Test ekranı**: tür "Telefon", "Sigara" veya "Hepsi" (kamerada görev açıksa). Dosya
  kaynağında ileri sarma çalışır.

## Ölçüm durumu (2026-09-22)

Geometri Pexels klipleriyle ÖLÇÜLDÜ ve sezgisel buna göre yazıldı: telefon
kulaktayken bilek kulağın ~1,2 baş altında ve yüzün yanında (kulakta değil!);
sigara nefesinde bilek ağız tahmininin ~1 baş çevresinde. Profilde kulaklar arası
ölçek çöktüğü için baş ölçeği birkaç ölçünün en büyüğüdür (burun→omuz ortası×0,6).

Güvenlik kamerası açısına yakın (orta/geniş plan) demo klipler, `data/videos/davranis/`,
Pexels (ücretsiz, atıf gerekmez), 1280 px. Test ekranında aynı adlı kameralar
(görevler kapalı) bunları gösterir; tür "Telefon" veya "Sigara" seçilir.

| Klip | Plan | Sonuç (varsayılan ayarlar: imgsz 960, min_bas_px 16) |
|---|---|---|
| `sigara_sokak_uzak_8103469` ([Pexels](https://www.pexels.com/video/a-person-smoking-cigarette-outside-8103469/)) | tüm vücut, uzak, baş 22 px | 2 ön uyarı, **sigara alarmı** 21,7 sn (3. nefes) |
| `sigara_balkon_cift_9498608` ([Pexels](https://www.pexels.com/video/couple-smoking-cigarette-at-the-balcony-9498608/)) | orta-geniş, 2 kişi, camdan | **sigara alarmı** 8,9 sn; telefon yalnız ön uyarı (yüze yaslanan el — 2× iken sahte alarmdı) |
| `telefon_yuruyen_adam_5391290` ([Pexels](https://www.pexels.com/video/a-man-talking-on-the-phone-while-walking-5391290/)) | orta-geniş, yürüyen, maskeli | **telefon alarmı** 8,1 sn, telefon kutusuyla |
| `telefon_kapi_adam_5281629` ([Pexels](https://www.pexels.com/video/a-man-talking-on-the-phone-outside-5281629/)) | orta plan | **telefon alarmı** 3,3 sn, telefon kutusuyla |
| 3 negatif klip (`data/videos/*.mp4`, 1.720 kare, 6 kişiye kadar) | mağaza, yaya, sokak | 0 ön uyarı, 0 alarm |

Yakın plan stüdyo klipleri (`telefon_kadin_*`, `sigara_adam_*`) de klasörde durur
ama HEDEF SAHNE DEĞİLDİR: yüz kadrajı doldurunca `imgsz 960` poz modelini bozar
(640'ta çalışıyordu). Güvenlik kamerasında böyle kare olmaz; 960 uzak kişi için seçildi.

- Birim: `tests/test_davranis.py` — 20 test.
- Hız: 21 ms/kare poz (RTX 3050); dosya yolunda telefon doğrulaması dâhil ~30 kare/sn.
- Sigara dedektörü (`models/sigara.pt`, Beehzod yolo11m, MIT) 2026-09-23'te kuruldu ve
  `sigara_model` ile açıldı. Ölçüm (yalnız poz → dedektör tercih): sokak uzak alarm 21,7 → 1,3 sn;
  balkon 8,9 → 7,4 sn; yakın plan klip alarm yok → 21,2 sn; telefon klibi ve mağaza negatifinde 0 tetik.
  Ağırlık depoya girmez (`models/` yok sayılır); kurulum: Hugging Face `best.pt` → `models/sigara.pt`.
- Açık borç: gerçek CCTV kaydında (tavan açısı, 2880 px ana akış) ölçüm yok.
  İlk hafta ön uyarı/alarm günlüğü toplanıp `telefon_sn`, `telefon_poz_kat`,
  `sigara_tekrar` buna göre ayarlanmalı. Sigara ağırlığı (`sigara_model`) kurulu değil.

## Lisans

Poz modeli Ultralytics (AGPL-3.0): sayım/plaka/yüz hatlarıyla aynı motor ve aynı
hukuki durum (`src/dedektor.py` başlığı). Sigara ağırlığı MIT. Ayrı motor
kararı verilirse değişecek tek yer `davranis._poz_kur`.


## Canlı ayrıntı düzeltmesi (2026-09-22)

`davranis.use_main_stream: true` artık canlı kaynak seçimine uygulanır.
Alt akıştaki küçük başlar minimum piksel eşiğine takıldığı için ana akış kullanılır.
Telefon doğrulayıcısı canlı ve dosya yolunda kişi kırpmalarını inceler: kamera
başına saniyede bir, en büyük altı kişi. Kutular ana kare koordinatlarına
çevrilir ve yalnız bir tarama aralığı boyunca kullanılır.

Telefon kutusu kişinin bileğine yakınsa zamansal telefon adayı sayılır;
kulakta tutulması şart değildir. Boş el, masadaki telefon ve tek karelik
tespit yeterli değildir. Etiket bu nedenle **telefon kullanımı**dır;
görüntüden sesli konuşma yapıldığı iddia edilmez. Telefon tutan el sigara
hareketinden çıkarılır; diğer elin sigara hareketi bağımsız değerlendirilir.

Yerel CCTV kaydında yeniden analiz (768 kare) telefon kutusuyla doğrulanan
telefon alarmı ve poz hareketine dayanan sigara alarmları üretti. Üç negatif
klibin 677 örnek karesinde alarm oluşmadı; bir sigara ön uyarısı oluştu.
Bu sınırlı saha doğrulamasıdır; sigara için ayrı nesne modeli hâlâ kurulu değildir.
