---
name: auras
description: Bir projeyi AurasAgents çalışma sistemine bağlar — AGENTS.md kuralları, capability profilleri, iş sözleşmesi formu, CI kanıt üretimi, push kapısı ve Codex risk sinyali kurulur. Kullanıcı "/auras", "bu projeyi bağla", "sisteme al", "kur" dediğinde veya yeni/boş bir projede çalışma sistemi istendiğinde kullan. Zaten bağlı projede motor dosyalarını GÜNCELLER (elle değiştirilmiş dosyayı ezmez, bildirir). Günlük geliştirme işinde kullanma.
---

# auras — projeyi sisteme bağla

Çekirdek kaynak: `~/Developer/GitHub/AurasAgents` (kanonik şablon).

## Prosedür

1. Hedef klasörü doğrula: kullanıcının bulunduğu proje klasörü. Kaynak reponun
   kendisiyse dur — orada zaten kurulu.
2. Kurulum/güncelleme motorunu çalıştır:
   `bash ~/Developer/GitHub/AurasAgents/bin/auras-init.sh`
   - **Kaynak tazeliği önce ölçülür**: kurucu kanonik ağacı upstream'e ileri
     sarar; saramazsa (yerel commit / kirli ağaç) DURUR. Engelde kanonik
     repoda durumu çöz (pull / rebase / stash) ve tekrar koş.
     `AURAS_ESKI_MOTOR=1` ile atlamak bağlı repoya ESKİ motoru yaymaktır —
     gerekçesiz kullanma, kullandıysan kullanıcıya söyle.
   - Çıktıdaki `uyarı: ... kirli` satırı, kurulan içeriğin hiçbir commit'e
     ait olmadığını söyler; kullanıcıya bildir.
   İki ayrı davranış vardır:
   - **Proje dosyaları** (AGENTS.md, CLAUDE.md, .gitignore): bir kez yazılır,
     ASLA ezilmez.
   - **Motor dosyaları** (bin/*, .agents/skills, profiller, routing.yml,
     workflow, şema, tests): her koşumda güncellenir — ama kullanıcı elle
     değiştirdiyse korunur ve `KORUNDU` diye raporlanır. Ezme kararının
     OTORİTESİ kanonik **git geçmişidir**, manifest DEĞİL (ADR-0002):
     hedefin içeriği kanonik geçmişte hiç görülmediyse o yerel iştir.
     Manifest yalnız hızlandırıcı bir önbellektir ve yanılabilir —
     2026-08-05'te 4cast'te projenin kendi içeriğini "el değmemiş" sanıp
     yerel düzeltmeyi ezmek üzereydi.
   - Hook'lar kaynak `.claude/settings.json`'dan birleştirilir; kernel yeni
     hook eklediğinde bağlı projeler bunu `/auras` ile alır.
   Kapanışta `KORUNDU` satırlarını kullanıcıya MUTLAKA söyle — sessiz geçme.
3. Projeyi tanı ve `AGENTS.md`'yi ona göre uyarla — şablonu olduğu gibi bırakma:
   - Dil/framework, test/lint/build komutları
   - Riskli path'ler (auth, ödeme, migration, secret) → risk tablosunun
     `deny` ve `approval` satırlarını bu projeye göre doldur
   - Repoya özgü konvansiyonlar ve tuzaklar
   `CLAUDE.md`'ye projenin gerçek komutlarını yaz.
4. `.github/workflows/evidence.yml` içindeki check listesine projenin gerçek
   komutlarını ekle (typecheck/lint/test/build). Var olan CI'ı silme, yanına ekle.
5. `python3 bin/validate.py` koş — geçmeden bitmiş sayma.
6. GitHub bağlantısı: uzak repo yoksa kullanıcıya sor (private öner), onay
   alırsan `gh repo create <ad> --private --source=. --remote=origin --push`.
   Onay almadan repo oluşturma veya push etme.
7. Kapanışta kullanıcıya sade özet ver: ne kuruldu, CI yeşil mi, sırada ne var.

## Gotcha'lar

- Boş projede bile AGENTS.md'yi genel bırakma; genel kural = uygulanmayan kural.
- Mevcut projelerde eski yapılandırma varsa (ör. Agent Ofis `projects/*.yml`)
  bilgiyi mekanizmaya taşı: forbidden→hook/deny kuralı, conventions→AGENTS.md,
  routing→capability profili. Düz metne kopyalayıp geçme.
- Kurulum tek iştir; proje koduna davranış değişikliği karıştırma.
- Private repo + Free plan'da GitHub dal koruması çalışmaz; koruma yerel
  pre-push kancası + CI'dır. Bunu kullanıcıya söyle, sessiz geçme.

## Referanslar

- `references/onboarding-checklist.md` — kurulum sonrası projeyi TANIMA ve
  `AGENTS.md`'yi ona uyarlama prosedürü (dil/framework, komutlar, izinli
  path'ler, pazarlıksız yasaklar). 2026-08-16'da ayrı bir skill'di
  (`project-onboarding`); iki skill tek işi yapıyordu ve hangisinin otorite
  olduğu her okumada yeniden kararlaştırılıyordu. Prosedür korundu, ikinci
  giriş noktası kaldırıldı.

## Eval

Kurulum sonrası ölçüt: `python3 bin/validate.py` geçiyor, ilk push'ta CI
`evidence.json` üretiyor ve kullanıcı hiçbir git komutu yazmadan iş verebiliyor.
