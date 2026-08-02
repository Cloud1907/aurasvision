# RBAC tasarımı (UYGULANDI — src/kimlik.py + store/server/UI; testler tests/test_birim.py)

Hedef: tek AURAS_TOKEN yerine kullanıcı/rol. TRASSIR kıyasında saptanan eksik.

## Model (basit tutulacak)
- Tablo `kullanicilar(id, ad, parola_hash, rol, created_at)` — hash: hashlib.scrypt (saf stdlib, ek bağımlılık yok)
- Roller: `yonetici` (her şey), `operator` (izleme+kayıt+olay+ack+arama+rapor; kamera/bölge/liste değiştiremez), `izleyici` (salt okuma)
- Oturum: imzalı çerez token (secrets + HMAC, AURAS_TOKEN gizli anahtar olarak kalır) — JWT bağımlılığı YOK
- İlk açılışta kullanıcı yoksa: mevcut AURAS_TOKEN eski davranışla çalışır (geriye uyum, kurulumlar kırılmaz); ilk yönetici Sistem ekranından oluşturulur
- Middleware: yazma uçları (`POST/PATCH/DELETE`) rol denetimi; `/api/export` + kanıt erişimi denetim satırı yazar (`isteyen` artık gerçek kullanıcı — exporter'daki sembolik "operatör" kalkar)
- UI: giriş ekranı + sağ altta kullanıcı adı/çıkış; Sistem ekranına kullanıcı yönetimi kartı

## Sıra (tamamlandı)
1. ✅ store: kullanicilar tablosu + ekle/bul/listele/sil (iki arka uç, BaseStore'da tek gövde)
2. ✅ server: /api/giris (parola → çerez), middleware rol denetimi, /api/kullanicilar CRUD (yalnız yonetici)
3. ✅ UI: giriş formu (401 gövdesindeki `giris` alanına göre parola/token), Sistem'e kullanıcı kartı, sol altta kullanıcı rozeti + çıkış
4. ✅ exporter/ack `isteyen` gerçek kullanıcıdan (manifest ve acked_by)
5. ✅ Testler: rol matrisi + scrypt + imzalı çerez (tests/test_birim.py, TestRolMatrisi/TestKimlik/TestKullaniciStore)

## Uygulamada netleşen kararlar
- Çerez yalnız KİMLİĞİ kanıtlar; ROL her istekte DB'den okunur (10 sn önbellek).
  Böylece kullanıcı silme/rol düşürme oturum bitmesini beklemez — silinen
  kullanıcının çerezi anında ölür (canlıda doğrulandı).
- İlk kullanıcı ne seçilirse seçilsin yonetici yapılır (sistem yöneticisiz kalamaz);
  son yonetici API'den silinemez.
- POST /api/search yazma sayılmaz (sorgu gövdesi taşıyan okuma) — izleyici de arar.
- Operatörün yazabildikleri: alarm kabulü, kanıt dışa aktarma, test koşusu,
  arşiv klasörü açma. Kamera/bölge/liste/kullanıcı yönetimi yalnız yonetici.
- WebSocket (/api/stream) middleware kapsamı dışında — aynı sıra elle uygulanır:
  makine token'ı → oturum çerezi (DB'de hâlâ var mı kontrolüyle) → auth kapalı.
- Aynı adla ikinci `kullanici_ekle` upsert'tir = parola sıfırlama yolu (yönetici
  formdan aynı adla yeni parola girer).
