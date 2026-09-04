# Yangın/duman modeli — eğitim ve ölçüm kaydı

> **Durum: EĞİTİM SÜRÜYOR.** Bu belge ölçüldükçe doldurulur. İçindeki her sayı
> bu makinede gerçekten ölçülmüştür; ölçülmemiş alanlar `— bekliyor —` olarak
> işaretlidir ve tahminle doldurulmaz.
>
> Son güncelleme: 2026-09-03 11:30 · epoch 2/10 koşuyor

Mimari, lisans ve kabul ölçütü: [yangin-modeli.md](yangin-modeli.md).

---

## 1. Eğitim ortamı

| | |
|---|---|
| Makine | Windows 10 Pro · NVIDIA GeForce RTX 3050 · **6.144 MiB VRAM** |
| Sürücü / CUDA | 610.88 / 13.0 |
| torch | 2.14.0+**cu130** |
| rfdetr | 1.9.4 |
| pytorch-lightning | 2.6.5 |
| Python | 3.12.10, ayrı sanal ortam (`.venv-egitim`) |
| Eğitim başlangıcı | 2026-09-03 09:36:01 (+03:00) |

**Planlanandan sapma: eğitim makinesi GB10 değil.** `yangin-modeli.md` eğitim
makinesi olarak GB10'u (128 GB birleşik bellek) gösteriyordu; bu koşu 6 GB'lık
bir RTX 3050'de yapıldı. Sonuçlar bu kısıt altında okunmalı.

**Ayrı sanal ortam bilinçlidir.** Üretim `.venv`'i `torch 2.13.0+cu130` ile
çalışıyor ve canlı GPU worker ona bağlı. Eğitim bağımlılıkları oraya kurulsaydı
bağımlılık çözücü torch'u değiştirebilir ve çalışan sistemi bozabilirdi.
Kurulum sırasında bu risk gerçekleşti: `pip install rfdetr` Windows'ta PyPI'nın
**CPU-only** wheel'ini (`2.14.0+cpu`) getirdi. cu130 hattından yeniden kuruldu;
`rfdetr[train,loggers]` kurulurken torch sürümü açıkça sabitlendi.

---

## 2. Veri seti — D-Fire

### 2.1 Kaynak ve köken

Kanonik dağıtım (OneDrive) **başsız indirmeye kapalı**: `1drv.ms` bağlantısı
tarayıcı oturumu istiyor, `curl` ve OneDrive API'si `403` döndürüyor. README'de
listelenen Kaggle aynası kimlik bilgisi istiyor; bu makinede yok.

Kullanılan kaynak: **HuggingFace aynası `badsaarow/d-fire`** (operatör onayıyla).

> **Köken uyarısı.** Bu üçüncü taraf bir kopyadır; zinciri resmî CC0 dağıtımı
> kadar güçlü değildir. Kimliği aşağıdaki sayım mutabakatıyla doğrulanmıştır,
> ancak lisans izlenebilirliği açısından resmî kaynaktan yeniden indirme
> önerilir.

**Aynanın ham dosya ağacı EKSİKTİR.** `train/images` altında 21.527 görüntünün
yalnız **7.222**'si var (`snapshot_download` `train/*`+`test/*` için toplam
14.614 dosya bildirdi: 7.222 görüntü + 7.221 etiket + 171 test görüntüsü + 0
test etiketi). Tam veri yalnız `data/*.parquet` içindedir; orada etiket, satırın
`label` alanında YOLO metni olarak durur (negatif kare = boş dize). Bu yüzden
`scripts/dfire_parquet_ac.py` yazıldı.

- Parquet: 12 parça, `download_size` 3.118.077.392 bayt (~3,1 GB)
- Açılmış hâli: ~5,3 GB

### 2.2 Sayım mutabakatı

Parquet'ten açılan veri, D-Fire'ın yayımlanmış sayılarıyla **birebir** tutuyor:

| | D-Fire beyanı | Ölçülen | Fark |
|---|---|---|---|
| Görüntü | 21.527 | 21.527 | 0 |
| Negatif kare | 9.838 | 9.838 | 0 |
| Kutu | 26.557 | 26.539 + **18 düşen** | 0 |
| Alev | 14.692 | 14.685 + **7 düşen** | 0 |
| Duman | 11.865 | 11.854 + **11 düşen** | 0 |

Düşen 18 kutunun sınıf kırılımı (7 alev + 11 duman) beyanla farkı tam kapatıyor.
Bu, aynanın D-Fire'ın kendisi olduğunun kanıtıdır.

### 2.3 Ölçülen veri kusurları

Etiketlerin tamamı (26.557 kutu) ayrıştırıcıdan geçirilerek tarandı:

