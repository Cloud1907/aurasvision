# Yangın/duman modeli — nereden gelir, nasıl eğitilir

`src/fire.py` bir model DOSYASI ile gelmez ve gelmemelidir: ağırlık dosyası
repoya girmez (boyut + lisans izlenebilirliği). Bu belge `fire.model` alanına
ne yazılacağını ve ağırlığın nereden geleceğini anlatır.

## Neden genel YOLO ağırlığı işe yaramaz

COCO'da duman veya alev sınıfı **yoktur**. `yolo11s.pt` `fire.model`e yazılırsa
hat sorunsuz koşar, hiç hata vermez ve **hiçbir zaman olay üretmez** — sahadaki
en pahalı hata tipi. `src/fire.py:model_yolu()` bunu açık `FileNotFoundError`'a
çevirir; bu kapıyı gevşetme.

## Sıralama: önce hazır model, eğitim SONRA

İlk yazımda "D-Fire ile kendi ağırlığımızı eğitelim" öneriliyordu. **Sıralama
yanlıştı** ve düzeltildi. Doğrusu:

1. **Hazır detektörle hattı çalıştır.** Bugün, sıfır maliyetle uçtan uca
   çalışan bir sistem elde edilir.
2. **Sahadan zor negatif topla.** Gerçek fabrikanın kendi yanlış tetikleyicileri:
   kaynak arkı, egzoz buharı, toz bulutu, güneş huzmesi, forklift farı.
3. **Sonra fine-tune et.** Asıl kazanç buradadır.

Sebep: bugün eğitirsek D-Fire'ın dağılımına optimize ederiz, müşterinin
sahasına değil. Sahanın verisi ise hat çalışmadan toplanamaz — yani eğitim
mantıken hattın SONRASINA düşer. Genel yangın görüntüsü eklemek, o sahanın
kaynak makinesini duman sanmayı düzeltmez.

## Aday hazır modeller

| Aday | Lisans | Biçim | Sınıf | Uygunluk |
|---|---|---|---|---|
| [pedbrgs/Fire-Detection](https://github.com/pedbrgs/Fire-Detection) | MIT (repo) | YOLOv5s/l, YOLOv4 ağırlıkları + `scripts/download_models.sh` | alev + duman | **En yakın aday** — D-Fire dahil eğitilmiş, DETEKTÖR. Ağırlıkların kendi lisansı repo README'sinde ayrıca yazılı değil; kullanmadan önce teyit gerekir |
| [pyronear/yolo11s_colorful-chameleon_v3.0.0](https://huggingface.co/pyronear/yolo11s_colorful-chameleon_v3.0.0) | Apache-2.0 | `.pt`, ONNX, NCNN, TorchScript | **tek sınıf: duman** | Açık saha/uzak duman kolonu. Kapalı mekânda zayıf; `fire.imgsz` 1024 olmalı |
| [prithivMLmods/Fire-Detection-Engine](https://huggingface.co/prithivMLmods/Fire-Detection-Engine) | Apache-2.0 | ViT | 3 sınıf | **KULLANILAMAZ** — sınıflandırıcı, kutu üretmez. Hattımız IoU bağlama ve kanıt çerçevesi için kutu ister. "Hazır ama yanlış biçim"in örneği |

## Kabul ölçütü — hangi model YETERLİ

Model seçimi zevk meselesi değil; `src/fire.py`'deki zamansal doğrulama
sayısal bir eşik dayatıyor. Varsayılan yapılandırmada (25 fps kaynak,
`vid_stride 3`, 6 sn pencere, 4 kare onay) pencereye **50 işlenmiş kare**
sığıyor ve %95 olasılıkla onay için **kare-başına recall ≥ %15** gerekiyor
(`src/fire.py:gereken_recall`, testi `tests/test_fire_metrik.py`).

Bu sayı iki şey söylüyor:

* **mAP bu üründe başarı ölçütü değildir.** Naif beklenti "dedektör olayı
  görmeli" (~%90 recall) iken zamansal doğrulama bunu 6 kat aşağı çekiyor.
* **Güven eşiği yükseltilerek precision satın alınabilir.** %15'e kadar
  recall'dan feragat etmek ürünü İYİLEŞTİRİR — çünkü yanlış alarmı belirleyen
  şey kare-başına yanlış pozitiftir, kaçırılan kare değil.

Marj sanıldığı kadar geniş DEĞİL: %10 recall'da onay olasılığı %75'e düşer,
yani dört olaydan biri kaçar. Ayrıca hesap kareleri bağımsız varsayıyor;
gerçekte ardışık kareler ilintilidir (aynı poz, aynı ışık) — bu yüzden
**hafif iyimser bir üst sınırdır**, eşik seçerken marj bırak.

## Eğitim — sırası geldiğinde

Kaynak: [D-Fire](https://github.com/gaiasd/DFireDataset) — **CC0 1.0**
(şartsız, ticari serbest), 21.527 görüntü, 26.557 kutu (14.692 alev /
11.865 duman), sınıf sırası `0=smoke, 1=fire`. En değerli kısmı **9.838
negatif** (yangın/duman içermeyen) kare: yanlış alarmı bastıran şey pozitif
örnek değil negatif örnektir. ISO/TS 7240-29 yanlış alarm testi
*tanımlamıyor* (FIA Fact File 90); o boşluğu ancak negatifler kapatır.

```bash
yolo detect train data=dfire.yaml model=yolo11s.pt imgsz=640 epochs=100 batch=16
```

**Eğitim makinesi GB10'dur, bu Mac değil.** `docs/olcumler-gb10.md`: Blackwell
sm_121, 128 GB birleşik bellek, CUDA 13.0. Geliştirme Mac'i M4/MPS'tir ve
aynı işi büyüklük mertebesi yavaş yapar; ayrıca diskte yer dar. Çıkan
`best.pt` → `models/fire.pt`; ağırlığı repoya **commit etme**, SHA'sını
ölçüm belgesine yaz.

## Donanım

`fire.model` bir `.pt` dosyasıdır ve `device: auto` ile çalışır: NVIDIA
(RTX 3050 ve sonrası dahil) CUDA, Mac MPS, sunucuda CPU. **TensorRT `.engine`
dosyası kullanma** — engine'ler GPU mimarisine ve sürücü sürümüne özgüdür;
GB10 için üretilen bir engine 3050'de yüklenmez. Hız gerekiyorsa export makine
başına yapılır, repoya girmez.

Kamera kapasitesi ölçülmedi. GB10 için `docs/olcumler-gb10.md` worker başına ~48
kamera diyor; 3050 için karşılığı **yoktur** — kurulum sonrası ölçülüp buraya
yazılmalı. Ölçmeden sayı vermek yanlış kapasite planlamasına yol açar.

## Lisans notu (kapsam dışı ama açık uç)

Ağırlıklar CC0/Apache olsa da YOLO11 mimarisi ve eğitim hattı **Ultralytics
AGPL-3.0**'dır: ticari üründe ya tüm proje AGPL açılır ya Enterprise lisans
alınır (https://www.ultralytics.com/license). Bu yeni bir borç değil —
`count`/`plate`/`face` zaten aynı bağımlılıkta. Ayrı bir karar olarak ele alınmalı.
