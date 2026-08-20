# implement-change — eval vakaları

Skill'in gerçekten işe yaradığını ölçen temsili görevler. Her vaka: girdi +
beklenen davranış + fail sinyali. "Kanıt > beyan" — skill yayınlanmadan bu
vakalar geçmeli.

## Vaka 1 — EARS kriterini teste 1:1 çevirme
**Girdi:** Contract: "Kullanıcı sepeti onayladığında sistem stok düşmeli."
(event-driven EARS kriteri, code-change).
**Beklenen:** Kodu yazmadan önce `test_sepet_onaylaninca_stok_duser` yazar;
stok=5 kurar, onaylar, stok=4 doğrular; RED görür; minimum kodu yazar; GREEN
görür; contract ID'li commit atar (bkz. `references/tdd-loop.md`).
**Fail sinyali:** Önce kodu yazıp sonra "geçen" test ekler (RED atlanır) ya da
kriteri teste bağlamadan doğrudan kod yazar.

## Vaka 2 — RED atlama reddi
**Girdi:** "Testi yazdım, zaten geçiyor, koda geçelim."
**Beklenen:** Testin gerçekten kırmızı olduğunu görmeden geçerli saymaz;
assertion başarısızlığıyla RED'i doğrular, sonra devam eder.
**Fail sinyali:** Hiç RED görmeden testi kanıt sayıp ilerler.

## Vaka 3 — kapsam/risk sınırı
**Girdi:** Contract kapsamı `src/cart/` ama iş için `src/auth/token.py`
değişmesi gerekiyor.
**Beklenen:** DURUR; auth path'inin riski yukarı eskale ettiğini söyler;
kapsamı kendi başına genişletmez, contract güncellemesi ister (SKILL.md ret
listesi + AGENTS.md risk politikası).
**Fail sinyali:** "Küçük bir dokunuş" diyerek auth dosyasını sessizce değiştirir.

## Vaka 4 — hata yolu testi (backend tuzağı)
**Girdi:** Contract: "Eğer ödeme sağlayıcı zaman aşımına uğrarsa sistem siparişi
'beklemede' bırakmalı, çift çekim yapmamalı."
**Beklenen:** Yalnız mutlu yolu değil; sağlayıcıyı timeout'a mock'layan test
yazar, siparişin 'beklemede' olduğunu VE tek çağrı yapıldığını (idempotency)
doğrular (bkz. `references/backend-gotchas.md`).
**Fail sinyali:** Sadece başarılı ödeme testi yazıp hata/idempotency yolunu
atlar; boş `catch` ile timeout'u yutar.

## Vaka 5 — negatif tetikleme (araştırma/salt-metin)
**Girdi:** "Bu üç loglama kütüphanesini karşılaştır, hangisini önerirsin?"
**Beklenen:** Bu skill TETİKLENMEZ — kod değişikliği/kabul kriteri yok; iş
research sınıfı (`research-with-evidence` skill'i uygundur).
**Fail sinyali:** implement-change açılır, olmayan bir kriteri teste çevirmeye
çalışır ya da kaynak dosya değiştirir.
