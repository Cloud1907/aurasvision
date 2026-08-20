---
name: research-with-evidence
description: Kaynaklı ve doğrulanabilir araştırma/keşif raporu üretir — her iddiaya kaynak bağlar, kaynak güvenini derecelendirir, doğrulanmış/ikincil/spekülatif ayrımını açık yapar. Kullanıcı "araştır, incele, karşılaştır, nerede tanımlı, nasıl çalışıyor, hangi seçenek, neden böyle" dediğinde kullan — rapor/doküman üretmek bu skill'e dahildir. Kod veya davranış değiştiren işte kullanma (bkz. implement-change).
---

# research-with-evidence

Amaç: çıktı "bence böyle" değil, **kanıtla savunulabilir** olsun. Bu skill
sana ne bulacağını dayatmaz; bulguyu nasıl kaynaklandıracağını, güvenini nasıl
derecelendireceğini ve kaynaksız iddiayı nasıl işaretleyeceğini öğretir.
İlke: **kanıt > beyan** (AGENTS.md). "Buldum" demek kanıt değildir; kaynak
kanıttır.

## Ne zaman geçerli

Bir soruya **karar** veya **envanter** üretmek için bilgi topluyorsan:
"nerede tanımlı", "nasıl çalışıyor", "hangi seçenek daha iyi", "bu iddia doğru
mu", "X ile Y'yi karşılaştır". Kaynak kod, web, repo geçmişi — hepsi geçerli
saha.

## Ne zaman geçerli DEĞİL (negatif tetik)

- Kod değiştiren, dosya yazan/düzenleyen iş → `implement-change`. Araştırma
  yalnız `.agents/reports/` altına tarihli rapor yazabilir; başka dosyaya
  dokunmaz (profil zaten engeller).
- Diff'i güvenlik açısından denetlemek → `security-review`.
- Diff tek cümleyle tarif edilebilen mikro iş → form/plan/rapor gereksiz.

## İş akışı (checklist — kopyala ve işaretle)

- [ ] 1. **Soruyu tek cümleye indir.** Cevabın neye yarayacağını belirle:
      karar mı (seçenek seçilecek), envanter mi (ne var), teşhis mi (neden
      böyle)? Bu, "yeterli kanıt" eşiğini belirler.
- [ ] 2. **Kaynak planı kur.** Hangi saha? Kod → dosya:satır. Web → URL.
      Geçmiş → commit/PR. Kritik iddia için ≥2 bağımsız kaynak hedefle
      (referans: `references/source-quality.md`).
- [ ] 3. **Topla ve etiketle.** Her bulguyu topladığın anda kaynağıyla
      birlikte not al. Kaynağı sonra "hatırlarım" deme — hatırlamazsın.
- [ ] 4. **Güven derecelendir.** Her iddia: `doğrulanmış` / `ikincil` /
      `spekülatif` (referans: `references/source-quality.md`).
- [ ] 5. **Çapraz doğrula.** Kararı etkileyen kritik iddiayı ikinci bağımsız
      kaynakla teyit et; tek kaynaklıysa "doğrulanmış" deme.
- [ ] 6. **Kaynak disiplinini uygula.** Her iddia cümlesi kaynak taşımalı
      (referans: `references/citation-discipline.md`).
- [ ] 7. **Raporu yapılandır.** TL;DR → bulgular → karar önerisi → açık
      sorular (referans: `references/report-structure.md`).
- [ ] 8. **Kaynak sinyalini ölç.** `python3 scripts/check_citations.py
      <rapor.md>` → kaynaksız iddia oranı yüksekse geri dön.

## High-signal gotcha'lar (en yüksek sinyalli içerik)

- **Tek kaynak ≠ doğrulanmış.** Tek kaynaklı kritik iddiayı çapraz doğrulama
  yapmadan "doğrulanmış" sayma. En fazla `ikincil`.
- **SEO tuzağı.** "2026 ultimate guide", "top 10 X" tarzı içerik birincil
  kaynak değildir; çoğu birbirini kopyalar (yankı odası). Resmi doküman,
  RFC/spec, kaynak kod, birincil ölçüm > ikincil blog > SEO içerik.
- **Kaynak yankısı bağımsızlık değildir.** Aynı orijinal iddiayı tekrarlayan
  üç blog "üç kaynak" değildir — tek kaynaktır. Bağımsızlık = farklı orijin.
- **Kod ground-truth'tur.** Dokümantasyon ile kod çelişirse kod kazanır;
  doküman bayat olabilir. İddiayı dosya:satır ile bağla, README ile değil.
- **Bayatlık.** Web kaynağına erişim tarihini, koda commit SHA'sını not al;
  "şu an doğru" zamanla yanlışa döner.
- **Kendi çıkarımını kaynak sanma.** "Muhtemelen böyle çalışıyor" bir bulgu
  değil hipotezdir → `spekülatif` etiketle veya rapordan çıkar.
- **LLM incelemesi kanıt değildir.** Codex/model görüşü risk sinyalidir
  (AGENTS.md); rapora "kanıt" olarak değil "sinyal" olarak girer.
- **Yokluk kanıtı ≠ kanıt yokluğu.** "Aradım, bulamadım" bir bulgudur ama
  arama kapsamını (hangi path'ler, hangi terimler) yaz; yoksa doğrulanamaz.

## Validation loop

`python3 scripts/check_citations.py <rapor.md>` → kaynaksız görünen iddia
oranını raporlar. Yüksekse (varsayılan eşik %20): ya kaynak ekle, ya iddiayı
`spekülatif` etiketle, ya da çıkar → tekrar çalıştır. Bu, öznel "yeterince
kaynaklı mı" sorusunu ölçülebilir bir orana çevirir. Script kaba bir
sinyaldir, hakem değil: düşük oran iyi kaynaklandırmayı garanti etmez ama
yüksek oran neredeyse kesin bir sorundur.

## Çıktı formatı

Rapor `.agents/reports/` altına tarihli dosya olarak yazılabilir. İskelet:

1. **TL;DR** — 3 cümle: ne soruldu, ne bulundu, ne öneriliyor.
2. **Bulgular** — her biri kaynaklı ve güven-etiketli (`doğrulanmış` /
   `ikincil` / `spekülatif`).
3. **Karar önerisi** — bulgulardan çıkan aksiyon; gerekçe kaynaklara dayanır.
4. **Açık sorular** — doğrulanamayanlar, eksik kalan kaynaklar, sonraki adım.

Tam iskelet + iyi/kötü örnek: `references/report-structure.md`.

## Referanslar

- `references/source-quality.md` — kaynak güven hiyerarşisi, çapraz-doğrulama
  kuralı, güven etiketleme.
- `references/citation-discipline.md` — her iddiaya kaynak bağlama biçimleri
  (dosya:satır, URL, commit/PR), kaynaksız iddia işaretleme.
- `references/report-structure.md` — dünya standardı rapor iskeleti + örnek.

## Eval

`eval/cases.md` — temsili vakalar (biri negatif: kod değişikliği işinde
tetiklenmemeli). Ölçüt: rapor başına kaynaklı-iddia oranı; sonradan yanlış
çıkan iddia sayısı (Memory Correction Rate'in araştırma ayağı).
