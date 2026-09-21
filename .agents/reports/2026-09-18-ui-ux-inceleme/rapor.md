# AurasVision — frontend, UI ve UX değerlendirmesi

Tarih: 18 Eylül 2026. İncelenen taban: `8b7559e` ve mevcut çalışma ağacındaki değişiklikler.

## Kapsam ve yöntem

Kullanıcı düzeltmesi: **GB10 artık devrede değil. Hedef mevcut NVIDIA ekran kartları veya CPU.** Tarihsel GB10 kapasitesi güncel performans kanıtı olarak kullanılmadı. GPU seçimi/uygulama değişikliği bu incelemenin kapsamında değil.

Frontend performansı ve UX akışları iki bağımsız uzman ajan tarafından incelendi. Workbench `visual-review` rotasındaki Claude UI danışmanı 180 saniyelik zaman aşımıyla sonuç üretmedi; yerine üçüncü bağımsız UI değerlendirme ajanı çağrıldı. Üçüncü ajan kaynak kodunu ve paylaşılan ölçümleri inceledi; ekran görüntüleri alt ajan bağlamına aktarılmadığından doğrudan görsel değerlendirmeyi ana ajan yaptı. Claude görüşü varmış gibi kullanılmadı.

Canlı panel adresi sağlanmadığından mevcut `web/` dosyaları yalnız loopback statik sunucuda açıldı. Gerçek kamera, DB, model veya backend başlatılmadı. API sonuçları yalnız tarayıcı belleğinde 8 temsili kamera/2 temsili alarm olarak sağlandı; yazma işlemleri engellendi. Ekran görüntüleri tarayıcı aracılığıyla oturumda incelendi. Bunlar mevcut arayüzün temsili veriyle render'ıdır, yeni tasarım değildir.

Gerçek cihazlarda API gecikmesi, video FPS, CPU/GPU kullanımı veya Core Web Vitals ölçülmedi. Aşağıdaki tarayıcı deneyleri üretim performans ölçümü değildir. Uygulama dosyaları değiştirilmedi; çıktı bu değerlendirme raporudur.

## Yönetici özeti

Arayüzdeki atıllık üç alanda ele alınmalı: istek ve ekran yaşam döngüsü, operatörün görevi tamamlaması, görsel öncelik ve okunabilirlik. Mevcut özellikler korunarak bu alanların iyileştirilmesi önerilir. Yeni framework veya tüm uygulamayı yeniden yazma kararını destekleyen bir ölçüm bulunmuyor.

## Frontend performansı

### F1 — P1: Geç yanıt yeni ekranın içeriğini değiştirebiliyor

**Doğrulanmış:** Ekran geçişi ortak içerik alanını kullanıyor; önceki ekranın devam eden istekleri iptal edilmiyor veya sonuçları ekran kimliğine göre elenmiyor. Olaylar sayfasının geç gelen yanıtı başka ekrana yazabiliyor. Kaynak: `web/index.html:527`, `web/index.html:550`, `web/index.html:1137`, `web/index.html:1176`.

Tarayıcı deneyi: temsili `/events` ve `/alerts` yanıtlarına 700 ms gecikme eklendi; Olaylar seçilip hemen Panel'e geçildi. Bekleme sonunda `active="panel"`, başlık `Panel`, içerikte `Olay akışı=true`, `Kamera durumu=false` görüldü. Bu, kaynak incelemesine ek davranış kanıtıdır; 700 ms gerçek sunucu ölçümü değildir.

**Öneri:** Ekran başına iptal ve istek sürümü kontrolü; yalnız güncel ekran/güncel filtrenin yanıtı çizilsin. İptal, boş ve hata durumları ayrı gösterilsin. Kabul: gecikmeli ve ters sırada yanıtlanan sekme/filtre geçişleri yanlış içeriğe yol açmamalı. Kaynak: `web/index.html:437`, `web/index.html:550`.

### F2 — P1: Kamera önizlemeleri ortak API kaynaklarını tüketebiliyor

