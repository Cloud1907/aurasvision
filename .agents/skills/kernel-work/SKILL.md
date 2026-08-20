---
name: kernel-work
description: AurasAgents çekirdeğinin kendisini değiştirir — skill, capability profili, routing tablosu, issue form, evidence şeması, validate.py bekçileri, hook ve hafıza araçları. Sistemin kendi kurallarını/mekanizmalarını kurarken veya düzeltirken kullan; "skill ekle", "kernel'e kural koy", "bekçi testi yaz", "router'ı düzelt" tipi isteklerde tetiklenir. Uygulama kodu, UI veya iş mantığı işinde kullanma (bkz. implement-change).
---

# kernel-work

Amaç: sistemin kendi kuralları da kanıtlı değişsin. Bu skill, AurasAgents'ın
**meta katmanına** (skill/profil/routing/form/şema/hook/bekçi) dokunan işi
yönetir. Buradaki ölçüt tek cümle: **bağlam değil mekanizma**. Bir kural
`bin/validate.py` ile doğrulanamıyorsa henüz kural değildir, temennidir.

## Ne zaman geçerli
Değişen dosya şunlardan biriyse: `.agents/skills/**`,
`.agents/capability-profiles/**`, `.agents/routing.yml`,
`.github/ISSUE_TEMPLATE/**`, `.github/workflows/**`, `schemas/**`, `bin/**`,
`.claude/rules/**`, `.claude/settings.json`, `AGENTS.md`, `CLAUDE.md`.
DEĞİL: ürün/uygulama kodu (bkz. `implement-change`), salt keşif
(bkz. `research-with-evidence`), yeni projeyi bağlama (bkz. `auras`).

## İş akışı (checklist — kopyala ve işaretle)
- [ ] 1. Değişikliğin **mekanizma mı bağlam mı** olduğunu yaz. Mekanizmaysa
      hangi kapı uygular: `bin/validate.py` (kernel), hook (`.claude/settings.json`
      / `bin/hooks/pre-push`), CI job'ı, yoksa hangisi eklenecek?
- [ ] 2. Önce **bekçiyi** yaz: `bin/validate.py`'ye kuralı ihlal eden durumu
      yakalayan `check(...)` ekle veya `tests/` altına birim testi yaz.
- [ ] 3. `python3 bin/validate.py` koş ve **kırmızıyı gör** (yeni bekçi gerçekten
      ihlali yakalıyor mu?). Kırmızı görmeden ileri gitme.
- [ ] 4. Değişikliği uygula (skill/profil/routing/form/şema/hook).
- [ ] 5. `python3 bin/validate.py` yeşile dönmeli. Yeşil değilse mesaj bir sonraki
      okuyucuya ne yapacağını söylüyor mu — kontrol et.
- [ ] 6. Yan etki taraması: yeni skill eklediysen (a) `.agents/routing.yml`'de
      tetiklerini tanımla, (b) en az bir capability profiline ekle,
      (c) `## Eval` bölümü veya `eval/` klasörü koy — eval'siz skill yayınlanmaz.
- [ ] 7. Router'a dokunduysan gerçek istekle dene:
      `echo '{"prompt":"..."}' | python3 bin/route.py` — beklenen skill mi geldi?
- [ ] 8. Kanıt: validate çıktısı + koşulan komutlar; kararsa `docs/decisions/`
      altına ADR. AGENTS.md'ye kural ekliyorsan 200 satır sınırını aşma.

## Zorunlu ret listesi (bunları yaparsan dur ve yeniden düşün)
- **Bekçisiz kural.** AGENTS.md'ye cümle eklemek uygulama değildir. Kuralı
  makine doğrulamıyorsa bir sonraki oturumda buharlaşır.
- **Bekçiyi gevşetmek.** `validate.py` kırmızı verdiği için eşiği/koşulu
  yumuşatmak. Kuralı gerçekten değiştiriyorsan gerekçeyi commit mesajına yaz;
  yoksa kodu düzelt, bekçiyi değil.
- **Skill'i sessizce yayınlamak.** routing/profil/eval üçlüsü eksikse skill
  görünür olsa bile seçilmez — ölü ağırlık olur.
- **Kendi işini onaylamak.** Kernel değişikliği kendi risk sınıfını
  düşüremez; `deny` yüzeyine (secret dosyası, permission genişletme) dokunan
  değişiklik break-glass olmadan geçmez.
- **İlgisiz meta işi tek PR'da toplamak.** Kernel PR'ı bisect'in en çok
  gerektiği yerdir; tek amaç kuralı burada daha katıdır.

## High-signal gotcha'lar
- **Description tek seçim sinyalidir.** Skill'i çağıran şey gövdesi değil,
  frontmatter description'ıdır. Sağlanamayan ön-koşul yazarsan ("issue form'da
  EARS tanımlıysa") skill hiç seçilmez. Ne zaman kullanılacağını **somut tetik
  ifadeleriyle** yaz, ne zaman kullanılmayacağını da ekle.
- **`.claude/skills` bir symlink'tir** → `.agents/skills`. Yeni skill'i
  `.agents/skills/` altına yaz; symlink'i dosyayla ezme, `validate.py` yakalar.
- **Hook yazınca oturum onu görmez.** `.claude/settings.json` değişikliği
  çalışan oturumda gecikebilir; kullanıcının `/hooks` açması veya yeniden
  başlatması gerekebilir — bunu teslim notunda söyle.
- **Router asla bloklamaz.** `bin/route.py` hata/eksik bağımlılıkta sessizce
  `exit 0` döner. Bu bilinçli: yönlendirme yardımdır, kapı değildir. Router'a
  "engelle" davranışı eklemek istiyorsan bu ADR gerektirir.
- **PyYAML çıplak bağımlılıktır.** `validate.py` onsuz exit 2 verir; CI kurar,
  yerelde yoksa kurulum notu ver. Router'ı yaml'sız çalışmaya zorlama —
  sessiz çıkışı zaten kapsıyor.
- **CI ile yerel farkı.** Kurulu git kancası kontrolü `CI` env'inde atlanır;
  yeni "yerel makineye özel" bekçi eklerken aynı istisnayı düşün, yoksa CI
  kırılır.
- **AGENTS.md ≤200 satır** ve `CLAUDE.md` içinde `@AGENTS.md` importu zorunlu —
  ikisi de bekçili. Derinlik `docs/` ve `references/`'a iner, kanona değil.

## Eval
Bu skill'in işe yaradığını gösteren kabul senaryoları:

1. **Bekçisiz kural reddi.** Girdi: "AGENTS.md'ye 'PR başlığı contract ID
   içermeli' kuralını ekle." Beklenen: sadece metin eklemekle yetinilmez;
   ya `validate.py`/CI'da kontrol eklenir ya da kuralın uygulanamaz olduğu
   açıkça söylenir.
2. **Yeni skill bütünlüğü.** Girdi: "X için skill ekle." Beklenen çıktı
   `.agents/skills/x/SKILL.md` + routing.yml tetikleri + en az bir profile
   kayıt + eval; `python3 bin/validate.py` yeşil.
3. **Router regresyonu.** Girdi: "'login akışını güvenlik açısından incele'
   yanlış skill'e gidiyor." Beklenen: önce `tests/test_route.py`'ye kırmızı
   vaka, sonra routing.yml düzeltmesi, sonra yeşil.
4. **Negatif kontrol.** Girdi: "kullanıcı listesi endpoint'i ekle." Beklenen:
   bu skill DEVREYE GİRMEZ; `implement-change`'e bırakılır.
