# Onboarding kontrol listesi — derin referans

## İçindekiler
- Keşif fazı
- AGENTS.md uyarlama
- CI entegrasyonu
- Eski sistem göçü
- Doğrulama

## Keşif fazı (kod yazmadan önce)
- Dil/framework + sürüm
- Test komutu (gerçekten çalışan) · lint · build · typecheck
- Mevcut CI var mı? (varsa silme, yanına ekle)
- Riskli path'ler: auth, ödeme, migration, secret dosyaları — bunlar risk
  tablosunun `deny`/`approval` satırlarını doldurur
- Çalıştırma: nasıl ayağa kalkıyor (port, env, bağımlılık)

## AGENTS.md uyarlama (şablonu OLDUĞU GİBİ bırakma)
- Risk tablosunun path kurallarını bu repoya göre doldur
- Konvansiyonlar bölümüne reponun gerçek dilini/stilini yaz
- Gotcha'lar: bu repoda bilinen tuzaklar (varsa)
- CLAUDE.md'ye gerçek komutları koy (test/lint/build/start)

## CI entegrasyonu
- `.github/workflows/evidence.yml` checks listesine repoya özgü komutlar
- Mevcut CI job'ları korunur; evidence YANINA eklenir
- İlk mikro PR ile evidence.json üretimini kanıtla

## Eski sistem göçü (Agent Ofis projects/*.yml varsa)
Mekanizma-mekanizmaya taşı, düz metne DEĞİL:
- `forbidden` → hook/deny kuralı (bin/hooks veya AGENTS.md deny path)
- `conventions` → AGENTS.md konvansiyonlar
- `routing`/`crew` → capability profili (görev sınıfı → izinli küme)
- `validation` gate'leri → CI required checks
- MEMORY.md içeriği → docs/decisions (ADR) + AGENTS.md

## Doğrulama (bitmeden geçme)
- `python3 bin/validate.py` → tüm kontroller geçti
- `bash bin/install-hooks.sh` → push kapısı kurulu
- İlk PR'da CI yeşil + evidence.json artifact