**Kod davranışı doğrulanmış, yavaşlığa katkısı ölçülmedi:** go2rtc bulunmadığında masaüstü canlı duvarı bütün görüntü URL'lerini beş saniyede bir değiştiriyor. Snapshot cache miss'inde sunucu görüntü kaynağını açıp JPEG üretiyor; eşzamanlı aynı kamera isteklerini birleştiren mekanizma ve başarısız kameraya backoff görünmüyor. Çok kamera/çok istemci/erişilemeyen kaynak kombinasyonu kritik aday. Kaynak: `web/index.html:911`, `src/server.py:1196`, `src/server.py:1215`.

**Öneri:** Görünen kameraya öncelik, sınırlı eşzamanlılık, aynı kamerada tek devam eden işlem ve hata backoff. Mevcut capture hattından son kare paylaşımı değerlendirilmelidir. Gerçek ölçüm: 1/4/16 kamera, erişilemeyen kaynak ve birden çok panel altında ilk kare süresi, API p95, CPU ve eşzamanlı capture sayısı. Kaynak: `src/server.py:1196`, `src/server.py:1215`.

### F3 — P2: Mobilde bir bozuk kamera sonraki kameraları bekletiyor

**Doğrulanmış kod davranışı:** Snapshotlar sırayla bekleniyor. Cevap vermeyen ilk kamera sonraki isteği sekiz saniye geciktirebilir; zaman aşımı bekleyen Promise'i tamamlar fakat HTTP isteğini iptal etmez. Kaynak: `web/mobil.html:268`.

**Öneri:** Görünen kartlar için küçük bir eşzamanlı istek havuzu; gerçek iptal edilen timeout; kamera başına bağımsız hata durumu. Kabul: erişilemeyen kamera, erişilebilir diğer görünür kameraların ilk görüntüsünü bloke etmemeli. Kaynak: `web/mobil.html:272`.

### F4 — P2: Ekranın ihtiyacından bağımsız sorgular sürüyor

**Doğrulanmış kod davranışı:** Masaüstünde sayaç sorgusu iki saniyede, durum ve alarm sorguları on saniyede sürüyor. Görünürlük ve önceki turun tamamlanması kontrol edilmiyor. Sayaç tarafında geçmiş olayları gruplayan sorgu var; veri hacmi arttıkça etkisi ayrıca ölçülmeli. Kaynak: `web/index.html:492`, `web/index.html:504`, `src/store.py:311`.

**Öneri:** Görünürlük ve aktif ekran ihtiyacına göre yenileme; tamamlanan turdan sonra zamanlama; değişmeyen veride DOM güncellememek; uygun ortak özet/cache. Güvenlik alarmının tazeliği ile ikincil sayaçların yenileme sıklığı ayrı kararlaştırılmalı. Kaynak: `web/index.html:498`, `web/index.html:538`.

### F5 — P2: Panel en yavaş bağımlılığı bekliyor

**Doğrulanmış kod davranışı:** Durum, alarm, olay özeti ve arşiv istatistiği tek `Promise.all` tamamlanınca çiziliyor; kamera sağlığı sonrasında isteniyor. Kritik uyarı, ilgisiz arşiv sorgusunun arkasında kalabiliyor. Kaynak: `web/index.html:801`, `web/index.html:825`.

**Öneri:** Alarm ve kamera sağlığı önce; arşiv ve genel özet bağımsız yükleme/hata durumlarıyla sonra. Her kart son başarılı güncellemesini gösterebilmeli. Kaynak: `web/index.html:790`.

## Kullanıcı akışları

