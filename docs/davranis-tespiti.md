# Davranış tespiti — telefonla konuşma ve sigara içme

Modül: `src/davranis.py` · görev anahtarı: `davranis` · yapılandırma: `config.yaml` → `davranis:`

## Ne yapar, ne yapmaz

Kameradaki kişinin **telefonla konuştuğunu** veya **sigara içtiğini** zaman içinde
doğrulayıp uyarı üretir. Kimlik eşlemesi yapmaz, yüz vektörü üretmez; çıktı
"bir kişi, şu kamerada, şu kadar süre" bilgisidir. Kanıt karesi kişiyi içerir
ve `evidence.davranis` ile kapatılabilir; saklama `evidence.keep_days`.

Sınır: kişi kameraya **yakın** olmalı. Baş genişliği (kulaklar arası) 24 pikselin
altındaysa kişi değerlendirilmez (`min_bas_px`); geniş açılı koridor kamerasında
uzak kişi için karar verilmez. Kapı, kasa, sigara yasağı olan koridor ağzı gibi
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

- **el kulakta**: bilek bir kulağa `kulak_oran × baş` yakın, omuz hizasının üstünde,
  ve kulağa ağızdan daha yakın.
- **el ağızda**: bilek tahmini ağız noktasına (burnun 0,5 baş altı) `agiz_oran × baş` yakın.

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
| `tercih` (varsayılan) | doğrulayan kutu varsa hemen alarm; yoksa sezgisel iki kat sürerse alarm |
| `zorunlu` | kutu görülmeden alarm yok, ön uyarı panelde kalır |
| `kapali` | yalnız poz |

## Kademeler ve çıktı

`izle → on_uyari → alarm` (yangın hattıyla aynı). Ön uyarı yalnız log ve Test
ekranı; alarm kanıt karesi + klip (`clip_seconds`) + `alerts` satırı
(`kind='davranis'`, `ref='telefon'|'sigara'`) + webhook (`tur: davranis`).
Aynı kişi + aynı davranış `cooldown_seconds`, aynı kamera + aynı davranış
`camera_cooldown_seconds` ile sınırlanır.

## Nerede çalışır

- **akis motoru** (canlı RTSP): `_DavranisKademe`, kendi iş parçacığı, `davranis.fps`
  (4) tempo, meşgulse kare atılır. Kamera görevlerinde "Davranış" açılınca.
- **ultralytics motoru / CLI**: `run_davranis(source, cfg, ...)`.
- **Test ekranı**: tür "Davranış" veya "Hepsi" (kamerada görev açıksa). Dosya
  kaynağında ileri sarma çalışır.

## Ölçüm durumu (2026-09-22)

- Birim: `tests/test_davranis.py` — 16 test, sahte anahtar noktayla karar mantığı.
- Yanlış alarm tabanı: `data/videos/` altındaki 3 örnek (mağaza koridoru 6 kişi,
  yaya, bisiklet/araç) → 1.720 kare, 0 ön uyarı, 0 alarm. 32 kare/sn (RTX 3050).
- **Doğru pozitif ölçülmedi**: elde telefon/sigara içeren video yok. Sahada bir
  haftalık ön uyarı/alarm günlüğü toplanıp eşikler (`telefon_sn`, `sigara_tekrar`,
  `kulak_oran`) buna göre ayarlanmalı. Tatmin etmezse PABD veri setiyle ince ayar.

## Lisans

Poz modeli Ultralytics (AGPL-3.0): sayım/plaka/yüz hatlarıyla aynı motor ve aynı
hukuki durum (`src/dedektor.py` başlığı). Sigara ağırlığı MIT. Ayrı motor
kararı verilirse değişecek tek yer `davranis._poz_kur`.
