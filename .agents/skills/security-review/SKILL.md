---
name: security-review
description: Diff'i OWASP 2025 temelli güvenlik denetiminden geçirir — erişim kontrolü (IDOR/tenant), injection (SQLi/XSS/traversal/upload), secret sızıntısı ve misconfig arar; her bulgu dosya:satır + somut istismar senaryosu olur. Diff auth/kimlik/oturum/ödeme/upload/migration yüzeyine dokunduğunda veya risk sınıfı approval/deny olduğunda kullan. Genel kod kalitesi/stil incelemesi veya kendi yazdığın kodu onaylamak için kullanma.
# "Bulur, kanıtlar, devreder — bu skill kod yazmaz" cümlesi artık mekanizma
# (2026-08-15): denetim turunda yazma araçları kapalıdır. Düzeltmeyi ilgili
# rol ayrı bir turda yapar; denetçinin kendi düzeltmesini onaylaması,
# bağımsızlığın kaybolduğu andır.
disallowed-tools: Write Edit NotebookEdit
---

# security-review

Amaç: bir diff'i saldırgan gözüyle white-box denetlemek ve sömürülebilir
güvenlik açıklarını kanıtla ortaya koymak. Bu skill kalite/stil incelemesi
DEĞİL; "bu kod nasıl kötüye kullanılır?" sorusunun peşinden gider. Bulgu
üretme baskısı değil, **doğrulanmış istismar** ölçüttür.

## Ne zaman geçerli

Aşağıdakilerden biri doğruysa TETİKLE:
- Diff auth / kimlik / oturum / yetkilendirme / ödeme / dosya upload /
  DB migration / secret-config yüzeyine dokunuyor.
- İşin risk sınıfı `approval` veya `deny` (AGENTS.md risk politikası).
- Kullanıcı verisi bir güven sınırını geçiyor (HTTP girdisi → sorgu, dosya,
  komut, şablon, redirect, deserializasyon).

Şunlarda TETİKLEME:
- Salt doküman/test/stil/refactor diff'i, görünür güvenlik yüzeyi yok.
- **Kendi bu oturumda yazdığın kodu** denetliyorsan — taze bağlamlı ayrı
  koşu ister (agent kendi işini onaylayamaz, AGENTS.md).

## İş akışı (checklist — kopyala ve işaretle)

- [ ] 1. **Yüzeyi sınıfla.** Diff'in dokunduğu her hunk'ı işaretle:
      erişim kontrolü / injection / kimlik-oturum / secret-config /
      bağımlılık. Her sınıfın kendi referansı var (aşağıda).
- [ ] 2. **Güven sınırlarını çiz.** Girdi nereden geliyor (query, body,
      header, path, cookie, upload, 3. taraf webhook)? Nereye akıyor
      (SQL, shell, dosya yolu, HTML, redirect, log)? Her sınır bir
      denetim noktasıdır.
- [ ] 3. **Erişim kontrolü.** Her yeni/değişen endpoint için:
      "başka kullanıcının kaynağını isteyebilir miyim?" (referans:
      `references/access-control.md`). OWASP #1 — en sık kaçırılan.
- [ ] 4. **Injection & girdi doğrulama.** Her güven sınırında parametreleme /
      kaçış / allowlist var mı? (referans: `references/injection.md`)
- [ ] 5. **Secret taraması (deterministik).**
      `python3 scripts/scan_secrets.py <diff-dosyaları-veya-dizin>` →
      bulgu varsa exit 1, merge durur.
- [ ] 6. **OWASP 2025 geçişi.** 10 kategoriyi hızlı tara, atlanan sınıf var
      mı? (referans: `references/owasp-2025.md`)
- [ ] 7. **Misconfig & kimlik.** CORS `*`+credentials, güvenlik header'ları,
      rate-limit, debug bayrağı, token ömrü, oturum sabitleme, parola/token
      loglama.
- [ ] 8. **Bağımlılık.** Yeni paketin bilinen CVE'si, sürüm sabitleme,
      typosquat şüphesi.
- [ ] 9. **Hüküm ver** (aşağıdaki şiddet cetveli + çıktı formatı).

## High-signal gotcha'lar (bu iş tipinin bilmen gerekenleri)

- **Kimlik doğrulama ≠ yetkilendirme.** "Giriş yapmış" olmak "bu kaynağa
  erişebilir" demek değil. En yaygın gerçek açık: authenticate edilmiş ama
  authorize edilmemiş endpoint (IDOR). Her nesne erişiminde sahiplik/tenant
  kontrolü ara.
