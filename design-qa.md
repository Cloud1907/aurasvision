# AurasVision birleşik operasyon paneli — tasarım QA

Tarih: 2026-09-22

## Karşılaştırma girdileri

- Kaynak referans: `/var/folders/yn/t5zkpqvs1v5f4hbzq6lfhlhh0000gn/T/codex-clipboard-a81460ef-8898-4cb5-990b-b2061b168b52.png`
- Uygulama: `http://127.0.0.1:8768/`
- Görsel kontrol: Codex uygulama içi tarayıcı, 1440×900 masaüstü ve 390×844 mobil görünüm

## Kabul edilen tasarım kararları

- Panel ve canlı izleme tek operasyon ekranında birleştirildi.
- İlk görünümde dört kamera, dört KPI, aktif alarm listesi ve veri temelli olay grafiği bulunuyor.
- Sol menüde ayrı bir `Gelişmiş` alanı bulunmuyor. Bütün sayfalar `İzleme`, `Analizler` ve `Ayarlar` akordeon gruplarına yerleştirildi; yalnız seçilen grup açık kalıyor.
- Dört KPI panelin üstünde ayrı kartlara taşındı; değer, bağlam ve önem tonu birlikte gösteriliyor.
- Analiz alanında parlayan yumuşak yoğunluk eğrisi, degrade alan, zaman yoğunluğu izi ve olay türü halka grafiği birlikte gösteriliyor.
- KPI, kamera, alarm, analiz ve alt özet kartları tema uyumlu saydam cam yüzeylere dönüştürüldü; blur, ince parlak kenar ve kontrollü gölge aynı sistemden geliyor.
- Canlı akış yokken sahte kamera görseli kullanılmıyor; açık bir `Görüntü alınamadı` durumu gösteriliyor.
- Alarm davranışı kamera ve alarm türüne göre popup, ses, ton ve tekrar süresiyle ayarlanabiliyor.
- Alarm kuyruğu ilk yüklenirken veya elle yenilenirken, mevcut sonucu kaybetmeden işlem adımlarını açıklayan kompakt bekleme kartı gösteriliyor; anlık filtre değişimlerine sahte gecikme eklenmiyor.
- Giriş kapısı sağ–sol bölünmüş düzende. Sol yüzün tamamını React Bits `DomeGallery`
  kaplar; karolar `web/assets/kapi` altındaki yerel görsellerdir (köken: KAYNAK.md),
  dış ağa istek atılmaz. Kubbe saniyede 0,55 derece kendiliğinden döner, sürüklenirken
  durur, hareket azaltma tercihinde hiç başlamaz. Karo üstündeki temsili `REC` ve saat
  damgaları kaldırıldı: karolar kamera görüntüsü değil. Sağ kolon yüzen cam kart yerine
  sakin bir giriş sütunudur. Görünen tek form eylemi `Giriş yap`; kullanıcı adı ve parola
  alanı bulunmuyor.
- Önceki sürümde kubbe karoları hiç yüklenmiyordu: sahne çizimleri `xmlns` taşımadığı
  için tarayıcı reddediyor, karolarda kırık görsel işareti çıkıyordu. Sahne üreticisi
  tamamen kaldırıldı.
- İlk bağlantıda eski alarmlar yeniden oynatılmıyor; kapatmak alarmı kabul etmiyor.

## Kontrol sonuçları

- Masaüstü hiyerarşisi ve referansla uyum: geçti
- Mobil yatay taşma ve menü açma/kapatma: geçti
- Cam yüzey kontrastı, grafik okunabilirliği ve 801 px yatay taşma kontrolü: geçti
- Koyu tema okunabilirliği: geçti
- Alarm ayarlarının görünürlüğü ve alan etiketleri: geçti
- Tarayıcı sesinin kullanıcı hareketiyle etkinleşmesi: geçti
- Gerçek veri / boş durum ayrımı: geçti
- Klavye ve erişilebilir adlandırma: geçti
- Azaltılmış hareket desteği: kod ve hedefli test kapsamı mevcut

## Kanıt

- Python hedefli testler: 107 geçti
- Bildirim politikası Node testleri: 2 geçti
- UI paketi: başarıyla derlendi
- `git diff --check`: temiz
- Uygulama içi tarayıcı: masaüstü ve mobil görsel inceleme tamamlandı

2026-09-22 ikinci tur — giriş kapısı ve panel:

- Kubbe: 130 karo, 0 kırık görsel, 20 benzersiz görsel, konsol hatası yok.
- Kontrast gerçek piksellerden ölçüldü (fotoğrafın en parlak %2'sine karşı):
  masaüstü ve mobilde tüm metinler eşiği geçti.
- Ekran geçişi performansı: 11 ekran 19–238 ms, uzun görev yok
  (`e2e/ui-gecis-performansi.spec.ts`).
- Giriş kapısı e2e senaryosu (V12) geçti.
- Panelin 8 e2e senaryosu kırmızı; hepsi V4 yenilemesiyle değişen eski işaretleri
  arıyor, bu turun değişikliğinden bağımsız.

final result: passed (giriş kapısı) · panel e2e senaryoları güncellenmeyi bekliyor
