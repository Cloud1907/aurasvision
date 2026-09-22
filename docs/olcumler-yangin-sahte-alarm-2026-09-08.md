# Yangın sahte alarm ölçümü — kamera-210 (ofis), 2026-09-07/08

## Bulgu
36 `fire_warning` alarmı, tamamı kamera-210 (Reolink, ofis; cam kapı + vitrin
sol %28'de). Gerçek yangın 0. Kanıt kareleri (`output/fire_eval/sahte-ofis-kamera-210/`):
- "duman": kapıdan geçen kişinin bacağı/kot pantolonu.
- "alev": vitrindeki sarı/parlak ürünler, cam yansımaları, parlak giysi.
- conf 0,35-0,63; 30 alarmın 25'i 0,45 altı. Alarm süreleri 3-5 sn (geçen kişi).

## Uygulanan (2026-09-09)
1. `zones` kind=`firemask` kamera-210: `[[0,0],[0.28,0],[0.28,0.55],[0,0.55]]` (kapı-vitrin).
2. Kişi bastırma `src/fire.py:kisi_bastir` — sayım hattının kişi kutusuyla
   kesişim/tespit-alanı ≥ `fire.person_overlap` (0,5) olan tespit atılır.
   Kutu akis motorundan gelir (`st["kisi_kutular"]`, 5 sn tazelik). Yalnız
   count/plate/face görevi de açık kamerada etkili.
3. `fire.confirm_frames` 4 → 8, `fire.alarm_seconds` 3 → 10.

Ek: dedektör yüklemesi artık yeniden denenir (5×30 sn) ve döngüden önce ana iş
parçacığında yüklenir — 2026-09-09 açılışında rfdetr import'u SigLIP yüklenirken
"kurulu değil" sanıldı ve hat kapalı kaldı. `dedektor.py` artık asıl hatayı yazar.

## Regresyon
`scripts/fire_video_dene.py --source data/videos/yangin/furg_barbecue.mp4`
(yeni eşikler): ön uyarı 0,9 sn, alarm 10,1 sn (önce 1-3 sn). Bilinçli bedel.
Sonuç: `output/fire_eval/regresyon-2026-09-09/`.

## Açık
- Canlıda sahte alarm sayısı yeniden ölçülmeli (ilk 24 saat).
- Yalnız yangın görevi açık kamerada kişi kutusu yok → bastırma çalışmaz.
- UI çizim editörü `firemask` çizdirmiyor, DB/API ile girildi.
