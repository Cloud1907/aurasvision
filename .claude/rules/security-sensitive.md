---
description: Güvenlik-duyarlı yüzeylerde (auth, secret, migration) ek dikkat
paths:
  - "**/auth/**"
  - "**/*.env*"
  - "**/secrets/**"
  - "**/migrations/**"
  - "**/payment/**"
---

# Güvenlik-duyarlı yüzey

Bu path'ler risk politikasında (AGENTS.md) `approval` veya `deny` sınıfını
tetikler. Bu dosya yüklendiyse dikkatli ol.

## Zorunlu
- Bu yüzeye dokunan diff `security-review` skill'inden geçmeli (taze bağlam).
- Risk otomatik yukarı eskale olur; auto akışta merge'e hazır sayma.
- `.env`, secret, credential dosyalarına yazma = `deny`. Örnek/şablon
  (`.env.example`) hariç; gerçek değer asla repoya girmez.

## Break-glass
Zorunlu bir `deny` işlemi gerekiyorsa: süreli + gerekçeli + kayıtlı olmalı;
işlem sonrası yetki geri alınır. Sessiz istisna yok.
