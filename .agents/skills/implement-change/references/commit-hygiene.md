# Commit hijyeni — bisect/rollback/kanıt izi bozulmasın

## İçindekiler
- Neden önemli
- Küçük ve tek-amaçlı commit
- Commit mesajı ve contract ID
- İlgisiz işi karıştırmama
- PR yapısı ve kanıt izi
- Push politikası hatırlatması

## Neden önemli
Commit tarihi bir kayıt sistemidir. Her commit tek bir "neden" taşırsa: bir bug
`git bisect` ile hızla bulunur, hatalı değişiklik tek başına `revert` edilir,
ve PR incelemesi okunabilir kalır. Karışık commit'ler bu üç aracı da bozar.
Bu, AGENTS.md push politikasının doğrudan gereğidir.

## Küçük ve tek-amaçlı commit
- Bir commit = bir mantıksal değişiklik. TDD döngüsünde doğal birim: bir kriterin
  RED→GREEN turu (test + minimum kod birlikte ya da art arda).
- Refactor'u davranış değişikliğinden ayır. "Yeniden adlandırma + yeni özellik"
  aynı commit'te olmaz — biri gürültü, diğeri sinyal.
- Formatlama/whitespace değişikliğini işlevsel değişiklikle karıştırma; diff'i
  okunamaz yapar.
- "Çalışan" ara durumları commit'le; bozuk ara durumu (kırmızı build) main'e
  taşıyacak şekilde değil.

## Commit mesajı ve contract ID
- Biçim: kısa, emir kipi, ne + neden. Konu satırı dar; detay gövdede.
- Dil: tr-TR açıklama, İngilizce tanımlayıcı (bu repo konvansiyonu).
- Contract'lı işte: PR gövdesinde contract ID; commit gövdesinde de referans
  vermek izlenebilirliği artırır.
- "wip", "fix", "asdf" gibi mesajlar iz bırakmaz — ne değiştiğini söyle.

## İlgisiz işi karıştırmama
En sık ihlal: "madem buradayım, şunu da düzeltirim." Bir contract'ın diff'i
yalnız o contract'ın kapsamını içermeli.
- Yol üstünde bir sorun gördüysen: ayrı bir iş/issue olarak kaydet, bu PR'a
  sokma. Kapsam dışı path'e dokunmak risk sınıfını da bozar.
- Tek PR birden çok bağımsız işi taşıyorsa `revert` hepsini birden geri alır —
  rollback granülaritesini kaybedersin.

## PR yapısı ve kanıt izi
- Bir contract → bir PR. PR gövdesi: contract ID + kriter→test eşleme tablosu +
  koşulan komutlar ve sonuçları.
- Kanıt beyan değildir: CI `evidence.json` üretir (şema:
  `schemas/evidence.schema.json`). "Bitti" tek başına geçersiz.
- Test değiştirdiysen nedenini gövdeye yaz (bkz. `tdd-loop.md` — meşru sebepler).

## Push politikası hatırlatması
- Araştırma / ideation / mikro iş → push yok, yerel checkpoint yeter.
- Bütünlüklü değişiklik → tek PR; git işlemlerini agent yapar.
- Kritik/cloud iş → contract + PR + CI kanıtı.
- Deterministik kapı: `bin/hooks/pre-push` kernel doğrulaması geçmeden push
  edilemez (`bash bin/install-hooks.sh` ile kurulur; bilinçli atlama
  `git push --no-verify`). Auto-merge yalnız dar path-allowlist'li mekanik işte.
