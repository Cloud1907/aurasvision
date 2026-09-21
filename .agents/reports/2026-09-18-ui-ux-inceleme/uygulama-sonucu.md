# UI modernizasyonu — uygulama ve yerel doğrulama

18 Eylül 2026. İlgili sözleşme: `docs/contracts/ui-modernization.md`.
Kullanıcı uzman önerilerini uygulamayı ve React Bits kullanımını onayladı.

## Teslim edilen davranış

React operasyon paneli; ortak açık/koyu tema, mobil açılır menü, klavye
navigasyonu ve olay inceleme penceresi eklendi. Alarm, sağlık, olay, arşiv
kaynakları bağımsız yüklenir. Başarısız yenileme eski sayıyı güncel gibi
sunmaz. Sağlık listesi sorunlu kameraları önce gösterir.

React Bits kaynaklı/uyarlanmış sekiz bileşen: SpotlightCard, StarBorder,
CountUp, AnimatedList, GlassIcons, FadeContent, DotGrid ve Noise.
DotGrid CSS ile sabittir; Noise 128×128 tek çizimdir. Animasyonlar azaltılmış
hareket tercihini ve sekme görünürlüğünü gözetir. Kaynak SHA ve lisans
`frontend/react-bits/README.md` içinde; üretim paketine lisans kopyaları eklenir.

Ekran/filtre değişiminde önceki GET'ler iptal edilir ve yanıt güncelliği
kontrol edilir. Mutation'lar ekran değişimiyle iptal edilmez. Snapshot
kuyruğu en fazla iki eşzamanlı istek, 6.5 saniye timeout ve 30 saniye hata
beklemesi kullanır. Görünür alana giren kamera bekleyen yenileme turunu
beklemeden kuyruğa alınır; kuyruktan çıkışta görünürlük yeniden denetlenir.
`/counts` yenilemesi yalnız canlı ekranda, 8 saniye aralığındadır.

Mobilde analiz FPS'sinin REC olarak gösterilmesi kaldırıldı; görüntünün
son kare zamanı ile analiz sağlığı ayrıldı. Açık alarm listesi kendiliğinden
yenilenir, filtre ve odak korunur. Kabul, çözülmüş olay olarak adlandırılmaz.
Alarmdan kayda geçiş kamera ve zamanı taşır. O anda kayıt yoksa açık boşluk
mesajı çıkar; komşu video ayrıca seçilir.

## Yerel kanıt

| Kontrol | Sonuç |
|---|---|
| `npm run build:ui` | Geçti |
| `npm run test:ui` | 21/21 Chromium testi geçti |
| `.venv/bin/python -m pytest -q` | 905 geçti, 9 atlandı, 143 alt test geçti |
| `.venv/bin/python bin/validate.py` | Tüm kontroller geçti |
| `.venv/bin/python bin/kalite.py --check` | Geçti; borç tabanı yükseltilmedi |
| Yerel skill `check_test_first.py` | PASS; testler kaynak başına ad eşleşmesi yerine davranışları kapsıyor |
| `git diff --check` | Geçti |
| Kontrast kontrolü | Kontrol edilen 9 metin/zemin çifti geçti; en düşük 4.80:1 |
| Tarayıcı ekran dolaşımı | 10 mevcut sayfada pageerror görülmedi |
| 320/390/768/1024/1440 px | Panelde yatay taşma yok; içerik başlangıcı 80–90 px |

JS çıktı: 382,576 bayt (yerelde hesaplanan gzip 122,339 bayt).
CSS çıktı: 22,250 bayt (gzip 5,687 bayt). Sunucunun gzip aktarımı ayrıca
ölçülmedi; bunlar sıkıştırılabilir dosya boyutlarıdır.

İlk beş davranış testi eski arayüzde RED görüldükten sonra uygulandı.
İncelemede çıkan eski KPI/boşlukta yanlış kayıt bulguları da iki ayrı RED
ile doğrulandı ve düzeltildi. Diğer testler regresyon doğrulamasıdır.
Mobil zaman testinde sanal saat sayfa yüklenmeden kurulacak şekilde düzeltildi;
önceki test kurulumu mevcut native zamanlayıcıları yakalamıyordu.
İlk genel doğrulamada sistem Python'u ortam bağımlılıklarını bulamadı;
projenin `.venv` yorumlayıcısıyla tekrar çalıştırılan doğrulama geçti.
Statik yangın UI testinin endpoint kontrolü, `api` yerine ekran kapsamlı
`ctx.get` çağrısını tanıyacak şekilde güncellendi; davranış kriteri korunuyor.

## Kabul kriteri → test eşlemesi

