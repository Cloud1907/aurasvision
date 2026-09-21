# AurasVision operasyon arayüzü

React operasyon paneli mevcut FastAPI/vanilla sayfaların içine bağlanır.
`main.jsx` yalnız `window.AurasUI.mountPanel` köprüsünü yayınlar. API, kamera
oynatıcı ve kayıt işlevleri mevcut uygulamadan alınır. React kökü ekran
çıkışında kaldırılır; sayfaya ait GET'ler `web/ui-runtime.js` ile iptal edilir.

## Derleme ve kontrol

Proje kökünde:

```sh
npm ci
npm run build:ui
npm run test:ui
```

`web/dist/` üretim çıktısı ve lisansları içerir. Mevcut Python statik sunucusu
`/static/dist/` yolundan sunar; tarayıcıda CDN veya Node sunucusu gerekmez.
Kaynak değişince bu dizin de yeniden derlenmelidir. Node 24.11.1 ile doğrulandı.

`npm run preview:ui` yalnız 127.0.0.1:8767 üzerinde statik dosyalar sunar.
API'lere 503 döner; kamera/DB/model başlatmaz. Playwright testleri kendi
`e2e/fixtures/ui-api.ts` yanıtlarını kullanır. Gerçek uygulama mevcut FastAPI
başlatma akışıyla açılır; önizleme örnek verileri üretim paketine girmez.

`node scripts/ui/preview.mjs --demo` 127.0.0.1:8768 üzerinde açıkça etiketlenmiş, salt okunur temsili veri önizlemesini açar. Canlı API veya kamera bağlantısı kurmaz.

## Yapı

- `components/Panel*`: bağımsız yüklenen operasyon bölümleri.
- `hooks/useResource.js`: GET iptali, aynı veri için nesne koruma, görünürlük kontrollü yenileme.
- `react-bits/`: kaynak commit'i ve uyarlamaları README'de, lisansı LICENSE.md'de.
- `theme.css`: mevcut sayfalar için ortak renk, tipografi ve mobil menü.
- `command-center.css`: V2 cam yüzeyler, kamera sahnesi, duyarlı yerleşim ve hareket tercihleri.
- `panel.css`: React panelinin sınırlı kapsamlı stilleri.
- `web/ui-runtime.js`: ekran yaşam döngüsü, seri polling, iki işçili snapshot kuyruğu.

Mobil ve masaüstü kayıt bağlantıları `/?view=rec&camera=...&at=...` biçimindedir.
`at` ISO zamanıdır; uygulama kullanıcının yerel gününü ve saniyesini hesaplar.
Tam olay anında kayıt yoksa önceki video kendiliğinden oynatılmaz.

## Kaynaklar ve sınırlar

React Bits: https://reactbits.dev / https://github.com/DavidHDev/react-bits
Dokuz bileşen ürün gereksinimine göre uyarlanmıştır. DotGrid statik CSS,
Noise tek çizimdir. Aurora özgün React Bits shader’ını native WebGL2 ile, en fazla 30 fps ve sınırlı çözünürlükte çalıştırır; OGL/GSAP/Three.js bağımlılığı eklenmemiştir. WebGL yoksa statik arka plan gösterilir. Azaltılmış hareket, görünürlük ve ekran çıkışı kaynak temizliği desteklenir.
React Bits MIT + Commons Clause; fontlar OFL lisanslıdır. Derleme çıktısı
React/Motion üçüncü taraf bildirimlerini ve font/React Bits lisanslarını taşır.

GB10 mevcut donanım hedefi değildir. NVIDIA ekran kartları veya CPU üzerinde
çalışan backend bu arayüzü kullanabilir; bu değişiklik inference motorunun
cihaz seçimini değiştirmez ve gerçek kamera/donanım throughput ölçümü içermez.
