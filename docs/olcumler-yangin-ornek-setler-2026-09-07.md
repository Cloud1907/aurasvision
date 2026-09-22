# Yangın hattı — açık örnek setlerinde eşik ölçümü (2026-09-07)

Amaç: canlıda (kamera-210, ofis) üretilen iki sahte alarmın (güven 0,37 ve 0,38)
ardından `fire.conf` eşiğini tahminle değil ölçümle seçmek. Model bir kez düşük
eşikle (0,20) koşuldu, ham tespitler `output/fire_eval/<set>/*.tespit.json`
olarak kaydedildi; `DumanTakip` dört eşikte yeniden puanlandı (model tekrar
koşmadı). Araç: oturum scratchpad `fire_eval_batch.py` (repoya alınmadı).

Ayarlar: RF-DETR-Small `models/fire.pt`, 2×2 karo, stride 3, pencere 6 sn,
4 kare doğrulama, alarm 3 sn, KAMERA düzeyi cooldown 120 sn (bu ölçümle eklendi,
bkz. aşağı).

## Setler (repoya girmez, `data/videos/yangin/`)

| Set | Lisans | İçerik |
|---|---|---|
| FURG Fire Dataset (github.com/steffensbola/furg-fire-dataset) | CC0 | 6 yangın videosu (mangal, ev, araç, gece pil, NASA eğitim, temizlik robotu) + 1 yangınsız robot kaydı |
| FIRESENSE duman (zenodo 836749) | CC-BY 4.0 | 13 dumanlı, 9 dumansız video |
| TRASSIR saha kaydı (05.09) | — | 2 kontrollü tutuşma, bkz. `olcumler-yangin-saha-2026-09-02.md` |
| Canlı kamera-210 (07.09) | — | 2 sahte alarm: kitap üstünde turuncu nesne (0,38), cam kapıdan turuncu yansıma (0,37) |

Not: FURG ve FIRESENSE videoları yangın/duman ZATEN varken başlıyor; "ilk alarm
3,1 sn" değeri alarm_seconds'ın kendisidir, erken tespit gecikmesi değil. Gecikme
ölçümü yalnız TRASSIR saha kaydında (tutuşma anı belli) anlamlıdır.

## Sonuç

| Eşik | Alev (FURG) | Duman (FIRESENSE) | Sahte: FURG neg | Sahte: FIRESENSE neg | Sahte: canlı 07.09 | İlk alarm medyan / maks |
|---|---|---|---|---|---|---|
| 0,35 (mevcut) | 6/6 | 12/13 | 1/1 (0,45) | 2/9 (0,47 · 0,46) | 2 | 3,6 sn / 23 sn |
| **0,40** | 6/6 | 12/13 | 0/1 | 1/9 (testneg03, 0,47) | 0 | 3,8 sn / 23 sn |
| 0,45 | 6/6 | 9/13 | 0/1 | 0/9 | 0 | 3,6 sn / 11,7 sn |
| 0,50 | 6/6 | 9/13 | 0/1 | 0/9 | 0 | 3,6 sn / 14,1 sn |

- 0,35 → 0,40: hiçbir gerçek olay kaybolmuyor, altı sahte alarmın beşi gidiyor.
- 0,40 → 0,45: son sahte alarm da gidiyor ama dört duman videosu kaçıyor
  (testpos06 maks 0,55, testpos07 0,43, testpos08 0,67, testpos13 0,83 — üçünde
  eşiği geçen kare var ama 6 sn penceresinde 4 doğrulama toplanamıyor).
- Alev her eşikte 6/6; duman modelin zayıf sınıfı (maks güvenler daha düşük).
- Kaçan tek duman videosu (testpos07) 0,35'te bile yakalanmıyor (maks 0,43).

**Karar önerisi:** `fire.conf: 0.40`. Ofis/satış alanı gibi yansımalı sahnede
kalan riski eşikle değil `firemask` bölgesiyle (cam kapı, vitrin) kapatmak;
depo/atölye gibi kritik alanda 0,35'te kalıp ön uyarıyı operatöre göstermek.

## Yan bulgu: alarm fırtınası → kamera düzeyi cooldown

Cooldown odak başınaydı. Gerçek yangında alev yer değiştirdikçe IoU bağı kopar,
her yeni odak kendi ön uyarı + alarmını üretir: FURG mangal videosunda 30 sn'de
**35 alarm**, araç yangınında 18. `DumanTakip`'e kamera düzeyi cooldown eklendi:
ilk alarmdan sonra cooldown dolana dek başka odak alarm/ön uyarı yaymaz; süren
yangın cooldown sonunda tek hatırlatma verir. Aynı videoda artık 1 alarm.

## Tekrar

```
# ham tespit + puanlama (model bir kez koşar, .tespit.json varsa atlar)
.venv\Scripts\python.exe fire_eval_batch.py "data/videos/yangin/furg_*.mp4" furg
.venv\Scripts\python.exe fire_eval_batch.py "data/videos/yangin/firesense_smoke/*/*.avi" firesense
# Test ekranı: kamera seç → Yangın → Analizi çalıştır (canlı veya arşiv anı)
# CLI: python -m src.cli fire --source <video>
```
