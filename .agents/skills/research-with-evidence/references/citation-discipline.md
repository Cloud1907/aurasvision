# Kaynak disiplini — her iddiaya izlenebilir bağ

## İçindekiler
- Temel kural
- Kaynak biçimleri (kod / web / geçmiş)
- İddia mı, arka plan mı: neyi kaynaklamalı
- Kaynaksız iddia nasıl işaretlenir
- İyi / kötü kaynaklama örnekleri

## Temel kural

**Her iddia cümlesi, onu doğrulayacak birinin gidebileceği bir kaynak
taşır.** Kaynak = başkasının senin bulgunu bağımsızca teyit edebileceği
adres. "Buldum" değil, "şurada": okuyucu tıklayıp/açıp görebilmeli.

Kaynaksız iddia iki şeyden biridir: (a) kaynağını yazmayı unuttuğun bir
olgu → kaynağı ekle; (b) aslında senin çıkarımın → `spekülatif` etiketle.
Üçüncü seçenek (kaynaksız kesin iddia) yasak.

## Kaynak biçimleri

### Kod tabanı → `dosya:satır`

- Biçim: `path/to/file.py:42` veya aralık `file.py:42-58`.
- Kök-göreli yol kullan (repo kökünden). Belirsizse fonksiyon/sembol adı ekle:
  `bin/validate.py:test_skills()`.
- Değişebilecek kodda commit SHA ekle: `file.py:42 @4b0a4cd`.
- Örnek: "Skill adı dizinle eşleşmeli (`bin/validate.py:71`)."

### Web → tam URL

- Çıplak, tıklanabilir URL. Query string'e kişisel/oturum verisi koyma.
- Erişim tarihi ekle (kaynak bayatlar): `(erişim: 2026-07-24)`.
- Derin bağ: sayfanın tümü değil ilgili bölüm/anchor.
- Örnek: "WCAG normal metin eşiği 4.5:1'dir
  (https://www.w3.org/TR/WCAG22/#contrast-minimum, erişim: 2026-07-24)."

### Repo geçmişi → `commit` / `PR` / `issue`

- Commit: kısa SHA + tek satır özet: `4b0a4cd (/auras: tek komutla bağlama)`.
- PR/Issue: `#123` (repo bağlamında) veya tam URL.
- "Ne zaman/neden değişti" sorularının kaynağı burasıdır, kodun kendisi değil.
- Örnek: "Kanca kontrolü CI'da atlanır kararı `86cbe4e`'de alındı."

## İddia mı, arka plan mı: neyi kaynaklamalı

Kaynak **iddiaları** taşır — doğru ya da yanlış olabilecek, kararı etkileyen
önermeler. Genel bilgi ("Python 3 yaygın kullanılır") ve senin akıl
yürütme cümlelerin kaynak istemez. Ayrım testi: "Biri buna "kanıtın ne?"
diye sorabilir mi?" → evetse kaynakla.

- İddia (kaynakla): "Bu fonksiyon O(n²) çalışıyor", "X kütüphanesi Y'yi
  desteklemiyor", "Bu path deny listesinde".
- Arka plan/çıkarım (kaynak gerekmez ama spekülatifse etiketle): "Bu yüzden
  büyük girdide yavaşlar" (çıkarım), "Genelde böyle yapılır" (genel bilgi).

## Kaynaksız iddia nasıl işaretlenir

Kaynağını o an bağlayamıyorsan iddiayı çıplak bırakma. Seçenekler:

- **`[kaynak?]`** — satır içi işaret: doğrulanacak, henüz bağlanmadı. Rapor
  teslim edilmeden hepsi çözülmeli (ya kaynak, ya spekülatif).
- **`spekülatif`** etiketi — bu senin çıkarımın, kaynağı yok ve olmayacak.
- **"Açık sorular"a taşı** — doğrulanamadı, sonraki adımda bakılmalı.

`scripts/check_citations.py` tam da bu çıplak iddiaları kaba biçimde
yakalamak için var: kaynaksız görünen iddia oranı yüksekse rapor ham demektir.

## İyi / kötü kaynaklama örnekleri

**Kötü:**
> Validate script'i skill adının dizinle eşleştiğini kontrol eder ve
> açıklama en az 40 karakter olmalıdır. Bu iyi bir tasarım.

Sorun: iki iddia da kaynaksız (nerede?), "iyi tasarım" gerekçesiz görüş.

**İyi:**
> Validate script'i skill `name` frontmatter'ının dizin adıyla eşleşmesini
> (`bin/validate.py:71`) ve `description`'ın ≥40 karakter olmasını
> (`bin/validate.py:76`) zorunlu kılar. Her ikisi de `test_skills()`
> içinde. — `doğrulanmış`

Fark: her iddia dosya:satır taşıyor, görüş çıkarıldı, güven etiketli.
