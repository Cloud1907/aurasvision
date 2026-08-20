---
name: implement-change
description: Kod/davranış değişikliğini spec-anchored TDD döngüsüyle uygular — kabul kriterini teste 1:1 çevirir, RED→GREEN→commit ritmiyle ilerler, backend/frontend tuzaklarını erken yakalar. Kullanıcı "yap, uygula, ekle, düzelt, refactor et, şu bug'ı çöz, endpoint ekle" dediğinde kullan; kabul kriteri (EARS) yoksa önce onu üret, skill'i atlamak için değil. Araştırma, salt inceleme, doküman veya keşif işinde kullanma.
---

# implement-change

Amaç: kod değişikliği "çalışıyor gibi" değil, kanıtlı çalışsın. Bu skill sana
mimari DAYATMAZ; her kabul kriterini önce başarısız bir teste, sonra minimum
koda bağlamayı ve tipik backend/frontend tuzaklarına düşmemeyi öğretir.
"Bitti" bir beyandır; kanıt CI'dan gelen yeşil test + `evidence.json`'dur.

## Ne zaman geçerli
Contract'ı (GitHub Issue Form) olan, EARS kabul kriterleri tanımlı bir
**code-change** işi uygulanıyorsa. DEĞİL: araştırma/keşif (bkz.
`research-with-evidence`), salt kod incelemesi (bkz. `security-review`),
doküman/metin işi, ya da diff tek cümleyle tarif edilebilen `micro` iş
(o zaman form/plan atlanır, doğrudan küçük commit).

## İş akışı (checklist — kopyala ve işaretle)
- [ ] 1. Contract'ı oku: hedef, EARS kriterleri, kapsam (izinli path'ler),
      görev sınıfı, ön-risk, zorunlu kanıt. (referans: `references/tdd-loop.md`)
- [ ] 2. Kapsamı doğrula: izinli path yetiyor mu? Yetmiyorsa DUR, contract
      güncellemesi iste — kendi başına genişletme, kendi riskini yükseltme.
- [ ] 3. Her EARS kriterini bir teste çevir: "X olduğunda sistem Y yapmalı"
      → bir test case. Eşleme tablosunu tut (kriter → test adı).
- [ ] 4. TDD döngüsü (kriter başına en az bir tur): failing test yaz → koş,
      **RED gör** → minimum kodu yaz → **GREEN gör** → küçük tek amaçlı commit.
- [ ] 5. Değişen yüzeye göre tuzak listesini geçir: backend ise
      `references/backend-gotchas.md`, frontend ise `references/frontend-gotchas.md`.
- [ ] 6. Test disiplini sinyalini çalıştır: `python3 scripts/check_test_first.py`
      → kaynak değişmiş ama test değişmemişse gerekçelendır ya da test ekle.
- [ ] 7. Commit hijyeni: küçük, tek-amaçlı, contract ID'li mesaj; ilgisiz iş
      karıştırma (referans: `references/commit-hygiene.md`).
- [ ] 8. Kanıt topla: test çıktısı + koşulan komutlar + (UI ise) screenshot.
      PR gövdesine contract ID + kriter→test eşlemesi yaz.

## Zorunlu ret listesi (bunları yaparsan dur ve yeniden düşün)
- **RED'i atlamak:** testin gerçekten kırmızı olduğunu görmeden yazılan test
  hiçbir şeyi kanıtlamaz — yanlış pozitif üretir (bkz. `references/tdd-loop.md`).
- **Testi koda uydurmak:** kod GREEN olsun diye asserti gevşetmek. Test
  kriteri temsil eder; kriteri değiştirmiyorsan testi zayıflatma.
- **Kapsamı sessizce genişletmek:** izinli olmayan path'e "küçük bir dokunuş".
  Kapsam yetmiyorsa contract güncellenir, kod değil.
- **İlgisiz işi tek PR'a doldurmak:** bisect/rollback/kanıt izini bozar.
- **Hata yutmak:** boş `catch`/`except`, loglanmadan yutulan istisna. Sessiz
  başarısızlık en pahalı tuzaktır (bkz. `references/backend-gotchas.md`).

## High-signal gotcha'lar (bu sistemin/bu projenin bilmen gerekenleri)
- **Risk yukarı eskale olur, geri dönmez.** Diff auth/ödeme/migration/secret
  path'ine dokunursa akış `approval`/`deny`'a döner — bunu görmezden gelip
  auto akışta devam etme; ön-risk ile nihai risk ayrı hesaplanır.
- **Deny her zaman önceliklidir.** secret/credential dosyası, veri silme,
  prod migration, permission genişletme = varsayılan red. Break-glass süreli +
  gerekçeli + kayıtlı olmadan dokunma.
- **Kanıt > beyan.** Yeşil olmayan CI ile "bitti" denmez. `make_evidence.py`
  failed check'te non-zero döner; bunu gizleme.
- **Stil taklidi:** bu repo tr-TR yorum, İngilizce tanımlayıcı. Mevcut dosyanın
  desenini (DI, hata tipi, test kurgusu) taklit et; kendi tarzını dayatma.
- **Test değiştirmek meşru olabilir** ama nedeni PR gövdesine yazılır — kriter
  değişti mi, test yanlış mı yazılmıştı? (bkz. `references/tdd-loop.md`).

## Validation loop
`python3 scripts/check_test_first.py` → değişen kaynak dosyalar için karşılık
gelen test değişmiş mi bakar. Uyarı verirse: ya kriteri karşılayan testi ekle,
ya da (config/dokümantasyon/pür refactor gibi) meşru istisnayı `--allow` ile
kaydet. Bu, "test yazdım" beyanını ölçülebilir bir sinyale çevirir — kanıt
değildir ama disiplini görünür kılar. Nihai kanıt CI test job'ıdır.

## Referanslar
- `references/tdd-loop.md` — RED→GREEN→commit döngüsü; EARS→test 1:1 çevirisi;
  test değiştirme ne zaman meşru.
- `references/backend-gotchas.md` — DI, transaction sınırı, N+1, hata yutma,
  sözleşme kırma, idempotency, race condition.
- `references/frontend-gotchas.md` — state senkronu, gereksiz re-render, XSS,
  dark mode, a11y, 60fps.
- `references/commit-hygiene.md` — küçük tek-amaçlı commit, contract ID,
  ilgisiz iş karıştırmama.

## Çıktı
Test çıktısı (RED→GREEN izi) + koşulan komutlar ve sonuçları + UI işiyse
önce/sonra screenshot. PR gövdesinde contract ID + kriter→test eşleme tablosu.
CI `evidence.json` üretir (şema: `schemas/evidence.schema.json`).

## Eval
`eval/cases.md` altındaki temsili vakalar (biri negatif: araştırma/salt-metin
işinde tetiklenmemeli). Skill Lift ölçümü: bu skill'le/skill'siz koşuların
First-pass Acceptance ve kriter→test eşleme oranı kıyası.
