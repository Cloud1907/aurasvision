---
description: Backend/API/servis dosyalarında geçerli konvansiyonlar ve tuzaklar
paths:
  - "**/api/**"
  - "**/server/**"
  - "**/services/**"
  - "**/*.controller.*"
  - "**/*.service.*"
  - "**/migrations/**"
---

# Backend kuralları

Yalnız backend dosyalarıyla çalışırken yüklenir (path-scoped). Derin denetim
`security-review`, uygulama disiplini `implement-change` skill'lerindedir;
bu dosya günlük backend refleksleridir.

## Zorunlu
- Girdi bir güven sınırını geçiyorsa (HTTP → SQL/shell/dosya/şablon) doğrula/
  parametrele/kaçır. Ham string birleştirme ile sorgu kurma.
- Her nesne erişiminde sahiplik/tenant kontrolü — "giriş yapmış" ≠ "yetkili".
- Yazma işlemleri idempotent olmalı (tekrar çağrı veri bozmasın).
- Transaction sınırını açık çiz; kısmi yazma bırakma.

## Yasak
- Boş `catch`/`except` — hata yutma. En az logla, mümkünse yükselt.
- Secret'ı koda/loga/repoya yazma. Config'ten, kısa ömürlü token'dan al.
- Prod migration'ı `deny` sınıfı dışında çalıştırma (geri alınamaz).

## Tuzaklar
- N+1 sorgu: döngü içinde sorgu → toplu çekime çevir.
- Race condition: eşzamanlı yazımda kilit/atomik işlem/optimistic concurrency.
- Sözleşme kırma: mevcut API yanıt şeklini değiştirme; sürümle veya geriye uyumlu ekle.
