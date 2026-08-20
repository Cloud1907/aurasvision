# TDD döngüsü — RED→GREEN→commit derinlemesine

## İçindekiler
- Neden test önce
- Döngü adımları
- EARS kabul kriterini teste 1:1 çevirme
- Testi doğru yazmanın kuralları
- Test değiştirmek ne zaman meşru
- Yaygın anti-pattern'ler

## Neden test önce
Testi koddan önce yazmak üç şeyi garanti eder: (1) kriterin gerçekten
test edilebilir olduğunu kanıtlar — test edilemeyen kriter belirsiz kriterdir;
(2) testin bir şeyi ölçtüğünü kanıtlar — RED görmeden yazılan test her zaman
GREEN olabilir ve bunu fark etmezsin; (3) minimum kodu yazmaya zorlar —
GREEN'e ulaşınca durursun, gold-plating yapmazsın.

"Bitti" bir beyandır. Kanıt, kriteri temsil eden testin önce kırmızı sonra
yeşil olmasıdır. Bu iz PR gövdesine ve CI kanıtına yansır.

## Döngü adımları
1. **Bir kriter seç.** Aynı anda tek kriter; iş bölünmez (tek yazar ilkesi).
2. **Failing test yaz.** Kriteri ifade eden en küçük testi yaz.
3. **Koş ve RED gör.** Test gerçekten başarısız mı? Hangi mesajla? Beklenen
   başarısızlık bu mu? "Import error" ya da "syntax error" RED sayılmaz —
   assertion başarısızlığı görmelisin.
4. **Minimum kodu yaz.** Testi geçirecek en az kod. Fazlasını yazma; başka
   kriter için kod yazma.
5. **Koş ve GREEN gör.** Bu test ve tüm önceki testler yeşil mi?
6. **Küçük tek-amaçlı commit.** Mesajda ne + neden; contract'lı işte contract ID.
7. **Tekrarla.** Bir sonraki kritere geç.

Refactor adımı isteğe bağlıdır ve yalnız testler GREEN'ken yapılır: davranışı
değiştirmeden yapıyı iyileştir, sonra testleri tekrar koş.

## EARS kabul kriterini teste 1:1 çevirme
EARS (Easy Approach to Requirements Syntax) kalıpları doğrudan test yapısına
çevrilir. Her kalıp → Arrange/Act/Assert.

**Ubiquitous (her zaman):** "Sistem, para birimini her zaman ISO 4217 kodu
olarak saklamalı."
→ `test_para_birimi_iso4217_saklanir`: bir kayıt oluştur, DB'deki alanın
"USD"/"TRY" gibi 3 harfli kod olduğunu doğrula.

**Event-driven (X olduğunda):** "Kullanıcı sepeti onayladığında sistem stok
düşmeli."
→ `test_sepet_onaylaninca_stok_duser`: stok=5 kur (Arrange), onayla (Act),
stok=4 doğrula (Assert).

**State-driven (X iken):** "Hesap kilitliyken sistem giriş denemesini
reddetmeli."
→ `test_kilitli_hesap_girisi_reddeder`: hesabı kilitli duruma getir, giriş
dene, 403/hata doğrula.

**Unwanted behavior (Eğer X olursa):** "Eğer ödeme sağlayıcı zaman aşımına
uğrarsa sistem siparişi 'beklemede' bırakmalı, çift çekim yapmamalı."
→ `test_odeme_timeout_ciftcekim_yok`: sağlayıcıyı timeout'a mock'la, siparişin
'beklemede' olduğunu VE tek çağrı yapıldığını doğrula (idempotency).

**Optional (Y özelliği varsa):** "Kupon girildiyse sistem indirimi uygulamalı."
→ `test_kupon_varsa_indirim`: kuponlu ve kuponsuz iki test.

Kural: bir kriterde birden fazla "ve/veya" varsa muhtemelen birden fazla test
gerekir. Sınır koşulları (0, negatif, boş, çok büyük, eşzamanlı) EARS'te yazsa
da yazmasa da ayrı test hak eder.

## Testi doğru yazmanın kuralları
- **Bir testte bir davranış.** Assert yığını değil; her test tek bir "neden".
- **Davranışı test et, implementasyonu değil.** Private metodu değil, gözlenen
  sonucu doğrula — refactor testi kırmamalı.
- **Deterministik ol.** Zaman, rastgelelik, ağ, sıralama bağımlılığı = kırılgan
  test. Saati/UUID'yi/clock'u enjekte et, mock'la.
- **Anlamlı isim.** `test_1` değil, `test_kilitli_hesap_girisi_reddeder`. İsim
  kriteri okutmalı.
- **Arrange/Act/Assert ayrımı** görünür olsun; kurulum ile doğrulama karışmasın.

## Test değiştirmek ne zaman meşru
Testi GREEN yapmak için testi zayıflatmak yasaktır. Ama test değiştirmek her
zaman yasak değildir. Meşru sebepler (hepsi PR gövdesinde gerekçelenir):
- **Kriter değişti.** Contract güncellendi; yeni davranışı yansıtan test doğru
  olandır. Önce contract, sonra test.
- **Test yanlış yazılmıştı.** Kriteri yanlış temsil ediyordu (ör. yanlış beklenen
  değer). Düzeltme kriterle hizalar.
- **Test kırılgandı.** Zamana/sıraya bağlıydı; determinizmi artıran değişiklik.

Meşru olmayan: "kod böyle davranıyor, testi ona uydurayım." Bu, kriteri
sessizce değiştirmektir — kanıtı sahteleştirir.

## Yaygın anti-pattern'ler
- **RED atlanmış test:** hiç kırmızı görülmeden yazılmış; kanıt değeri sıfır.
- **Tautology:** `assert x == x` ya da mock'un kendi döndürdüğünü doğrulamak.
- **Aşırı mock:** her şey mock'lanınca test gerçek entegrasyonu değil kurguyu
  test eder. Sınırları mock'la, çekirdek mantığı gerçek koş.
- **Test sonrası yazımı (test-after) kamufle:** kodu yazıp sonra "geçen" test
  eklemek RED adımını atlar; disiplin sinyali `check_test_first.py` bunu
  yakalamaz ama sen bilirsin — RED'i gör.