| Öncelik | Sorun | Kanıt ve öneri |
|---|---|---|
| P1 | Mobil “Kayda git” olay videosuna ulaştırmıyor | `web/mobil.html:329`, `web/mobil.html:338`: yalnız kamera filtresi ve olay listesi; olay zamanı taşınmıyor. Tarayıcıda hedef ekran “Kayıtlar ve Olaylar”, video elemanı=0, tarih girişi=0. Alarm → olay anı → oynatma → kesit akışı gerekli. |
| P1 | “REC” gerçek kayıt durumunu temsil etmiyor | `web/mobil.html:243`: kayıt etiketi analiz FPS'inden türetiliyor. Görüntü bağlantısı, analiz ve kayıt ayrı durumlar olmalı. |
| P1 | Gördüm ile çözdüm birbirine karışıyor | `web/mobil.html:295`, `web/mobil.html:305`, `web/mobil.html:328`: ack sonucu “Çözülen” sayılıyor. Operatör kabulü “Gördüm/Kabul edildi”; çözüm farklı bir süreç ise ayrı eylem olmalı. |
| P1 | Rozet yenilenirken açık alarm listesi eski kalabiliyor | `web/index.html:538`, `web/mobil.html:400`: periyodik iş listeden çok rozeti yeniliyor. Açık liste kontrollü güncellenmeli; yeni/güncel olmayan veri açıkça belirtilmeli. |
| P1 | Arşiv hatası “kayıt yok” diye görünebiliyor | `web/index.html:1607`: hata boş listeye çevriliyor. Boş sonuç, bağlantı sorunu ve yetki sorunu ayrılmalı; yeniden deneme yolu sunulmalı. |
| P2 | Kamera ekleme teknik seçimlerle başlıyor | `web/index.html:1875`: üç keşif yöntemi ve teknik alanlar birlikte. Ağda bul → önizlemeyi doğrula → adlandır → görev seç → kaydet; ayrıntılar gelişmiş seçeneklere taşınmalı. |

UX değerlendirmesi: mobil olay videosuna ulaşma görevi mevcut yüzeyde tamamlanamıyor. Bu, yalnız görünüm düzenlemesiyle kapanacak bir bulgu değil. Kaynak: `web/mobil.html:335`, `web/mobil.html:338`.

## Görsel ve responsive kanıt

**Doğrulanmış render gözlemi:** 1440×1000 masaüstü Panel'de iki sıra toplam on özet kartı benzer ağırlık taşıyor; kritik uyarılar ve kamera listesi bu kartların altında. İki uyarı bulunan sütun, sekiz kameranın yüksekliğine kadar uzayarak büyük boş alan bırakıyor. Bunun operatör önceliğini zayıflattığı değerlendirmesi görsel yorumdur. Kaynak: `web/index.html:506`, `web/index.html:790`; oturumdaki temsili Panel ekran görüntüsü.

**Doğrulanmış ölçüm:** 390×844 viewport'ta mevcut masaüstü arayüzünün navigasyon alanı 546 px; ana içerik başlangıcı 620 px, menüde 11 öğe. Ekranın önemli kısmı görev içeriğine ulaşmadan harcanıyor. Ölçüm, emülasyon sonrası temsili veriler yeniden yüklendikten sonra `getBoundingClientRect()` ile alındı. Ayrı mobil arayüzün alt navigasyonu bundan farklıdır; bu bulgu masaüstü arayüzünün dar ekran davranışıdır. Kaynak: `web/index.html:284`, `web/index.html:336`.

**Doğrulanmış kontrast hesabı:** Projenin `contrast_check.py` aracı aşağıdaki sonuçları verdi; bu bütün uygulamaya erişilebilirlik sertifikası değildir. Küçük etiketlerde kullanılan renkler açısından somut düzeltme ihtiyacıdır. Kaynak: `web/index.html:15`, `web/index.html:26`, `web/index.html:86`, `web/mobil.html:24`.

| Renk çifti | Oran | Proje normal metin eşiği 4,5 |
|---|---:|---|
| `#878e96` / `#ffffff` | 3,31:1 | Başarısız |
| `#6b7178` / `#151719` | 3,64:1 | Başarısız |
| `#7e848b` / `#17191c` | 4,66:1 | Geçti |
| `#4e8cc9` / `#151719` | 5,07:1 | Geçti |

Komut: `python3 .agents/skills/designing-interfaces/scripts/contrast_check.py '#878e96 on #ffffff' '#6b7178 on #151719' '#7e848b on #17191c' '#4e8cc9 on #151719'` → exit 1, iki başarısız çift.

