# Yangın erken uyarısı — pilot işletim ve saha kabul runbook'u

## Güvenlik sınırı

Bu özellik **sertifikalı yangın alarm sistemi değildir** ve EN 54 yangın
algılama/ihbar sisteminin yerine geçmez. Mevcut dedektör, santral, siren,
tahliye ve itfaiye süreçleri aynen kalır. AurasVision yalnız operatöre ek bir
video erken-uyarı sinyali verir. Pilot boyunca herhangi bir röle, siren,
tahliye veya söndürme mekanizması AurasVision tarafından otomatik çalıştırılmaz.

## Mevcut sinyal yolu

1. RF-DETR karede `smoke` veya `fire` tespiti üretir.
2. Aynı fiziksel odak, sınıf kareler arasında değişse bile IoU ile izlenir.
3. Altı saniyelik pencerede dört doğrulama `on_uyari` üretir.
4. Doğrulama üç saniye daha kesintisiz sürerse `alarm` oluşur.
5. İki saniyeden uzun tespit boşluğu eski doğrulamayı sıfırlar.
6. Ön uyarı `fire_events` tablosuna yazılır; webhook gönderilmez.
7. Alarm; `fire_events`, bekleyen `alerts`, kanıt karesi/klibi ve yapılandırılmış
   webhook mesajı üretir.

Alarm tüketicileri bugün şunlardır:

| Tüketici | Durum | Sınır |
|---|---|---|
| Masaüstü Olaylar ekranı | Var | Operatörün ekranı açık olmalı |
| Mobil Alarm Merkezi | Var | Push notification değildir; ekran/polling gerekir |
| Veritabanı `alerts` kaydı | Var | Operatör kabulü elle yapılır |
| `bildirim.webhook_url` | Opsiyonel | 3 sn timeout, tek deneme; teslim alındısı/retry kuyruğu yok |
| Siren/röle/SMS/e-posta/itfaiye | Yok | Pilot kapsamı dışında; otomatik aktüasyon yasak |

Webhook alıcısı başarısız olursa alarm veritabanında kalır ve hata loga yazılır,
ancak bugün teslim garantisi yoktur. Pilot vardiyasında bu nedenle ana bildirim
kanalı panel, webhook ise yardımcı kanaldır.

## Devreye alma kapıları

Sırayla ve tamamı geçmeden kamerada yangın görevi açılmaz:

- `models/fire.pt` mevcut olmalı; genel amaçlı YOLO ağırlığı kabul edilmez.
- Modelin SHA-256 değeri ölçüm kaydına yazılmalı ve değiştirilmemeli.
- `rfdetr` çalışma-anı paketi bulunmalı; `/api/capabilities` içinde
  `fire.available=true` görülmeli.
- Model, D-Fire test split'inde `scripts/fire_eval.py` ile değerlendirilip güven
  eşiği belirlenmeli.
- Aşağıdaki müşteri videosu kabulü geçmeli.
- Kamera başına izleme ve yanlış-alarm maske bölgeleri çizilmeli.
- Vardiya sorumlusu panel alarmını ve webhook alıcısını test etmeli.
- Sertifikalı sistemin çalışır olduğu bağımsız olarak doğrulanmalı.

## Müşteri videosu kabulü

Dosya: `TRASSIR-4.9.9.0-1308508 2026-09-02 09-22-42.mp4`

Manuel görüntü incelemesiyle kullanılan başlangıç işaretleri:

| Aralık | Etiket | Not |
|---|---|---|
| 00:00–07:55 | negatif | Görünür alevden önceki bölüm |
| 07:56–14:44 | pozitif | Görünür alevin sürdüğü bölüm |
| 14:44 sonrası | ölçüm dışı | Söndürme bulutu ve artık duman; negatif sayılmaz |

Bu sınırlar otomatik gerçek değildir; müşteri/yangın uzmanı kare bazında değiştirirse
komut da güncellenir. Kabul komutu:

```bash
.venv/bin/python scripts/fire_video_eval.py \
  --video "/Users/cloudsmac/Downloads/TRASSIR-4.9.9.0-1308508 2026-09-02 09-22-42.mp4" \
  --positive-start 07:56 \
  --positive-end 14:44 \
  --negative 00:00-07:55 \
  --max-alarm-latency 10 \
  --max-detection-gap 2
```

Kabul için üç koşul birlikte sağlanır:

- İlk alarm görünür alev başlangıcından en geç 10 saniye sonra gelmeli.
- Pozitif aralıkta ardışık ham tespitler arasındaki en uzun boşluk en çok 2 saniye olmalı.
- Negatif aralıkta alarm oluşmamalı.

Araç `output/fire_video_eval.json` üretir. Sonucun `status=passed` ve
`passed=true` olması gerekir. Rapor video yolu, model SHA-256, motor, güven
eşiği, alarm gecikmesi ve en uzun tespit boşluğunu birlikte taşır. Model/paket
yoksa `status=blocked` ve çıkış kodu 2 üretir; bu durum başarısız test değil,
eksik önkoşuldur ve devreye alma yine durur.

## Vardiya müdahalesi

Yangın erken uyarısı görülünce operatör:

1. İlgili kamerayı ve kanıt klibini hemen açar.
2. Tesisin mevcut yangın acil durum prosedürünü uygular; AurasVision sonucunu
   tek doğruluk kaynağı olarak kullanmaz.
3. Alarmı yalnız gördükten ve prosedürü başlattıktan sonra panelde kabul eder.
4. Yanlış alarm ise sahneyi, saati ve tetikleyiciyi (kaynak, buhar, toz, güneş,
   forklift farı vb.) kaydeder; maske/eşik değişikliği doğrudan üretimde yapılmaz.
5. Worker sağlık durumu `degraded` veya `error` ise görev ayrıntısını kaydeder ve
   sertifikalı alarm sistemine güvenerek teknik sorumluya eskale eder.

## Pilot ölçümleri

Her vardiya sonunda şu sayılar raporlanır: gerçek olay sayısı, yakalanan olay,
ilk alarm gecikmesi, yanlış alarm sayısı/saat, en uzun tespit boşluğu, görev
restart/park sayısı, webhook teslim hatası ve operatör kabul süresi. İlk pilotta
eşik değiştirme kararı tek videoya değil saha yanlış-negatiflerine ve zor
negatiflerine dayanır.