| Bulgu | Adet | Karar |
|---|---|---|
| Normalize kenar > 1.0 (en büyük **1,0563**) | 8 | **Geçerli** — kadrajı dolduran nesnenin kutusu taşıyor; kırpılır |
| Sıfır alanlı kutu (`w=0 h=0`) | 18 | **Elenir ve SAYILIR** — nokta işaretlenmiş, eğitim sinyali yok, NaN kayba yol açar |
| Merkez koordinat aralık dışı | 0 | — |
| Negatif değer / sınıf dışı id | 0 | — |

Merkez koordinatların tamamı `[0,1]` içinde (en büyük cx 0,9957, cy 0,9921).
Kenar tavanı 2.0 konuldu: onun üstü taşma değil bozuk etikettir ve sessizce
kırpılırsa eğitime yanlış kutu girer.

### 2.4 COCO dönüşümü

`scripts/dfire_to_coco.py` · deterministik %10 doğrulama ayrımı (rastgelelik yok,
iki koşu karşılaştırılabilsin diye).

| Split | Görüntü | Negatif | Kutu | smoke | fire | Düşen |
|---|---|---|---|---|---|---|
| train | 15.498 | 7.051 | 19.255 | 8.597 | 10.658 | 11 |
| valid | 1.723 | 782 | 2.095 | 946 | 1.149 | 3 |
| test | 4.306 | 2.005 | 5.189 | 2.311 | 2.878 | 4 |
| **Toplam** | **21.527** | **9.838** | **26.539** | **11.854** | **14.685** | **18** |

Negatif oranı üç split'te de korunmuş (%45–46). **Negatif kareler COCO'nun
`images` listesindedir, `annotations`ı yoktur** — kasıtlı: yanlış alarmı
bastıran şey pozitif örnek değil negatiftir.

---

## 3. Eğitim yapılandırması

