# security-review — eval vakaları

Skill'in gerçekten işe yaradığını ölçen temsili görevler. Her vaka: girdi +
beklenen davranış + fail sinyali. "Kanıt > beyan" — skill değiştiğinde bu
vakalar elle gözden geçirilmeli.

## Vaka 1 — IDOR yakalama (erişim kontrolü)
**Girdi:** Diff yeni endpoint ekliyor:
`GET /api/invoices/:id` → `SELECT * FROM invoices WHERE id = :id` (sahiplik
filtresi yok, kimlik doğrulaması var).
**Beklenen:** HIGH bulgu. Konum dosya:satır ile. İstismar yazılır: "kendi
oturumumla id'yi artırarak başka kullanıcının faturasını okurum". Düzeltme:
sorguya `AND owner_id = :current_user`. Hüküm VETO. (`access-control.md`)
**Fail sinyali:** "Auth var, güvenli" deyip geçmek; authentication ile
authorization'ı karıştırmak.

## Vaka 2 — SQL injection (injection)
**Girdi:** Diff'te `query = "SELECT * FROM users WHERE email='" + email + "'"`.
**Beklenen:** CRITICAL bulgu. İstismar: `' OR '1'='1` ile tüm satırlar / auth
bypass. Düzeltme: parametreli sorgu. Hüküm VETO. (`injection.md`)
**Fail sinyali:** "kullanıcı e-posta girer, sorun olmaz" varsayımı; string
birleştirmeyi görmezden gelmek.

## Vaka 3 — hardcoded secret (deterministik kapı)
**Girdi:** Diff bir config dosyasına
`STRIPE_KEY = "sk_live_<ÖRNEK-GERÇEK-DEĞİL-24-KARAKTER>"` ekliyor (gerçek
formatta bir canlı Stripe anahtarı — GitHub push protection tetiklemesin
diye burada kırık yazıldı, eval sırasında agent kendi scratch dosyasına
gerçek formatta yazar).
**Beklenen:** `python3 scripts/scan_secrets.py <dosya>` çalıştırılır, exit 1
döner, bulgu dosya:satır ile raporlanır. CRITICAL. Düzeltme: env/secret
manager'a taşı + anahtarı rotate et. Hüküm VETO.
**Fail sinyali:** Scripti çalıştırmadan gözle "secret yok" demek; canlı
anahtarı sadece "kaldır" deyip rotate'i atlamak.

## Vaka 4 — negatif tetikleme (yanlış-pozitif direnci)
**Girdi:** Diff yalnız `README.md` içinde yazım düzeltmesi ve bir testte
assert mesajı değişikliği yapıyor — güvenlik yüzeyi yok.
**Beklenen:** Skill TETİKLENMEZ veya tetiklenirse "güvenlik yüzeyi yok,
kapsam dışı" der; **hiçbir uydurma bulgu üretmez**. Örnek `.env.example`
içindeki `API_KEY=your_key_here` gibi placeholder, scan_secrets tarafından
elenir (bulgu değil).
**Fail sinyali:** Bulgu üretme baskısıyla teorik/erişilemez senaryoyu HIGH
diye şişirmek; placeholder'ı gerçek secret sanmak.

## Vaka 5 — CORS misconfig (fail-open sınır)
**Girdi:** Diff `Access-Control-Allow-Origin: *` ile birlikte
`Access-Control-Allow-Credentials: true` set ediyor.
**Beklenen:** HIGH/MEDIUM bulgu (etkiye göre). İstismar: herhangi bir origin
kullanıcının credential'ıyla API'ye erişip yanıtı okur. Düzeltme: origin
allowlist; wildcard + credentials birlikte yasak. (`owasp-2025.md` A02)
**Fail sinyali:** İki başlığın birlikte olmasının tehlikesini gözden kaçırıp
ayrı ayrı "normal" saymak.

## Ölçüt
- Yakalama: Vaka 1-3, 5'te doğru şiddet + istismar + konum.
- Yanlış-pozitif: Vaka 4'te sıfır uydurma bulgu (gürültü eşiği).
- Deterministik kapı: Vaka 3'te scan_secrets exit 1 kanıtı zorunlu.
