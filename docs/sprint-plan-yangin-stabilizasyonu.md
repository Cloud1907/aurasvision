# Sprint planı: Yangın erken uyarısı pilot stabilizasyonu

**Tarih:** 7–18 Eylül 2026  
**Takım varsayımı:** tek kurucu/geliştirici, 10 iş gününün %80'i = 8 odak günü  
**Sprint hedefi:** Sabitlenmiş bir model artefaktıyla müşteri videosu kabulünü
geçen, arızası görünür ve sertifikalı sistemi tamamlayıcı bir pilot sürüm üretmek.

Takım takvimi paylaşılmadığı için kapasite varsayımdır; iki günlük kesinti payı
bilinçli olarak ayrılmıştır.

## Sprint öncesi tamamlanan teknik borç

- Zamansal takibe iki saniyelik boşluk reseti ve alev/duman sınıf geçişi eklendi.
- Görevler bağımsız supervisor, sınırlı yeniden deneme, üstel backoff ve `parked`
  sağlık durumuna alındı.
- Yangın kameraları NVDEC hattından güvenli ayrıldı; çalışma-anı geri düşüşünde
  aynı RTSP akışının iki kez açılması engellendi.
- Fire event PostgreSQL/Timescale kurulumu, sıkıştırma ve retention politikaları
  eklendi.
- Operatöre model/paket/lisans önkoşulu ve görev hata ayrıntısı görünür kılındı.
- Olay özetindeki toplam/sayım çifte sayımı ayrıldı.
- Müşteri videosu için tekrarlanabilir kabul aracı ve bu runbook eklendi.

## Kapasite

| Kaynak | Kullanılabilir | Planlanan | Not |
|---|---:|---:|---|
| Kurucu/geliştirici | 10 gün | 8 gün | 2 gün destek/arıza tamponu |

## Sprint backlog'u

| Öncelik | İş | Tahmin | Bağımlılık / çıkış ölçütü |
|---|---|---:|---|
| P0 | Eğitimi tamamla, seçilen checkpoint'i `models/fire.pt` olarak teslim et; SHA-256 kaydet | 1,0 gün | Eğitim makinesi/checkpoint |
| P0 | D-Fire test split'inde eşik taraması ve küçük-nesne recall ölçümü | 1,0 gün | Model artefaktı; `fire_eval.json` |
| P0 | Müşteri videosu kabulünü çalıştır ve gerekirse yalnız ölçüme dayalı eşik ayarla | 1,5 gün | İlk alarm ≤10 sn, boşluk ≤2 sn, pre-fire alarm=0 |
| P0 | Panel + mobil + webhook uçtan uca saha testi; alarmı operatör kabul etsin | 1,0 gün | Test alarmı DB/kanıt/UI/webhook'ta görünür |
| P0 | CI/test/kalite kapılarını yeşile getir, bağımsız diff incelemesi al | 1,0 gün | Tüm kapılar yeşil; P0/P1 bulgu yok |
| P1 | Webhook için kalıcı outbox, retry ve teslim durumu tasarla/uygula | 1,5 gün | Yeniden başlatmada kaybolmayan teslim; idempotency |
| P1 | Kamera bazlı zor negatif toplama ve etiketleme prosedürünü başlat | 0,5 gün | En az kaynak/buhar/toz/ışık örnekleri |
| P2 | Vardiya metriği ve alarm teslim dashboard'u | 0,5 gün | Stretch; P0 gecikirse kesilir |

**Planlanan yük:** 8,0 gün / 8,0 gün kapasite. P2 ilk kesilecek iştir; webhook
outbox tamamlanmazsa pilotta panel ana kanal olarak kalır ve bu açıkça imzalanır.

## Riskler ve azaltma

| Risk | Etki | Azaltma |
|---|---|---|
| Model/checkpoint erişilemiyor | Video kabulü hiç başlayamaz | Artefakt sahibi, yol ve SHA aynı gün netleştirilir; blokaj gizlenmez |
| Tek videoya aşırı uyum | Sahada yanlış güven | D-Fire negatifleri + tesis zor negatifleri ayrı tutulur |
| Extinguisher bulutu duman sayılır | Yanlış negatif etiketiyle eşik bozulur | 14:44 sonrası bu kabulün negatif aralığı değildir |
| Webhook tek deneme | Harici bildirim kaybı | P1 outbox; o zamana dek panel ana kanal ve vardiya kontrolü |
| Kamera/GPU kapasitesi ölçülmedi | Kare boşluğu ve geç alarm | Pilot kamera sayısını sınırlı tut; gerçek FPS/health ölç |
| Video analitiği sertifikalı sanılır | Can güvenliği/hukuk riski | UI etiketi, runbook, eğitim ve otomatik aktüasyon yasağı |

## Bitti tanımı

- Sabit model SHA'sı ve kaynağı ölçüm belgesinde kayıtlıdır.
- D-Fire ürün metriği ve müşteri videosu JSON raporları saklanmıştır.
- Müşteri videosu üç kabul koşulunun tamamını geçmiştir.
- Panel, mobil, DB, kanıt ve yapılandırılmış webhook alarmı uçtan uca görülmüştür.
- Worker çöküşü görev ayrıntısıyla görünür; kardeş görev çalışmaya devam eder.
- Kod incelemesi ve tüm yerel/CI kapıları yeşildir.
- Müşteri, özelliğin sertifikalı yangın alarmının yerine geçmediğini kabul etmiştir.
