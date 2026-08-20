# Kaynak kalitesi — güven hiyerarşisi ve etiketleme

## İçindekiler
- Güven hiyerarşisi (yüksekten alçağa)
- Bağımsızlık: kaç kaynak gerçekten kaç kaynaktır
- Çapraz-doğrulama ne zaman zorunlu
- Güven etiketleme kuralı (doğrulanmış / ikincil / spekülatif)
- Bayatlık ve kaynak damgası

## Güven hiyerarşisi (yüksekten alçağa)

Aynı iddiada üsttekini tercih et; alttaki yalnız destek/renk verir.

1. **Birincil, doğrulanabilir olgu.** Çalışan kaynak kod (dosya:satır),
   ölçüm çıktısı (test/bench sonucu), resmi spesifikasyon/RFC, standart
   doküman, üreticinin API referansı, birincil veri seti.
2. **Birincil beyan.** Proje maintainer'ının değişiklik notu, commit/PR
   mesajı, resmi changelog, konferans/POST-mortem'de birinci ağız.
3. **İkincil, editöryel.** İtibarlı teknik yayın, kitap, iyi bilinen
   mühendisin derinlemesine yazısı — birincili yorumlar ama değildir.
4. **İkincil, genel.** Sıradan blog, forum cevabı, Q&A sitesi — yararlı
   ipucu, zayıf kanıt.
5. **SEO / türev içerik.** "2026 ultimate guide", "top 10", içerik çiftliği,
   AI-üretimi özet. Çoğu birbirini kopyalar. Kanıt değeri ~sıfır; yalnız
   birincil kaynağa **giden yol** olarak kullan, iddianın kendisi için değil.

Kod tabanı işlerinde **kod ground-truth'tur** (AGENTS.md): dokümantasyon ile
kod çelişirse kod kazanır. Doküman bir "beyan"dır (3. seviye), kod bir
"olgu"dur (1. seviye).

## Bağımsızlık: kaç kaynak gerçekten kaç kaynaktır

"Üç blog aynı şeyi söylüyor" üç kaynak değildir eğer üçü de aynı orijinal
yazıdan besleniyorsa — bu **tek** kaynaktır, üç yankı. Gerçek bağımsızlık:

- Farklı **orijin** (biri kaynak kodu okumuş, diğeri kendi ölçmüş).
- Farklı **yöntem** (biri doküman, diğeri deneysel doğrulama).
- Çıkar çatışması yokluğu (ürünün kendi pazarlaması bağımsız kanıt değildir).

Sinyal: kaynaklar aynı cümleyi/örneği tekrarlıyorsa muhtemelen tek orijin.

## Çapraz-doğrulama ne zaman zorunlu

Zorunlu:
- İddia **kararı değiştiriyorsa** (seçilen seçenek, önerilen aksiyon buna
  dayanıyor).
- Kaynak 3. seviye veya altıysa (ikincil/genel/SEO).
- İddia sürpriz/çelişkiliyse ya da "çok iyi/çok kötü" görünüyorsa.
- Güvenlik, veri kaybı, geri alınamaz sonuç ihtimali varsa.

Gerekmez (ama kaynak yine de bağlanır):
- Birincil olgudan (kod:satır, ölçüm) doğrudan okunan, yoruma açık olmayan
  bilgi.
- Kararı etkilemeyen arka plan/renk bilgisi.

## Güven etiketleme kuralı

Her önemli iddia bir etiket taşır:

- **`doğrulanmış`** — birincil kaynak VE (kritikse) bağımsız ikinci kaynakla
  teyit. "Bunu gösterebilirim" seviyesi.
- **`ikincil`** — tek kaynak, ya da yalnız ikincil kaynak(lar). Muhtemelen
  doğru ama tek başına karar dayanağı olmamalı.
- **`spekülatif`** — kendi çıkarımın, tek zayıf işaret, ya da kaynağı
  doğrulayamadın. Rapora girerse mutlaka bu etiketle; çoğu zaman "açık
  sorular"a taşınır.

Kural: tek kaynaklı kritik iddia **en fazla `ikincil`** olur; çapraz
doğrulanmadan `doğrulanmış` olamaz.

## Bayatlık ve kaynak damgası

Kaynak zamanla yanlışa döner. Damgala:

- Web → erişim tarihi (bugün: rapor tarihi). Sürümlü doküman ise sürüm no.
- Kod → commit SHA veya en azından branch + tarih (dosya değişir).
- Ölçüm → ortam (makine, sürüm) ve tarih.

"Şu an doğru" bir tarih olmadan doğrulanamaz. 90 günden eski araştırma
bulgusu (AGENTS.md hafıza politikası) yeniden geçerlilik ister.