| Kriter | Kanıt |
|---|---|
| K1 | Geç ekran yanıtı, ters sıralı filtre yanıtı |
| K2 | Yavaş arşiv, alarm KPI 503, mobil alarm polling/sağlık hatası, kırık kanıt görseli |
| K3 | Gizli sekme/seri polling, iki snapshot sınırı/iptal, yeni görünür kamera |
| K4 | 390 px menü/Enter, reduced motion, modal Escape/odak, mobil filtre odağı |
| K5 | Kabul POST'u sürerken kayıt ekranına geçiş |
| K6 | Mobil kamera+zaman bağlantısı, olay anında kayıt boşluğu |
| K7 | REC etiketinin yokluğu, kayıt API hatasının boş arşiv sayılmaması |
| K8 | Yerel üretim build'i, sabit kaynak SHA, paket lisansları |
| K9 | Yangın capability kapısı, sunucu ret mesajı, Python regresyonları |

## Bağımsız inceleme

Frontend performans, UX akışları ve görsel arayüz uzmanları salt okunur
inceleme yaptı. Eski KPI, mobil canlı alarm yenilemesi, kayıt boşluğu,
klavye odağı, kanıt görseli hatası, API ret mesajı, viewport snapshot kuyruğu
ve mobil sistem durumu bulguları düzeltildi. Bunlar kaynak/görsel incelemesidir;
otomasyon sonuçlarının bağımsız yeniden çalıştırılması olarak sunulmaz.

## Görsel kayıt

Görüntüler aynı izole API fixture'ıyla üretilmiştir; gerçek saha verisi değildir.

- [Önce](once-desktop.png)
- [Yeni masaüstü](uygulama-desktop.png)
- [Koyu tema](uygulama-dark.png)
- [Dar ekran](uygulama-mobile.png)
- [Olay inceleme](olay-inceleme.png)
- [Mobil alarm merkezi](mobil-alarm.png)
- [Tarayıcı kontrol kaydı](tarayici-kontrol.json)

## Ölçüm ve kapsam sınırı

GB10 güncel hedef değildir; NVIDIA/CPU hedefi esas alınmıştır. Backend cihaz
seçimi ve gerçek kamera throughput'u bu UI değişikliğinde değiştirilmedi/ölçülmedi.
API fixture testleri gerçek ağ, RTSP, GPU veya üretim performansını kanıtlamaz.
Çalışan kameralar/modeller başlatılmadı. CI, PR, commit veya dağıtım yapılmadı;
bu rapor yerel doğrulama kaydıdır, CI `evidence.json` yerine geçmez.

Başlangıçta bulunan yangın geliştirmeleri korunmuştur. Bu turun değişikliği
frontend/web, UI build/test altyapısı ve ilgili belgelerle sınırlıdır; server,
DB, model veya rol matrisi bu turda değiştirilmedi.


## V2 — cesur, fütüristik çalışma alanı

Kullanıcının seçtiği yön uygulandı: koyu indigo zemin, cam paneller, mor aksiyonlar, Manrope/IBM Plex Mono tipografi, büyük kamera çalışma alanı ve bitişik alarm kuyruğu. React Bits Aurora özgün shader’ı native WebGL2 ile eklendi; toplam dokuz uyarlanmış React Bits bileşeni kullanılıyor. Kamera şeridi klavyeyle çalışır; kamera yokluğu canlı görüntü diye sunulmaz.

- Yerel üretim build’i: JS 391286, CSS 39446 bayt.
- Playwright: **28 geçti (9.9 saniye)**. İlk üç V2 kabul testi değişiklik öncesinde kırmızı görüldü.
- Yangın UI regresyonları: **10 geçti**. Kernel ve kalite kapıları geçti; borç tabanı değiştirilmedi.
- Kontrast: sekiz temel koyu/açık tema metin çifti PASS; en düşük 5.55:1. Hareketli cam yüzeylerin tüm kareleri için ölçüm iddiası değildir.
- 1440 px ekran: kamera alanı y=323; ilk alarm viewport içinde. 390 px ekran: belge genişliği 390, taşma yok. Tarayıcı pageerror yok.
- Bağımsız teknik incelemede bulunan WebGL context-loss fallback düzeltildi; gerçek WEBGL_lose_context ile regresyon testi geçti. Görünüm dışındaki shader zamanlayıcısı durur.
- Görsel inceleme: ürün bileşenlerinde taşma/örtüşme bulunmadı. Önizleme etiketinin içeriği örtmesi düzeltildi, belge akışına alındı.
- Ağ testleri reduced-motion ile GPU yükünden ayrıldı; eşzamanlı iki istek testi zaman yarışına bağlı gecikme yerine kontrollü yanıt bariyeri kullanıyor. Animasyon/WebGL testleri ayrı ve hareket açık.

Görseller: `v2-desktop.png`, `v2-mobile.png`. İnteraktif önizleme: `node scripts/ui/preview.mjs --demo` → http://127.0.0.1:8768. Temsili fixture verileri ve salt okunur API; üretim paketine demo verisi eklenmez.

30 fps shader üst sınırı düşük CPU maliyetinin kanıtı değildir. Gerçek NVIDIA/CPU inference, kamera decode ve saha gecikmesi bu yerel görsel çalışmada ölçülmedi. Bu turda tüm Python paketi yeniden çalıştırılmadı; önceki V1 tam paket sonucu yukarıda, V2 için odaklı UI regresyonu çalıştırıldı. Üretime dağıtılmadı.