## Önerilen tasarım yönü

**UI uzmanının ek kod bulguları:** Ana navigasyondaki öğeler `href` ve `tabindex` taşımayan `<a onclick>` olarak kuruluyor; gerçek bağlantı/düğme semantiği ve görünür odak gerekli. Canlı kamera aksiyonları `opacity:0` ile saklanıp yalnız hover ile gösteriliyor; klavye odağı için `focus-within`, dokunmatik için sürekli görünür eylem gerekir. Kaynak: `web/index.html:535`, `web/index.html:100`, `web/index.html:904`. Bunlar kod temelli erişilebilirlik bulgularıdır; tam ekran okuyucu/klavye denetimi yapılmış sayılmaz.

**[yorum] Operatör çalışma alanı:** İlk ekranda müdahale isteyen alarmlar ve sorunlu kameralar; seçili olayın görüntüsü ve eylemleri yan panelde. Arşiv hacmi ve etkin olmayan özellik sayıları ikincil özetlere taşınabilir. Dayanak: `web/index.html:790`, `web/index.html:1166`.

**[yorum] Göreve göre gezinme:** İzleme, olay inceleme ve kayıt inceleme ana görevler; kurulum/yönetim ayrı bölüm. Dar ekranda menü katlanmalı, ana çalışma alanı ilk ekranda görünmeli. Dayanak: `web/index.html:336`, `web/index.html:284`.

**[yorum] Ortak görsel sistem:** Mevcut ölçülü palet korunabilir; okunabilir ikincil metin, belirgin odak, tutarlı durum etiketleri ve birincil eylem hiyerarşisi güçlendirilmeli. Desktop/mobile ortak token ve sözlüğe dayanmalı. Dayanak: `web/index.html:12`, `web/mobil.html:21`.

**[yorum] Hız hissini doğru durum yönetimiyle kur:** Ekran kabuğu hemen görünür; veriler bağımsız gelir; işlemler ilerleme, başarısızlık ve yeniden deneme durumlarını gösterir. Eski görüntünün veya eski alarm listesinin güncel sanılması önlenmeli. Dayanak: `web/index.html:437`, `web/index.html:801`, `web/mobil.html:400`.

## Uygulamadan önce hazırlanacak iş sırası

1. **[yorum] Davranış stabilizasyonu:** İstek iptali/sürüm kontrolü, snapshot yükü, kontrollü yenileme ve bağımsız panel kartları. Dayanak: F1–F5; `web/index.html:437`, `src/server.py:1215`.
2. **[yorum] Akış prototipi:** Operasyon özeti → alarm kanıtı → olay anı kaydı → operatör kabulü. Dayanak: `web/mobil.html:329`, `web/index.html:1166`.
3. **[yorum] Görsel uygulama:** Önce Panel, Olaylar, Canlı ve Kayıtlar; sonra yönetim ekranları. Kontrast, responsive ve beş durum (dolu/boş/yükleniyor/hata/taşma) birlikte kabul edilmeli. Dayanak: `web/index.html:790`, `web/index.html:1137`.
4. **[yorum] Donanım üzerinde ölçüm:** Gerçek NVIDIA ve CPU kurulumlarında aynı kamera/operatör senaryoları. UI kaynaklı yük ile inference/decode yükü ayrı kaydedilmeli. Tarihsel GB10 sonuçları kabul ölçütü değildir; kullanıcı düzeltmesi bu raporun kapsamındadır.

## Açık sorular ve ölçülmeyenler

- Kullanıcının yavaşlık yaşadığı çalışan panelin adresi ve sürümü henüz sağlanmadı.
- Kullanılan NVIDIA kartları, CPU ve aktif kamera/operatör sayısı bilinmiyor.
- Gerçek video taşıma yolu, API p95, uzun görevler ve bellek davranışı ölçülmedi.
- Klavye turu, ekran okuyucu ve tüm formların erişilebilirliği uçtan uca doğrulanmadı.
- Bu değerlendirme tasarım/uygulama onayı veya üretime hazır olma kanıtı değildir.
