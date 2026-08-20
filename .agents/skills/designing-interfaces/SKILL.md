---
name: designing-interfaces
description: Görünür UI/tasarım işini dünya standardı kaliteye taşır — tipografi, renk, boşluk, hiyerarşi, hareket ve erişilebilirlik kararlarını ilke+karşı-örnekle yönlendirir ve iki-geçişli self-critique ile şablon/AI-default görünümü reddeder. Kullanıcı bir ekran/sayfa/bileşen tasarla, yeniden tasarla, "premium yap", "güzelleştir", dashboard/landing kur dediğinde kullan. Salt backend, sorgu, test veya metin işinde kullanma.
---

# Designing interfaces

Amaç: çıktı "template" değil, kasıtlı görünsün. Bu skill sana font/renk
DAYATMAZ; bağlama göre nasıl seçeceğini öğretir ve default'a kaçmanı engeller.

## Ne zaman geçerli
Görünür bir yüzey üretiliyor veya değiştiriliyorsa (view, component, sayfa,
dashboard, landing, e-posta). Salt iş mantığı/API/sorguda DEĞİL.

## İş akışı (checklist — kopyala ve işaretle)
- [ ] 1. Tonu commit et: bu ürün ne hissettirmeli? (referans: `references/aesthetic-direction.md`)
- [ ] 2. Design token'ları tanımla: tipografi ölçeği, renk rolleri, boşluk birimi, köşe, gölge (referans: `references/design-tokens.md`)
- [ ] 3. Hiyerarşi kur: göz nereye önce gitmeli? Boyut/ağırlık/renk kontrastıyla (referans: `references/layout-hierarchy.md`)
- [ ] 4. İnşa et — token'ları kullan, sihirli sayı yazma.
- [ ] 5. Birinci critique: "default'a mı kaçtım?" (aşağıdaki ret listesi)
- [ ] 6. Erişilebilirlik + kontrast doğrula: `python3 scripts/contrast_check.py` (referans: `references/accessibility.md`)
- [ ] 7. İkinci critique: hareket 60fps mi (yalnız transform/opacity)? Reduced-motion guard var mı?

## Zorunlu ret listesi (bunları üretirsen dur ve yeniden düşün)
- Commodity font (yalnız system-ui/Arial default'u) — niyetli bir seçim yap.
- Mor→cyan gradient, neon glow, pulsing halo, sparkle/robot/brain ikonu:
  "AI-SaaS default"u. Premium = kısıtlılık, ışıltı değil.
- Her yeri ortalamak, tek tip 16px, her şeye eşit ağırlık: hiyerarşisizlik.
- Gölge+blur+gradient yığmak. Bir öğe en fazla bir vurgu tekniği.
- Emoji-birincil UI, büyük renkli ikon dansı.

## High-signal gotcha'lar (bu sistemin/bu projenin bilmen gerekenleri)
- Anlam katmanı dürüstlüğü: durum etiketlerinde "Yetim" gibi yargı sözcüğü değil,
  "Doğrulanmadı" gibi dürüst sözlük kullan (Agent Ofis anlam katmanı dersi).
- reduced-motion: hareket eklerken `prefers-reduced-motion` guard'ı zorunlu.
- Dark mode: her renk iki temada da okunmalı; hardcoded #333 dark'ta kör.
- Contrast validator PASS vermeden UI "bitti" sayılmaz — kanıt > beyan.

## Validation loop
`python3 scripts/contrast_check.py <renk-çiftleri>` → FAIL varsa renk/rol
düzelt → tekrar çalıştır → PASS. Bu, öznel "okunur mu" sorusunu WCAG
oranıyla ölçülebilir yapar.

## Çıktı
Önce/sonra ekran görüntüsü + hangi token'ların kullanıldığı + contrast PASS
çıktısı. UI işinde screenshot kanıt zorunludur.
