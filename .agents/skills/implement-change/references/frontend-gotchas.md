# Frontend tuzakları — görünür değişiklikte erken yakala

## İçindekiler
- State senkronu ve tek doğruluk kaynağı
- Gereksiz re-render
- XSS ve dangerouslySetInnerHTML
- Dark mode ve tema
- Erişilebilirlik (a11y)
- 60fps ve hareket

Her tuzak: belirti → neden → savunma. Frontend işinde "çalışıyor" kanıtı
before/after screenshot'tır; salt "kodu yazdım" yetmez.

## State senkronu ve tek doğruluk kaynağı
**Belirti:** Aynı veri iki yerde farklı görünüyor; form değeri güncelledikten
sonra eski değere dönüyor; server verisiyle local state çakışıyor.
**Neden:** Aynı gerçeğin iki kopyası (prop'tan türetilmiş state'i ayrıca
saklamak); server-state'i client-state gibi tutmak; derive edilebilir değeri
state'e koymak.
**Savunma:** Tek doğruluk kaynağı — türetilebilen değeri render sırasında hesapla,
state'e koyma. Server verisi için server-state aracı (query cache) kullan.
Kontrollü/kontrolsüz bileşeni karıştırma. Kanıt: değeri değiştir → ekranda
tutarlı kaldığını screenshot ile göster.

## Gereksiz re-render
**Belirti:** Yazarken input takılıyor; liste her tuşta yeniden çiziliyor;
DevTools'ta aşırı render sayacı.
**Neden:** Render içinde yeni referans üretmek (inline obje/fonksiyon prop),
memo'suz pahalı hesap, gereksiz geniş context, key olarak index kullanıp
listeyi yeniden bağlamak.
**Savunma:** Stabil referans (memoize edilmiş callback/değer), pahalı hesabı
memo'la, context'i böl, listede stabil `key` (index değil kimlik) kullan.
Kanıt: etkileşim akıcı — 60fps kontrolü ve gerekirse render profili.

## XSS ve dangerouslySetInnerHTML
**Belirti:** Kullanıcı girdisi HTML olarak yorumlanıyor; `<script>` çalışıyor.
**Neden:** Ham HTML enjeksiyonu (`dangerouslySetInnerHTML`, `innerHTML`,
`v-html`) sanitize edilmeden; URL'e `javascript:` girmesi; kullanıcı verisini
`href`/`src`'ye doğrudan koymak.
**Savunma:** Varsayılan olarak metni escape'li render et (framework zaten yapar).
Ham HTML zorunluysa sanitize et (izin listeli). URL şemasını doğrula. Bu path
güvenlik yüzeyidir — risk `approval`'a kayabilir, `security-review` skill'i
devreye girebilir. Test: kötü niyetli girdiyle (`<img onerror=...>`) render et,
script'in çalışmadığını / escape edildiğini doğrula.

## Dark mode ve tema
**Belirti:** Dark modda metin görünmez; hardcoded `#333` koyu zeminde kayboluyor;
yalnız bir temada test edilmiş.
**Neden:** Renk rolü yerine ham renk yazmak; iki temayı da kontrol etmemek;
`prefers-color-scheme` yok sayılması.
**Savunma:** Renk rolü/token kullan (surface/text/accent), ham hex gömme. Her
rengi iki temada da doğrula. Kontrastı ölç — `designing-interfaces` skill'inin
`scripts/contrast_check.py` aracı WCAG oranını verir. Kanıt: light + dark
screenshot.

## Erişilebilirlik (a11y)
**Belirti:** Klavyeyle kullanılamıyor; ekran okuyucu boş buton okuyor; focus
kayboluyor; dokunma hedefi küçük.
**Neden:** `div` üstüne click (button yerine); ikon-only butonda `aria-label`
yok; focus ring kaldırılmış; başlık sırası bozuk.
**Savunma:** Doğru semantik element (`<button>`, `<a>`), ikon butona `aria-label`,
görünür focus ring koru, dokunma hedefi ≥ 44×44px, başlık sırası h1→h2→h3.
Kanıt: klavyeyle tab dolaşımı çalışıyor.

## 60fps ve hareket
**Belirti:** Animasyon takılıyor (jank); scroll kekliyor; düşük cihazda yavaş.
**Neden:** Layout/paint tetikleyen özellikleri animasyonlamak (`top`, `left`,
`width`, `height`); büyük ağır gölge/blur; her frame'de layout okumak
(layout thrashing).
**Savunma:** Yalnız `transform` ve `opacity` animasyonla (compositor katmanı →
60fps). `prefers-reduced-motion: reduce` guard'ı zorunlu — bu bir a11y
gereğidir, süsleme değil. Kanıt: hareketin akıcılığı ve reduced-motion'da
kapandığı.
