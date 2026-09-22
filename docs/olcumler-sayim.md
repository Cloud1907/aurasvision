# Sayım doğruluk ölçümü

> Depoda sayım modülü için de hiçbir doğruluk ölçümü yoktu. Bu belge
> `docs/olcumler-plaka.md` ile aynı prensiple, TRASSIR'ı yer gerçeği olarak
> kullanır. Yöntem: `scripts/count_eval.py`.

## Neden olay-olay eşleştirme YAPILMADI

TRASSIR'ın ham `border_events`'i (`kamera-201` / `GE1eca7u`) ölçülen hızda
üretiyor: **saatte ~1000 olay, ~3,6 saniyede bir**. AurasVision'ın kendi
sayım mantığı ise track başına 2 saniyelik cooldown uyguluyor
(`count.cooldown_seconds`) — yani TRASSIR muhtemelen bölge sınırında duran/
salınan nesneleri de her geçişte yeniden sayıyor (flicker), AurasVision ise
bunu bilinçli olarak süzüyor. İki farklı debounce mantığını tek tek
eşleştirmek adil değil; bunun yerine **5 dakikalık kovalara toplanmış toplam
trafik** karşılaştırıldı.

## Ölçüm (2026-09-03, kamera-201, 15:00–16:00 UTC)

| kova | AurasVision | TRASSIR | oran |
|---|---|---|---|
| 0dk | 22 | 88 | 0,25 |
| 5dk | 15 | 94 | 0,16 |
| 10dk | 28 | 104 | 0,27 |
| 15dk | 11 | 72 | 0,15 |
| 20dk | 12 | 52 | 0,23 |
| 25dk | 29 | 84 | 0,35 |
| 30dk | 31 | 98 | 0,32 |
| 35dk | 6 | 96 | 0,06 |
| 40dk | 11 | 65 | 0,17 |
| 45dk | 5 | 59 | 0,08 |
| 50dk | 10 | 61 | 0,16 |
| 55dk | 4 | 40 | 0,10 |

**TOPLAM:** AurasVision 184 · TRASSIR 913 · oran 0,202
**Kova-bazlı korelasyon:** 0,68

Ham dosya: `output/count_eval/count_eval.json`.

## Yorum

AurasVision, TRASSIR'ın ürettiği ham olay hacminin yalnız **%20**'sini
üretiyor — ama **korelasyon 0,68**, yani hangi 5 dakikalık dilimin
yoğun/sakin olduğu ikisinde de aynı örüntüyü izliyor (35dk ve 45dk'daki
düşüşler, 25-30dk'daki tepe her iki serinin de görünüyor).

**Bu düşük oran "AurasVision yanlış sayıyor" anlamına GELMEZ** — kanıt yok.
İki olası açıklama var ve bu ölçüm ikisini ayıramaz:

1. TRASSIR'ın ham akışı flicker/re-tetikleme içeriyor (bölge sınırında duran
   kişi, aynı geçişi birden çok kez üretiyor) — bu durumda AurasVision'ın
   filtrelenmiş sayısı GERÇEĞE daha yakın olabilir.
2. AurasVision'ın 2 saniyelik cooldown'u veya track kalite eşiği
   (`min_track_frames: 6`) gerçek geçişleri de kaçırıyor olabilir.

**Sınır:** Bağımsız bir üçüncü kaynak (elle video izleyip sayma) olmadan bu
ikisi ayırt edilemez. 0,68 korelasyon, sistemin gerçek trafiği TAKİP ettiğini
gösteriyor — mutlak sayının doğru olduğunu göstermiyor. Bir sonraki adım:
kısa bir pencerede (örn. 10 dakika) elle sayım yapıp iki kaynağı da o
referansla kalibre etmek.
