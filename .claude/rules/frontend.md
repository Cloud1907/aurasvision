---
description: Frontend/UI dosyalarında geçerli konvansiyonlar ve tuzaklar
paths:
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.vue"
  - "**/*.css"
  - "**/components/**"
  - "**/web/**"
---

# Frontend kuralları

Bu kurallar yalnız UI dosyalarıyla çalışırken yüklenir (path-scoped —
backend/docs oturumunda context'e girmez). Derin tasarım işi için
`designing-interfaces` skill'i devreye girer; bu dosya günlük frontend
disiplinidir.

## Zorunlu
- Hareket yalnız `transform`/`opacity` (layout/paint tetikleyen `top`/`width`
  değil) → 60fps. `prefers-reduced-motion: reduce` guard'ı ekle.
- Dark mode: her renk iki temada da okunur olmalı; hardcoded `#333` dark'ta kör.
  Renkleri CSS değişkeni/token üzerinden kullan.
- Etkileşimli öğe klavyeyle erişilebilir; görünür focus; dokunma hedefi ≥44px.
- Serbest metni `dangerouslySetInnerHTML` ile basma (XSS) — güvenli renderer kullan.

## Yasak (bu projelerin kararı)
- AI-SaaS default'u: mor→cyan gradient, neon glow, pulsing halo, sparkle/robot/
  brain ikonu, emoji-birincil UI. Premium = kısıtlılık.
- Durum etiketinde yargı sözcüğü ("Yetim") — dürüst sözlük ("Doğrulanmadı").
- Sihirli sayı: boşluk/tipografi token'dan gelir, rastgele 13px yok.

## Tuzaklar
- Gereksiz re-render: bağımlılık dizilerini ve memoization'ı kontrol et.
- State senkronu: tek doğruluk kaynağı; türetilmiş state'i ayrı tutma.
