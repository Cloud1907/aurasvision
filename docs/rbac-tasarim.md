# RBAC tasarımı (uygulama sırada — bu belge yol haritası)

Hedef: tek AURAS_TOKEN yerine kullanıcı/rol. TRASSIR kıyasında saptanan eksik.

## Model (basit tutulacak)
- Tablo `kullanicilar(id, ad, parola_hash, rol, created_at)` — hash: hashlib.scrypt (saf stdlib, ek bağımlılık yok)
- Roller: `yonetici` (her şey), `operator` (izleme+kayıt+olay+ack+arama+rapor; kamera/bölge/liste değiştiremez), `izleyici` (salt okuma)
- Oturum: imzalı çerez token (secrets + HMAC, AURAS_TOKEN gizli anahtar olarak kalır) — JWT bağımlılığı YOK
- İlk açılışta kullanıcı yoksa: mevcut AURAS_TOKEN eski davranışla çalışır (geriye uyum, kurulumlar kırılmaz); ilk yönetici Sistem ekranından oluşturulur
- Middleware: yazma uçları (`POST/PATCH/DELETE`) rol denetimi; `/api/export` + kanıt erişimi denetim satırı yazar (`isteyen` artık gerçek kullanıcı — exporter'daki sembolik "operatör" kalkar)
- UI: giriş ekranı + sağ altta kullanıcı adı/çıkış; Sistem ekranına kullanıcı yönetimi kartı

## Sıra
1. store: kullanicilar tablosu + ekle/doğrula/listele (iki arka uç)
2. server: /api/giris (parola → çerez), middleware rol denetimi, /api/kullanicilar CRUD (yalnız yonetici)
3. UI: giriş formu (token isteme yerine), Sistem'e kullanıcı kartı
4. exporter/ack `isteyen` gerçek kullanıcıdan
5. Testler: rol matrisi (izleyici yazamaz, operator kamera silemez)
