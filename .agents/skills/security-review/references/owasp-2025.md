# OWASP Top 10:2025 — kürasyonlu denetim listesi

Bu ham standart metni değil, **diff denetiminde ne aranacağının** kürasyonlu
listesidir. Her kategori: kısa tanım + diff'te aranan sinyal + hızlı istismar
sorusu. Sırayla geç; atlanan sınıf kalmasın.

## İçindekiler
- A01 Broken Access Control
- A02 Security Misconfiguration
- A03 Software Supply Chain Failures
- A04 Cryptographic Failures
- A05 Injection
- A06 Insecure Design
- A07 Authentication Failures
- A08 Software & Data Integrity Failures
- A09 Logging & Alerting Failures
- A10 Mishandling of Exceptional Conditions
- Kullanım notu

---

## A01 — Broken Access Control
En sık ve en yüksek etkili kategori. Ayrıntı: `access-control.md`.

**Diff sinyali:**
- Yeni/değişen endpoint, route, controller aksiyonu.
- İstek parametresiyle nesne çeken sorgu (`WHERE id = :id`) — sahiplik/tenant
  filtresi var mı?
- Rol/izin kontrolünün kaldırılması, gevşetilmesi veya yalnız client tarafında
  yapılması.
- `is_admin`, `role`, `tenant_id` gibi alanların kullanıcı girdisinden gelmesi.

**İstismar sorusu:** Kendi oturumumla, başka kullanıcının/tenant'ın id'sini
koyarsam kaynağı görür/değiştirir miyim? Yetki kontrolünü atlayan doğrudan
URL/endpoint var mı?

## A02 — Security Misconfiguration
Güvensiz varsayılan, gereksiz açık yüzey, eksik sertleştirme.

**Diff sinyali:**
- `DEBUG=true`, ayrıntılı hata/stack trace prod'a açık.
- CORS `Access-Control-Allow-Origin: *` + `Allow-Credentials: true` (tehlikeli
  bileşim).
- Eksik güvenlik header'ları (CSP, HSTS, X-Content-Type-Options, X-Frame-Options).
- Açık yönetim endpoint'i, actuator, `/debug`, default kimlik bilgisi.
- Bulut deposu/DB'nin herkese açık ayara alınması, gereksiz port.
- Rate-limit yokluğu (brute-force/enumeration yüzeyi).

**İstismar sorusu:** Hata mesajı bana iç yapıyı sızdırıyor mu? Yabancı origin
credential ile istek atabilir mi?

## A03 — Software Supply Chain Failures
Bağımlılık, build, CI/CD ve 3. taraf bileşen zinciri.

**Diff sinyali:**
- Yeni bağımlılık: bilinen CVE'si var mı, sürüm sabitlenmiş mi (lockfile),
  typosquat adı mı?
- Sabitlenmemiş sürüm (`^`, `*`, `latest`), doğrulanmamış kaynak/registry.
- CI pipeline'a dış script `curl | bash`, pin'siz action (`@main`).
- Build çıktısına imza/checksum doğrulaması eksik.

**İstismar sorusu:** Bu paketin bakımı düşerse veya ele geçerse benim
build'ime ne enjekte edilir?

## A04 — Cryptographic Failures
Hassas verinin zayıf/yanlış kriptografiyle korunması veya korunmaması.

**Diff sinyali:**
- Parola için düz metin veya hızlı hash (MD5/SHA1); bcrypt/argon2/scrypt yok.
- Sabit/hardcoded IV, key, salt; `ECB` modu; kendi kripto uydurması.
- TLS doğrulamasının kapatılması (`verify=False`, `rejectUnauthorized:false`).
- PII/token'ın şifresiz saklanması veya URL query'de taşınması.
- Zayıf rastgelelik (`Math.random`, `rand()`) token/secret üretiminde.

**İstismar sorusu:** Veri sızarsa okunur mu? Token tahmin edilebilir mi?

