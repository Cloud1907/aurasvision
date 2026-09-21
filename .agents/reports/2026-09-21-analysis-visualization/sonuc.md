# Analiz görselleştirmesi — doğrulama kaydı

Sözleşme: #6

## Görsel kanıt

- `desktop-light.png`: 1440×1000 açık tema, V4 çalışma alanı ve trend kartı.
- `desktop-dark.png`: 1440×1000 koyu tema, aynı veri ve kontrast kontrolü.
- `mobile-light.png`: 390×844 mobil görünüm; yatay taşma olmadan trend kartı.
- `people-detection_count.mp4`: örnek kişi analizi; editörle aynı amber çizgi,
  seçili A→B yön oku ve kadraj içinde tutulan etiket.

Görüntüler temsili fixture verisiyle, video ise yerel örnek kaynakla üretildi.
Kaynak video ayrıca çoğaltılmadı; yalnız analiz katmanı işlenmiş örnek sonuç
eklendi. Kimlik eşleştirmesi veya biyometrik çıktı içermez.
Video 49,5 saniye / 198 işlenmiş karede 2 giriş ve 1 çıkış olayı üretti.

## Otomatik kanıt

- Python regresyonları: `tests/test_analysis_visualization.py`
- Tarayıcı regresyonları: `e2e/ui-command-center.spec.ts`
- UI derleme: `npm run build:ui`
- Proje kapıları: `bin/validate.py`, `bin/kalite.py --check`, pre-push ve CI