| Parametre | Değer | Gerekçe |
|---|---|---|
| Model | RF-DETR-**Small** | Apache-2.0. XL/2XL PML 1.0'dır, `LISANSLAR` tablosuna alınmadı |
| Eğitilebilir parametre | 31,8 M | ölçüldü |
| Çözünürlük | **512** | Modelin pretrain çözünürlüğü; PE = 512/16 = 32 buradan türer. 640'a çıkmak PE'yi değiştirir ve bu VRAM'e sığmaz |
| batch_size | 2 | 6 GB VRAM |
| grad_accum_steps | 8 | efektif batch **16** korunur |
| Epoch | 10 (planlanan) | kısa tur; kabul ölçütü mAP değil |
| Karışık hassasiyet | bf16 AMP | rfdetr varsayılanı |
| Optimizer adımı / epoch | **969** | 15.498 / 16 — ölçümle doğrulandı (epoch 0, step 968'de bitti) |

> **Çözünürlük sınırı ürün açısından önemli.** Küçük nesne (erken duman) recall'ı
> çözünürlükle iyileşir ve bu, hattın en kritik dilimidir. 512 bir uzlaşmadır;
> daha büyük VRAM'de 640 denemeye değer. **Açık uç.**

---

## 4. Ölçülen süre

| Aşama | Süre | Not |
|---|---|---|
| Kurulum (ağırlık indirme + sanity-check) | ~13 dk | 09:36 → 09:49 |
| Epoch 0 | ~42 dk | analiz worker'ı GPU'yu paylaşıyordu |
| Epoch 1 | ~33 dk | worker durdurulduktan sonra |
| Hız | 22,6 → **32,5** optimizer adımı/dk | worker durdurma etkisi |

**GPU çekişmesi ölçüldü:** analiz worker'ı çalışırken GPU doluluğu %16, worker
durdurulduktan sonra **%90**. Worker 10:00'da durduruldu (operatör kararı);
kayıt servisi `-c copy` olduğu için GPU kullanmıyor ve çalışmaya devam etti.

10 epoch tahmini: **~5,5 saat** (epoch 1 hızıyla).

---

## 5. Doğrulama metrikleri (epoch bazında)

| Epoch | mAP@50 | mAP@50:95 | F1 | Precision | Recall | val/loss | AP smoke | AP fire |
|---|---|---|---|---|---|---|---|---|
| 0 | 0,6868 | 0,3748 | 0,6696 | 0,7181 | 0,6282 | 3,6694 | 0,4179 | 0,3318 |
| 1 | 0,7325 | 0,4030 | 0,7052 | 0,7645 | 0,6573 | 3,5468 | 0,4549 | 0,3510 |
| 2–9 | — bekliyor — | | | | | | | |

EMA ağırlıklarla epoch 1: mAP@50 **0,7541** · mAP@50:95 **0,4286**.

**Duman alevden belirgin daha iyi öğreniliyor** (AP 0,455 vs 0,351). Erken uyarı
için kritik olan duman olduğundan bu ürün lehine bir dağılımdır.

**`val/class_error` %45'te takılı** (epoch 0: 45,39 → epoch 1: 45,45) ve mAP
yükselirken düşmüyor. Duman↔alev karışımından geldiği değerlendiriliyor; ürün
açısından önemsizdir çünkü `fire_eval.py` eşleştirmesi **sınıf-bağımsızdır** —
alarm açısından "duman yerine alev dedi" kaçırma değildir. Doğrulanmadı, izleniyor.

---

## 6. Ürün ölçütüne göre değerlendirme

Kabul ölçütü mAP **değildir**. `src/fire_metrik.gereken_recall(50, 4, 0.95)` =
**0,15**: 6 sn penceresine 50 işlenmiş kare sığıyor ve 4 kare onay için
kare-başına recall %15 yeterli.

Epoch 1'de kare-başına recall **%65,7** — eşiğin **dört katından fazla**. Yani
recall bolluğu var; kalan iş **güven eşiğini yükselterek precision satın
almaktır**.

### 6.1 Güven eşiği taraması (0,10 → 0,90)

— bekliyor — (`scripts/fire_eval.py`, test split)

### 6.2 Negatif karelerde alarm oranı

D-Fire test split'inde **2.005 negatif kare** var. "En az bir tespit üreten
negatif kare" oranı nuisance alarmın gerçek sürücüsüdür.

— bekliyor —

### 6.3 Nesne boyutuna göre recall

Küçük dilim (< 32² piksel) erken dumanı temsil eder; ortalama recall onu gizler.

— bekliyor —

### 6.4 Önerilen `fire.conf`

Seçim kuralı: recall'ı **(0,15 + marj)** üstünde tutan **en yüksek** eşik.
Marj `--marj 0.05` olarak verildi.

> **Marjın gerekçesi.** `gereken_recall` kareleri BAĞIMSIZ varsayar; gerçekte
> ardışık kareler ilintilidir (aynı poz, aynı ışık), yani hesap **iyimserdir**.
> Marjsız seçim tam sınırda durur ve sahada altına düşer.

— bekliyor —

---

## 7. Model ağırlığı

| | |
|---|---|
| Yol | `models/fire.pt` (repoya **commit edilmez**) |
| Kaynak checkpoint | — bekliyor — |
| SHA-256 | — bekliyor — |
| Boyut | — bekliyor — |

---

## 8. Bu ölçümün sınırları

1. **D-Fire dağılımına ait sonuçlardır, sahaya değil.**
   `yangin-modeli.md` bunu zaten savunuyor: doğru sıralama önce hattı çalıştırıp
   sahadan zor negatif (kaynak arkı, egzoz buharı, toz, güneş huzmesi, forklift
   farı) toplamak, fine-tune'u sonra yapmaktır. Bu koşu operatör kararıyla o
   sıradan önce yapıldı; buradaki precision sayıları müşterinin kendi yanlış
   tetikleyicileri karşısındaki performansı **temsil etmez**.
2. **Çözünürlük 512 ile sınırlı** (VRAM). Küçük nesne recall'ı etkilenmiş
   olabilir — ölçümü §6.3'te.
3. **Kare bağımsızlığı varsayımı** (§6.4) — hesap iyimser bir alt sınırdır.
4. **Üçüncü taraf ayna** (§2.1) — sayım mutabakatı güçlü, köken zinciri değil.
5. **Kamera kapasitesi ölçülmedi.** Bu modelin RTX 3050'de kaç kamera taşıdığı
   bilinmiyor; `yangin-modeli.md`'deki GB10 rakamı (worker başına ~48 kamera)
   buraya taşınamaz. Ölçülmeden kapasite planlaması yapılmamalı.

---

## 9. Üretilen dosyalar

| Dosya | İş |
|---|---|
| `scripts/dfire_parquet_ac.py` | Parquet → YOLO düzeni (ayna ham ağacı eksik olduğu için) |
| `scripts/dfire_to_coco.py` | YOLO → COCO; negatif kareleri korur, bozuk kutuyu sayarak eler |
| `scripts/fire_train.py` | RF-DETR-Small eğitimi; ayarları koşudan ÖNCE doğrular |
| `scripts/fire_eval.py` | Ürün ölçütüyle değerlendirme (mAP değil) |
| `tests/test_dfire_parquet_ac.py` · `test_dfire_to_coco.py` · `test_fire_train.py` · `test_fire_eval.py` | 65 test, model ve GPU istemez |