## A05 — Injection
Güvenilmeyen girdinin komut/sorgu/şablon olarak yorumlanması. Ayrıntı:
`injection.md` (SQLi, XSS, path traversal, komut, template, LDAP).

**Diff sinyali:**
- String birleştirmeyle kurulan SQL/komut/HTML.
- `eval`, `exec`, `system`, `Function()`, `dangerouslySetInnerHTML`, `v-html`.
- Kullanıcı girdisinin dosya yoluna, redirect URL'ine, şablona geçmesi.

**İstismar sorusu:** Girdiye kontrol karakteri/payload koyarsam sink onu veri
değil komut olarak mı işler?

## A06 — Insecure Design
Uygulama hatası değil, tasarım/iş-mantığı düzeyinde eksik kontrol.

**Diff sinyali:**
- İş akışında eksik adım doğrulaması (ödeme atlanabilir, negatif miktar,
  fiyat/quantity client'tan).
- Rate/abuse limitinin tasarımda hiç olmaması (kupon, OTP, davet).
- Kritik akışta güven sınırı belirsizliği.

**İstismar sorusu:** Adımları atlar/sıralarını değiştirir/negatif değer
verirsem sistem kabul eder mi?

## A07 — Authentication Failures
Kimlik doğrulama ve oturum yönetimi zayıflıkları.

**Diff sinyali:**
- Zayıf parola politikası, brute-force limiti yok, kullanıcı enumeration
  (farklı hata mesajı).
- Oturum sabitleme (login sonrası session yenilenmiyor), uzun/expire olmayan
  token, güvensiz cookie (`HttpOnly`/`Secure`/`SameSite` eksik).
- JWT: imza doğrulanmıyor, `alg:none`, secret zayıf/hardcoded.
- Parola sıfırlama token'ı tahmin edilebilir/süresiz.

**İstismar sorusu:** Token'ı çalar/tahmin eder/yeniden kullanır mıyım?
İmzayı bypass edebilir miyim?

## A08 — Software & Data Integrity Failures
Doğrulanmamış veri/kod bütünlüğü; güvensiz deserializasyon.

**Diff sinyali:**
- Güvenilmeyen veriyi deserialize (`pickle`, `yaml.load`, Java
  `readObject`, `unserialize`).
- İmzasız güncelleme/plugin yükleme, doğrulamasız webhook payload'u.
- CDN/3. taraf script'i SRI (integrity hash) olmadan.

**İstismar sorusu:** Payload'ı değiştirirsem kod çalıştırır veya nesne
enjekte eder miyim?

## A09 — Logging & Alerting Failures
Görünürlük eksikliği ve log'un kendisinin açık olması.

**Diff sinyali:**
- Güvenlik olayı (login fail, yetki reddi, kritik işlem) loglanmıyor.
- **Log'a secret/parola/token/PII yazılıyor** (bu aynı zamanda sızıntı).
- Log injection (kullanıcı girdisi filtresiz log satırına).

**İstismar sorusu:** Saldırım iz bırakır mı? Log'dan hassas veri okunur mu?

## A10 — Mishandling of Exceptional Conditions
Hata/istisna yollarının güvensiz davranması (2025'te yeni giriş).

**Diff sinyali:**
- Hata durumunda "fail-open" (doğrulama hata verince erişime izin).
- Yutulmuş exception (`catch {}` boş) — güvenlik kontrolü sessizce atlanıyor.
- Ayrıntılı hata mesajının kullanıcıya sızması.
- Kısmi işlem/rollback eksikliği (tutarsız güvenlik durumu).

**İstismar sorusu:** Bileşeni hataya zorlarsam sistem güvenli mi kapanır
(fail-closed), yoksa kapıyı mı açar?

---

## Kullanım notu
Bu liste kapsam kontrolüdür, kanıt değil. Bir kategori "sinyal yok" ise bunu
kapsam notunda belirt. Bir kategoride sinyal varsa ilgili derin referansa
(`access-control.md` / `injection.md`) in ve istismarı SKILL.md çıktı
formatında yaz.
