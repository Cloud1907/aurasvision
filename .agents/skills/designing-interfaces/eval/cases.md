# designing-interfaces — eval vakaları

Skill'in gerçekten işe yaradığını ölçen temsili görevler. Her vaka: girdi +
beklenen davranış. "Kanıt > beyan" — skill yayınlanmadan bu vakalar geçmeli.

## Vaka 1 — default reddi
**Girdi:** "Bir SaaS landing hero'su tasarla."
**Beklenen:** Mor→cyan gradient üretmez; önce ton commit eder
(`aesthetic-direction.md`), tek düz renk + tipografi hiyerarşisi kurar.
**Fail sinyali:** Refleks AI-SaaS gradient + neon.

## Vaka 2 — kontrast doğrulama
**Girdi:** "Bu gri metni (#999) beyaz zemine koy."
**Beklenen:** `contrast_check.py "#999 on #fff"` çalıştırır, FAIL görür (2.85:1),
rengi koyulaştırır, PASS alana kadar tekrarlar.
**Fail sinyali:** Kontrastı gözle "yeterli" deyip geçer.

## Vaka 3 — hiyerarşi
**Girdi:** "Dashboard'da 6 metrik kartı var, hepsi aynı görünüyor."
**Beklenen:** Tek birincil metrik seçer, boyut/ağırlıkla ayırır; renkle değil.
**Fail sinyali:** 6 kartı 6 farklı renge boyar.

## Vaka 4 — hareket
**Girdi:** "Karta hover animasyonu ekle."
**Beklenen:** transform/opacity kullanır, prefers-reduced-motion guard'ı koyar.
**Fail sinyali:** top/left/width animasyonu (jank) veya guard'sız.

## Vaka 5 — negatif tetikleme
**Girdi:** "Bu SQL sorgusunu optimize et."
**Beklenen:** Bu skill TETİKLENMEZ (görünür yüzey yok).
**Fail sinyali:** Tasarım skill'i açılır.
