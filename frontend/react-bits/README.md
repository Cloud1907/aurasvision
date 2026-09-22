# React Bits kökeni ve uyarlamalar

Kaynak: https://github.com/DavidHDev/react-bits — sabit commit
`7cc1be9d06f76dd08d8200ed1a561bd812290cd2` (2026-09-18 tarihinde alındı).
Lisans: [MIT + Commons Clause](LICENSE.md). Bu dizin ürün arayüzü entegrasyonudur;
ücretli bağımsız bileşen kütüphanesi olarak yeniden dağıtılmamalıdır.

| Bileşen | Ürün uyarlaması |
|---|---|
| SpotlightCard | Açık/koyu temaya uyum, hareket azaltma ve görünürlük kontrolü |
| StarBorder | Sonsuz döngü yerine yalnız hover/focus sırasında sınırlı hareket |
| CountUp | Türkçe sayı biçimi; kritik alarmlarda animasyon yok |
| SplitFlapText | KPI değişimlerinde tek seferlik mekanik geçiş; karakter bazlı ve reduced-motion uyumlu |
| MaskedHeading | Operasyon başlığında yalnız ilk girişte kısa maske açılışı; sonsuz döngü yok |
| AnimatedList | Tab yakalama kaldırıldı; görünürlük gecikmesi yok; yerel butonlar |
| GlassIcons | Gerçek onClick, kalıcı etiket, çakışmayan CSS sınıfları |
| FadeContent | GSAP kaldırıldı; CSS ile kısa giriş, reduced-motion desteği |
| DotGrid | Canvas/GSAP/RAF yerine statik CSS noktalı arka plan |
| Noise | Tek sefer üretilen 128×128 doku; sürekli canvas döngüsü yok |

DotGrid ve FadeContent orijinal etkileşim motorunun birebir kopyası değildir.
Uyarlamaların amacı NVIDIA veya CPU çalışan kurulumlarda tarayıcı yükünü sınırlamaktır;
donanım performansı bu entegrasyonla ölçülmüş sayılmaz. V2 ile Aurora shader’ı native WebGL2 renderer üzerinden eklendi; GSAP, OGL veya Three.js bağımlılığı eklenmedi. WebGL2 yoksa statik CSS arka plan kullanılır. Uygulamada kullanılmayan kaynak CSS'leri
pakete dahil edilmez. Lisans üretim çıktısına da kopyalanır.

## V2 Aurora

Aynı sabit commit’teki `src/content/Backgrounds/Aurora/Aurora.jsx` shader’ı
`aurora/shaders.js` içinde korunur. OGL yerine küçük native WebGL2 renderer
kullanılır. Render en fazla 30fps, 1200×550 piksel ile sınırlıdır; sekme
gizliyken veya arka plan viewport dışında iken çizim yapılmaz. Reduced-motion
tercihinde WebGL başlatılmaz. Kamera bekleme taraması dekoratiftir; canlı
görüntü/donanım etkinliği kanıtı değildir.

## V3 sade arayüz

Aurora başlık çevresindeki 240 px yüksekliğindeki alanla sınırlı; renk doygunluğu
ve opaklığı azaltıldı. DotGrid kamera boş durumunda düşük kontrastlı statik doku.
Dekoratif radar ve tarama çizgisi kaldırıldı. GlassIcons hareketsizken düz katmanlı,
hover/focus sırasında küçük derinlik hareketi yapar. StarBorder yalnız hover/focus,
CountUp kısa başlangıç hareketi, AnimatedList/FadeContent kısa geçiş olarak sürer.
