# Backend tuzakları — davranış değişikliğinde erken yakala

## İçindekiler
- Bağımlılık enjeksiyonu (DI) ve yaşam döngüsü
- Transaction sınırı
- N+1 ve sorgu patlaması
- Hata yutma ve sessiz başarısızlık
- Sözleşme kırma (API/contract)
- Idempotency
- Race condition ve eşzamanlılık

Her tuzak: belirti → neden → test edilebilir savunma.

## Bağımlılık enjeksiyonu (DI) ve yaşam döngüsü
**Belirti:** İstekler arası veri sızıyor, "ara sıra" hatalar, testte geçip
prod'da patlıyor.
**Neden:** Yanlış scope. Singleton'a request-scoped bağımlılık (DbContext,
kullanıcı bağlamı) enjekte etmek; captive dependency. Ya da new'lenmiş
bağımlılık — test edilemez, mock'lanamaz.
**Savunma:** Bağımlılığı constructor'dan al, elle new'leme. Scope'u doğru seç
(request-scoped state singleton'a girmez). Test: bağımlılığı mock'layıp
davranışı izole doğrula — mock'lanamıyorsa DI yanlıştır.

## Transaction sınırı
**Belirti:** Yarım yazılmış veri; bir tablo güncellendi diğeri güncellenmedi.
**Neden:** Transaction ya hiç yok ya yanlış yerde. Birden fazla yazma tek atomik
birim olmalıyken ayrı commit'lerde. Ya da transaction içinde ağ çağrısı/uzun
iş → kilit tutma, deadlock.
**Savunma:** İş kuralı "ya hep ya hiç" ise tek transaction. Transaction'ı dar
tut — içine HTTP çağrısı, e-posta, dış API koyma. Test: bir adımı ortada
başarısız et (mock exception), hiçbir kısmi yazının kalmadığını doğrula
(rollback).

## N+1 ve sorgu patlaması
**Belirti:** Liste büyüdükçe endpoint lineer yavaşlıyor; log'da yüzlerce benzer
sorgu.
**Neden:** Döngü içinde lazy-load; her eleman için ayrı sorgu. ORM'in tembel
navigasyonu.
**Savunma:** İlişkili veriyi tek sorguda çek (eager load / join / IN).
Test/ölçüm: sorgu sayısını say (çoğu ORM/test aracı sorgu sayacı sunar); N
elemanda sorgu sayısı sabit kalmalı, N'e bağlı olmamalı. Ölçümsüz "hızlandırdım"
kanıt değil — before/after sorgu sayısı ver (database-engineer'a devretmek
gerekebilir).

## Hata yutma ve sessiz başarısızlık
**Belirti:** "Neden çalışmadı bilmiyoruz"; hata log'da yok; kullanıcı sessizce
yanlış sonuç alıyor.
**Neden:** Boş `catch{}`/`except: pass`; istisnayı loglamadan yutmak; hatayı
genel bir "başarılı" ile maskeleme; `null`/default dönüp devam etme.
**Savunma:** Ya hatayı ele al (anlamlı biçimde), ya yukarı fırlat — asla sessizce
yutma. Yakaladığın istisnayı logla ve bağlam ekle. Test: hata yolunu ayrıca
test et — dış bağımlılık patladığında sistemin doğru hata/durum döndürdüğünü
doğrula, "mutlu yol" tek başına yetmez.

## Sözleşme kırma (API/contract)
**Belirti:** İstemci bozuldu; alan kayboldu/yeniden adlandı; tip değişti; enum
değeri değişti.
**Neden:** Response şemasında geriye uyumsuz değişiklik; zorunlu alan ekleme;
status code semantiği değiştirme.
**Savunma:** Genişletici değişiklik yap (alan ekle, kaldırma/yeniden adlandırma).
Kırıcı değişiklik gerekiyorsa versiyonla. Test: mevcut sözleşme testleri
(contract/schema test) hâlâ GREEN mi? Yeni alan opsiyonel mi? Bu path
`approval` riskine kayabilir — sözleşme değişikliği sinyaldir.

## Idempotency
**Belirti:** Çift çekim, çift kayıt, retry sonrası yan etki iki kez.
**Neden:** Yeniden gönderilebilen işlem (ödeme, webhook, mesaj) tekrar
çağrılınca etkiyi tekrar üretiyor. Ağ retry'ı, kullanıcı çift tıklaması,
at-least-once teslimat.
**Savunma:** Idempotency anahtarı; "zaten işlendi" kontrolü; upsert. Yan etkiyi
tekilleştir. Test: aynı isteği iki kez gönder, etkinin bir kez oluştuğunu
doğrula (EARS "unwanted behavior" kalıbı — bkz. tdd-loop.md).

## Race condition ve eşzamanlılık
**Belirti:** Yükte bozulan sayaç/stok; "check-then-act" arası başka işlem
araya giriyor; ara sıra tekrarlanmayan bug.
**Neden:** Oku-değiştir-yaz atomik değil; paylaşılan duruma kilitsiz erişim;
son-yazan-kazanır kaybı (lost update).
**Savunma:** Atomik operasyon (DB düzeyinde `UPDATE ... WHERE`, optimistic
locking/version, ya da uygun kilit). Kritik bölümü küçük tut. Test: eşzamanlılık
zordur; en azından mantığı optimistic-lock çakışması senaryosuyla test et
(iki eşzamanlı güncelleme, birinin reddedildiğini doğrula). Tam yük testi ayrı
bir doğrulama katmanıdır.
