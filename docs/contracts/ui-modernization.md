# UI modernizasyonu — yerel iş sözleşmesi ve plan

18 Eylül 2026 · sınıf: code-change · ön risk: approval.
Yetki: kullanıcının uzman önerilerini uygulama ve React Bits kullanma isteği.
GB10 güncel hedef değildir; NVIDIA ekran kartları ve CPU hedeflenir.

## Hedef ve kapsam

Mevcut kamera/analiz/kayıt API'lerini koruyarak hızlı, okunabilir ve görev odaklı
bir operasyon arayüzü teslim etmek. React Bits bileşenlerini yerel derlenen
React panelinde kullanmak; mobil kayıt ve durum anlamlarını düzeltmek.

İzinli yüzeyler: web/**, frontend/**, scripts/ui/**, e2e/**,
package.json/package-lock.json, ilgili UI testleri ve belgeleri.
Gerekli küçük API düzeltmeleri ayrı testle src/server.py yardımcılarıyla sınırlıdır.
Kapsam dışı: model/GPU motoru, kimlik/rol matrisi, biyometri, DB şeması,
mevcut yangın değişiklikleri, production dağıtımı ve kaynak verileri.

## Kabul kriterleri (EARS)

- K1: Kullanıcı ekran/filtre değiştirdiğinde eski yanıt güncel içeriği ezmemeli.
- K2: Bir panel kaynağı yavaş veya hatalı olduğunda bağımsız alarm/sağlık kartları görünmeli; hata yeniden denenebilmeli.
- K3: Sekme gizlendiğinde dekoratif animasyon ve gereksiz polling durmalı; GET turları üst üste binmemeli.
- K4: Dar ekranda navigasyon ana içeriği aşağı itmemeli; klavye odağı ve azaltılmış hareket desteklenmeli.
- K5: Alarm kabulü tamamlandığında veri yenilenmeli; navigasyon mutation'ı iptal etmemeli veya eski ekranı açmamalı.
- K6: Alarmdan kayıt seçildiğinde doğru kamera ve olay zamanı korunmalı; mobilde gerçek kayıt oynatıcıya ulaşılmalı.
- K7: Görüntü/analiz/kayıt durumları birbirinin yerine kullanılmamalı; kayıt sorgu hatası boş arşiv diye sunulmamalı.
- K8: React Bits kaynakları/sürümleri/lisansı belgelenmeli; uygulama çalışma anında CDN gerektirmemeli.
- K9: Mevcut yangın capability kapısı ve mevcut sayfaların temel işlevleri korunmalı.

## Plan

- [x] Proje kuralları, mevcut UI ve React Bits kaynaklarını incele.
- [x] İzole API fixture'larıyla davranış testlerini ekle ve RED gör.
- [x] Ekran yaşam döngüsü, kontrollü polling ve snapshot kuyruğunu uygula.
- [x] React operasyon paneli, React Bits ve ortak responsive tasarımı uygula.
- [x] Mobil kayıt/durum akışını düzelt.
- [x] Build, UI regresyonları, Python testleri, kontrast ve ekran görüntülerini doğrula.
- [x] Bağımsız inceleme bulgularını kapat; değişiklik ve ölçüm sınırlarını raporla.

## Kanıt

Playwright: gecikmeli yanıt, ters filtre yanıtı, yavaş ikincil kaynak,
klavye/dar ekran, mutation sırasında navigasyon, alarm→kayıt, reduced motion.
Python mevcut testleri ve kernel/kalite kapıları; yerel üretim frontend build'i.
Gerçek kamera/NVIDIA/CPU uçtan uca performansı canlı ortam olmadan iddia edilmez.
Çalışma ağacındaki önceki kullanıcı değişiklikleri başlangıçta saklandı;
bu işin teslimi onları kendiliğinden commit/push kapsamına almaz.

Sonuç ve kriter eşlemesi: `.agents/reports/2026-09-18-ui-ux-inceleme/uygulama-sonucu.md`.

## V2 — kullanıcı görsel yön düzeltmesi

Kullanıcı ilk tasarımı yeterli bulmadı ve açıkça **cesur, fütüristik; yoğun
React Bits arka planları, cam yüzeyler, görünür animasyonlar** yönünü seçti.
Bu seçim yerel skill'in sade/premium estetik tercihinden önce gelir.
Mevcut izinli UI kapsamı ve backend sınırı sürer.

- [x] Slogan/KPI ağırlıklı yerleşimi kamera çalışma alanı + olay kolonuyla değiştir.
- [x] Gerçek React Bits Aurora shader'ını kontrollü render ve statik fallback ile ekle.
- [x] Cam yüzeyleri, güçlü tipografi ve görünür hareket dilini ortak temaya taşı.
- [x] Kamera seçimi, durum dürüstlüğü, reduced-motion ve mevcut UI regresyonlarını doğrula.
- [x] Yeni masaüstü/mobil görselleri gerçekten incele ve paylaş.

V2 kabulü: 1440 px ekranda kamera alanı üstten 340 px'den önce başlar ve ilk
alarm aynı viewport'ta görünür; kamera seçimi doğru snapshot endpoint'ini
kullanır; görüntü yoksa CANLI denmez; 390 px taşma/reduced-motion korunur.

## V3 — Apple sadeliği, React Bits etkileşimleri (2026-09-21)

Kullanıcı `$cdx` planını “ok uygundur” ile onayladı. Hedef: açık nötr
çalışma alanı, mavi eylem vurgusu, ölçülü cam yüzeyler; React Bits efektleri
kartlara, geçişlere ve kontrollere yayılır. Neon/radar dili kaldırılır.
Koyu tema, kamera merkezli yerleşim, mevcut işlevler ve erişilebilirlik korunur.
Yeni bağımlılık, backend/donanım değişikliği, dağıtım bu kapsamda değildir.

- [x] Değişecek kaynakların yerel geri dönüş kopyasını al.
- [x] Tema ve bileşenleri sadeleştir; React Bits hareketlerini bağlamda koru.
- [x] Mevcut regresyonlar, yeni tema kriterleri, kontrast ve ekranları doğrula.
- [x] Bağımsız görsel/teknik inceleme bulgularını gider; önizleme teslim et.

V3 kabulü: kayıtlı tercih yoksa açık tema; kayıtlı koyu tercih korunur.
Kamera/alarmlar önceliklidir; neon radar ve pazarlama sloganı yoktur.
React Bits kontrolleri klavye ile çalışır, reduced-motion tüm hareketi durdurur.
390/768/1440 px ve iki temada taşma/örtüşme olmaz. Normal metin ≥4.5:1.
Geri dönüş: /var/folders/yn/t5zkpqvs1v5f4hbzq6lfhlhh0000gn/T/auras-ui-apple-before-q7sxoop2.

## V4 — yerleşim değişikliği (2026-09-21)

Kullanıcı V3'ü eski sürüme fazla benzer buldu; yalnız palet yerine yapısal
modernizasyon istedi. Aynı UI kapsamı: kompakt masaüstü navigasyonu, kart
olmayan durum özeti, ana kamera+olay akışı ve bitişik alarm/sağlık sütunu.
Görüntü yok durumu yeni nötr yüzey diline taşınır; gerçek görüntü uydurulmaz.
React Bits hover/focus ve kamera seçimi geçişleri belirginleşir.
Kabul: 1440 px'de navigasyon ≤110 px; kamera y<300 px, ilk alarm görünür;
390 px'de menü/odak/taşma; önceki 30 davranış testi korunur.
