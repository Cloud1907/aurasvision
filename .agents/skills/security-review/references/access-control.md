# Erişim kontrolü — IDOR, multi-tenant, yetki bypass

OWASP A01, en sık ve en yüksek etkili sınıf. Kimlik doğrulama (authentication,
"kimsin?") ile yetkilendirme (authorization, "ne yapabilirsin?") ayrıdır; bu
sınıftaki açıkların çoğu ikincisinin eksikliğidir. Bu referans desenleri +
somut istismar örnekleriyle verir.

## İçindekiler
- Temel ilke: her nesne erişiminde yetki
- IDOR (Insecure Direct Object Reference)
- Multi-tenant izolasyon
- Fonksiyon/rol düzeyi yetki bypass
- Kütle atama (mass assignment) ve yetki yükseltme
- Path/route düzeyi bypass
- Denetimde nereye bakılır (checklist)

---

## Temel ilke: her nesne erişiminde yetki
Bir endpoint kimliği doğrulanmış kullanıcıya açık olabilir ama **o kullanıcının
o nesneye erişim hakkı** her istekte, sunucuda, ayrıca kontrol edilmelidir.
Kural: "kaynağı id ile çek" değil, "kaynağı **bu kullanıcıya ait** id ile çek".

Güvensiz:
```
SELECT * FROM invoices WHERE id = :id
```
Güvenli (sahiplik sorguya gömülü):
```
SELECT * FROM invoices WHERE id = :id AND owner_id = :current_user
```

## IDOR (Insecure Direct Object Reference)
Kullanıcı, kendine ait olmayan bir nesneyi doğrudan tanımlayıcıyla ister ve
sistem sahiplik kontrolü yapmadan verir.

**Örnek 1 — sıralı id:**
```
GET /api/orders/1001   → kendi siparişim
GET /api/orders/1002   → başkasının siparişi, yine 200 döner  ← IDOR
```
İstismar: id'yi 1'er artırarak tüm siparişleri sızdır (enumeration).

**Örnek 2 — UUID "güvenlik" yanılgısı:**
Tahmin edilemez UUID kullanmak IDOR'u çözmez; UUID sızarsa (log, referrer,
paylaşılan link, başka API yanıtı) yine erişim olur. Çözüm gizlilik değil,
**sunucu tarafı sahiplik kontrolü**.

**Örnek 3 — dolaylı IDOR:**
```
POST /api/cart/checkout  { "address_id": 55 }
```
`address_id` başka kullanıcının adresine işaret ediyorsa ve kontrol yoksa,
saldırgan başkasının adres kaydını kendi akışına bağlar.

**Aranan sinyal:** İstek gövdesi/query/path'ten gelen bir id ile DB kaydı
çekiliyor; sorguda/kod akışında `current_user`/`owner`/`tenant` filtresi yok.

## Multi-tenant izolasyon
Çok kiracılı sistemde her sorgu `tenant_id` sınırıyla kapatılmalı. Tek eksik
sorgu tüm kiracılar arası veri sızıntısıdır.

**Sık hata desenleri:**
- Tenant filtresini uygulama katmanında elle eklemek (bir yerde unutulur).
  Daha sağlam: ORM/DB düzeyinde zorunlu scope (row-level security, global
  filter, tenant-aware repository).
- `tenant_id`'yi **kullanıcı girdisinden** almak (header/body) — token/oturumdan
  türetilmeli, asla istemciden.
- Ortak cache anahtarı (tenant öneki yok) → bir kiracının verisi diğerine
  servis edilir.
- Arka plan işi/webhook/rapor sorgusunun tenant scope'unu kaybetmesi.

**İstismar:** Kendi tenant'ımın oturumuyla, body'de `tenant_id` alanını başka
tenant değeriyle gönderirsem veri döner mi?

## Fonksiyon/rol düzeyi yetki bypass
Belirli bir işlev yalnız yetkili role açık olmalı; kontrol eksik veya yalnız
UI'da.

**Örnek — gizli admin endpoint:**
```
POST /api/users/42/promote     ← yalnız admin butonundan çağrılıyor "sanılıyor"
```
UI butonu gizli ama endpoint korumasız; normal kullanıcı doğrudan isteği atar.

**Örnek — HTTP metodu farkı:** `GET` korunmuş ama aynı kaynağın `PUT`/`DELETE`
metodu koruma dışı bırakılmış.

**Örnek — client-side rol:** Yetki kararı frontend'de (`if (user.isAdmin)`);
sunucu güvenir. Kullanıcı isteği doğrudan atınca bypass.

**Aranan sinyal:** Yeni endpoint'te `@authorize`/middleware/guard yok; yetki
kontrolü sadece view/template'te; yeni HTTP metodu eski route'a eklenmiş.

## Kütle atama (mass assignment) ve yetki yükseltme
İstek gövdesindeki alanlar doğrudan modele bağlanıyor; kullanıcı beklenmeyen
alanı (rol, bakiye, onay) set ediyor.

**Örnek:**
```
PATCH /api/profile   { "name": "Ali", "role": "admin" }
```
Kod `user.update(request.body)` yapıyorsa `role` da güncellenir → yetki
yükseltme. Çözüm: allowlist (yalnız izinli alanları bağla), DTO/serializer
ile alan filtreleme.

**Aranan sinyal:** `update(body)`, `Object.assign(model, input)`,
`Model(**data)` gibi kör bağlama; hassas alan (role, is_admin, tenant_id,
price, balance) girdiden set edilebiliyor.

## Path/route düzeyi bypass
- **Path traversal ile yetki atlama:** `/admin/../user` veya çift kodlama
  (`%2e%2e`) ile koruma path'i atlatma.
- **Trailing slash / büyük-küçük harf:** `/Admin`, `/admin/` gibi varyantlar
  eşleşme kuralını atlar.
- **Doğrulanmamış redirect (open redirect):** `?next=` parametresi harici
  URL'e yönlendirirse phishing/oturum çalma yüzeyi.

## Denetimde nereye bakılır (checklist)
- [ ] Her yeni/değişen endpoint'te sunucu tarafı yetki kontrolü var mı?
- [ ] Nesne çeken her sorguda sahiplik/tenant filtresi sorguya gömülü mü?
- [ ] `tenant_id`/`role`/`owner` istemci girdisinden mi geliyor? (kırmızı bayrak)
- [ ] Model güncellemesinde alan allowlist'i var mı (mass assignment)?
- [ ] Aynı kaynağın tüm HTTP metotları korunuyor mu?
- [ ] Yetki kararı yalnız client'ta mı? (bypass edilir)
- [ ] Redirect/`next`/`returnUrl` parametresi allowlist'e tabi mi?
- [ ] Yetki kontrolü diff dışı bir fonksiyondaysa, o fonksiyonu **oku** ve
      kontrolün gerçekten var olduğunu doğrula.