- **Client-side kontrol güvenlik değildir.** UI'da butonun gizlenmesi,
  frontend rol kontrolü, gizli form alanı — hepsi bypass edilir. Yetki
  kararı sunucuda olmalı.
- **Bulgu üretme baskısına direnç.** Erişilemez/teorik senaryoyu "CRITICAL"
  diye şişirme; bunu ayrı "bilgi" olarak yaz. Yanlış-pozitif, skill'in
  güvenilirliğini yakar. Şüpheliyse istismar adımını yazmayı dene —
  yazamıyorsan muhtemelen bulgu değil.
- **Diff dışına bakmak gerekir.** Bir çağrı güvenli görünebilir ama çağırdığı
  fonksiyonun içi diff'te değildir. Yetki/doğrulama kontrolünün gerçekten
  var olduğunu, diff dışındaki kaynağı okuyarak doğrula — varsaymak yerine.
- **Log & hata mesajı sızıntısı.** Stack trace, SQL hatası, token/parola/PII
  loglama sessiz açıklardır; grep'te `console.log`, `print`, `logger` +
  `password`/`token`/`secret` yakınlığına bak.
- **Kaçış != doğrulama.** HTML kaçışı XSS'i durdurur ama SSRF/path-traversal'ı
  durdurmaz. Her sink kendi savunmasını ister; tek savunmayı her yere uygulama.
- **Migration = geri alınamaz.** `deny` sınıfı. Veri silen/kolon düşüren
  migration'da rollback ve veri-kaybı etkisini açıkça sorgula.

## Şiddet cetveli ve hüküm

| Şiddet | Ölçüt | Davranış |
|---|---|---|
| CRITICAL | Kimlik doğrulamasız/tek adımda sömürülür; veri sızıntısı, RCE, auth bypass | Sert VETO — merge durur |
| HIGH | Sömürülebilir ama koşul/ön-erişim gerektirir; IDOR, saklı XSS | VETO — merge durur |
| MEDIUM | Sınırlı etki veya zorlu ön-koşul; savunma derinliği eksiği | PR'a not, merge kararı insanda |
| LOW | En iyi pratik ihlali, doğrudan sömürü yolu yok | PR'a not |
| BİLGİ | Teorik/erişilemez; sertleştirme önerisi | Ayrı bölüm, veto değil |

CRITICAL/HIGH bulgu bir tanesi bile varsa hüküm **VETO**'dur. Agent kendi
risk sınıfını düşüremez (AGENTS.md).

## Validation loop

1. `python3 scripts/scan_secrets.py <yol>` → exit 1 ise secret var, temizle,
   tekrar çalıştır → exit 0 alana kadar. Bu, "secret var mı?" öznel sorusunu
   deterministik kapıya çevirir.
2. Her CRITICAL/HIGH bulgu için istismar adımını **yaz**. Yazamıyorsan
   şiddeti düşür veya BİLGİ'ye taşı — kanıtsız veto yapma.
3. Diff dışı bağımlılık iddiası (yetki kontrolü var/yok) için kaynağı **oku**,
   varsayma.

## Çıktı formatı

Her bulgu:

```
[ŞİDDET] Başlık — kısa açıklama
  Konum: path/dosya.ext:satır
  İstismar: <somut adım — "şu isteği atarsam şu olur">
  Düzeltme: <tek cümle önerilen savunma>
```

Sonda:
- **Hüküm:** VETO (CRITICAL/HIGH varsa) veya GEÇ (yalnız MEDIUM/LOW/BİLGİ).
- **Secret taraması:** `scan_secrets.py` exit kodu (0/1).
- **Kapsam notu:** denetlenen yüzeyler + diff dışı okunan dosyalar.

Bulur, kanıtlar, devreder — bu skill kod yazmaz, düzeltmeyi ilgili role bırakır.

## Referanslar

- `references/owasp-2025.md` — OWASP Top 10:2025 kürasyonlu kontrol listesi.
- `references/access-control.md` — IDOR, multi-tenant izolasyon, yetki bypass
  desenleri + somut istismar örnekleri.
- `references/injection.md` — SQLi/XSS/path-traversal/upload doğrulama,
  dil-agnostik + örnek.
- `scripts/scan_secrets.py` — bağımlılıksız deterministik secret tarayıcı.
- `eval/cases.md` — temsili vakalar (biri negatif tetikleme).
