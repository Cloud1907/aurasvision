# Yangın/duman modeli — nereden gelir, nasıl eğitilir

`src/fire.py` bir model DOSYASI ile gelmez ve gelmemelidir: ağırlık dosyası
repoya girmez (boyut + lisans izlenebilirliği). Bu belge `fire.model` alanına
ne yazılacağını ve ağırlığın nereden geleceğini anlatır.

## Neden genel YOLO ağırlığı işe yaramaz

COCO'da duman veya alev sınıfı **yoktur**. `yolo11s.pt` `fire.model`e yazılırsa
hat sorunsuz koşar, hiç hata vermez ve **hiçbir zaman olay üretmez** — sahadaki
en pahalı hata tipi. `src/fire.py:model_yolu()` bunu açık `FileNotFoundError`'a
çevirir; bu kapıyı gevşetme.

## Seçenek 1 (önerilen): D-Fire ile kendi ağırlığımız

| | |
|---|---|
| Kaynak | https://github.com/gaiasd/DFireDataset |
| Lisans | **CC0 1.0 Universal** — şartsız, ticari kullanım serbest |
| Ölçek | ~21.000 görüntü; 14.692 alev + 11.865 duman kutusu |
| Sınıflar | `fire`, `smoke` (YOLO formatı, normalize koordinat) |

**Asıl sebep negatif kareler:** sette **9.838 adet yangın/duman içermeyen**
görüntü var. Yanlış alarmı bastıran şey pozitif örnek değil negatif örnektir.
ISO/TS 7240-29 yanlış alarm testi *tanımlamıyor* (FIA Fact File 90) — o boşluğu
ancak eğitim setindeki negatifler ve sahadan toplanan zor negatifler kapatır.

Eğitim (tek GPU yeter; RTX 3050 ve üstü):

```bash
yolo detect train data=dfire.yaml model=yolo11s.pt imgsz=640 epochs=100 batch=16
```

Çıkan `best.pt` → `models/fire.pt`. Ağırlığı repoya **commit etme**; sürüm ve
SHA'sını `docs/olcumler-*.md` içine yaz.

### Sahadan zor negatif toplama (ilk kurulumdan sonra zorunlu adım)

İlk hafta hattı `alarm_seconds` yüksek tutup yalnız ön uyarı topla. Yanlış ön
uyarıların karelerini etiketleyip negatif olarak eğitime kat. Kaynak makinesi,
egzoz buharı, toz bulutu, güneş huzmesi ve far ışığı en sık yanlış tetikleyiciler.
Maskeleme (`kind='firemask'`) bunun yerine geçmez — ikisi birlikte çalışır.

## Seçenek 2: PyroNear hazır ağırlığı (açık saha / uzak duman)

| | |
|---|---|
| Kaynak | https://huggingface.co/pyronear/yolo11s_colorful-chameleon_v3.0.0 |
| Lisans | **Apache-2.0** |
| Mimari | YOLO11s, 1024×1024; formatlar: `.pt`, ONNX, NCNN, TorchScript |
| Sınıf | **Tek sınıf** — duman kolonu |

İndir-çalıştır; eğitim gerekmez. Ama domaini **orman/açık alan**: uzaktaki duman
kolonu için eğitilmiş. Fabrika içi, depo, otopark gibi kapalı/yarı kapalı
sahnelerde Seçenek 1'in yerini tutmaz. `fire.imgsz` bu modelde `1024` olmalı.

## Seçenek 3: FASDD ile ölçek büyütme

100.000+ görüntü, üç alt küme (yer / İHA / uydu):
https://essd.copernicus.org/preprints/essd-2023-73/ — YOLOv5x ile ~%80 mAP@0.5
bildiriliyor. Seçenek 1 saha ölçümünde yetersiz kalırsa buraya geçilir; lisans
kullanımdan önce ayrıca doğrulanmalı (bu belge yazılırken teyit edilmedi).

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
