# Deterministik kapılar — tam davranış ve ölçüm geçmişi

`AGENTS.md` her oturumda TAM yüklenir; bu dosya yalnız kernel işinde okunur.
Bu yüzden ayrım şudur: AGENTS.md kapının NE olduğunu söyler, burası NASIL
çalıştığını ve HANGİ ölçümün onu bu hâle getirdiğini anlatır. Bir kapının
davranışını değiştiriyorsan **önce burayı oku** — çoğu kural bir kez ölçülmüş
bir hatanın karşılığıdır ve gerekçesi silinirse aynı hata geri gelir.

## `bin/hooks/pre-push` — yerel push kapısı

Kernel doğrulaması geçmeden push edilemez. Kurulum: `bash bin/install-hooks.sh`;
bilinçli atlama: `git push --no-verify`.

Dört tarama sırayla koşar, **hepsi fail-closed** (tarayıcı dosyası yoksa push
engellenir; "yok" hâli "geçti" olamaz):

1. `validate.py` — kernel doğrulaması. Exit 2 "araç hatası"dır ve "kural
   ihlali" ile aynı şey değildir; kapı ikisini de bloklar ama **doğru olanı
   söyler**. 2026-08-07: Homebrew python3'ü 3.14'e taşıdı, PyYAML yoktu ve
   kapı "doğrulama BAŞARISIZ" dedi — oysa doğrulama hiç koşamadı.
2. `scan_secrets.py --git` — yalnız git-İZLENEN içerik. Çalışma ağacının
   tamamı taranırsa `.gitignore`'lu yerel `.env.local` push'u bloklar
   (OICommand'da yaşandı) ve kullanıcı `--no-verify` alışkanlığı edinir.
3. `scan_personal_data.py` — AYRI boyut. Sır tarayıcısı "bu değer bir anahtar
   mı", bu "bu dosya bir insan listesi mi" diye sorar. 4Flow'da (2026-08-07)
   20 kişilik `users_list.json` sır taramasından temiz geçmişti; kapıda bu
   boyut hiç yoktu. Eşik: ≥8 benzersiz e-posta ya da TC kimlik no. `AUTHORS`
   gibi tanımı gereği kişi listesi olan dosyalar muaftır.
4. `scan_gecmis.py --push-range` — index taramasının kör noktası (bağımsız
   inceleme, Codex 2026-08-12): commit A'da eklenip B'de silinen sır index'te
   GÖRÜNMEZ ama iki commit de uzak geçmişe gider ve oradan geri alınamaz.
   Yeni dalda (remote_sha 40 sıfır) aralık `--not --remotes` olur.

Yorumlayıcı seçimi çıkış koduna değil **çıktıya** bakar: `AURAS_PYTHON=/usr/bin/true`
ile sırlı push kapıyı sessizce geçmişti (2026-08-07) — `true` argümanları yok
sayıp 0 döner. Süreç kendi hakkında yalan söyleyebiliyorsa çıkış kodu kanıt
değildir.

Worktree'den push'ta git kancayı KENDİ ortamıyla çalıştırır; `GIT_DIR` mirası
alt süreçlere geçip doğrulayıcının geçici depolardaki `git` çağrılarını yanlış
depoya yöneltiyordu (PR #17). Çözüm: ortamı temizle, keşfi normal yoldan yap.

### Proje kapısı (opsiyonel uzantı)

`bin/hooks/proje-kapisi` varsa pre-push onu koşar. Projeye özel pazarlıksız
yasaklar (ör. "localStorage'da token yok") motor dosyasını çatallamadan burada
mekanizmaya bağlanır. Dosya motorun değil projenindir: `/auras` ezmez.
Çalıştırılabilir değilse push engellenir — sessiz atlama yok.
`</dev/null` ZORUNLU: git ref listesini pre-push'a stdin ile verir; proje
kapısı stdin'i okursa ref'e dayanan her politika sessizce işlevsizleşir
(denetim bulgusu 2026-08-06).

## `bin/kapi.py` — tur sonu kanıt kapısı (Stop hook)

Bu turda ne değiştiğine bakar ve kanıt arar: kaynak kod değiştiyse SON
düzenlemeden sonra koşmuş ve GEÇMİŞ bir test; risk yüzeyi değiştiyse güvenlik
incelemesi; görünür yüzey değiştiyse tıklama kanıtı.

Codex eleştirisi (2026-07-26) doğrudan buraya işlendi:
- "test dosyası değişti" test kanıtı DEĞİLDİR → testin koştuğu ve geçtiği aranır.
- "skill yüklendi" inceleme kanıtı DEĞİLDİR → asgari koşuldur, yeterli değil.
- Uyarmak yetmez, bloklamak gerekir; yoksa gerekçe yazdırmak bürokrasidir.

Bloklanan tur KAPANMAZ ('stop' yazılmaz). Yazılsaydı bir sonraki değerlendirme
boş pencere görür ve kanıtsız düzenlemeler sessizce geçmiş tura gömülürdü
(Codex ölçümü 2026-08-12).

## `bin/incele.py` — merge yolu (bağımsız inceleme)

Diff'i Codex'e (farklı satıcı, farklı kör nokta) inceletir, bulguyu P0/P1/P2
ayırır, PR'a karar biçiminde yorum düşer. **P0 varsa merge REDDEDİLİR; P1
bloklamaz, kararı insana taşır.** `deny` sınıfı her zaman insana gider.
`auto` risk + P0 yok + CI yeşil ise `--merge` ile birleştirir.

Fail-closed: çıktı ayrıştırılamazsa ENGEL — "okunamadı" ≠ "temiz". Biçim
bozuksa BİR KEZ daha sorulur; zaman aşımı/çağrı hatası tekrarlanmaz (bütçeyi
ikiye katlardı). Merge komutu incelenen head SHA'ya sabitlenir
(`--match-head-commit`): inceleme sonrası dala eklenen commit aynı hükmü
devralmaz.

Bütçe `INCELE_BUTCE` (varsayılan 900s) — diff boyutuna göre ölçeklenmez;
ölçüm boyutun sürücü olmadığını gösterdi (4.4KB→147s, 9.0KB→156s). Zaman
aşımında ilk bakılacak yer asılı `codex exec` sürecidir.

Diff inceleyiciye TALİMAT veriyorsa (enjeksiyon şüphesi) hüküm otomatik merge
için yeterli sayılmaz — ENGEL değil İNSAN, çünkü aracın kendi format dizesini
içeren meşru PR'lar da eşleşir ve ENGEL kalıcı öz-blok üretirdi.

### Döngünün sonu

Ölçüm 2026-08-12: 9 PR'da 62 tur, ~17 saat, 62 hükmün 2'si temiz — her tur
birikmiş diff'i yeniden inceliyordu. Üç çıkış:
- **artımlı diff** — son incelenen SHA'dan beri; P0 görülmüş PR'da KAPALI.
- **tur tavanı** — `INCELE_TUR_TAVANI` (varsayılan 3); aşılınca ENGEL İNSAN'a
  döner, asla `merge` üretmez, `deny`/kırmızı CI'ı gevşetmez.
- **dal kıpırdamadıysa yeniden inceleme yok.**

Sayaç PR yorumundaki markerdadır; kaybolursa sıfırlanır — fazladan inceleme,
açılan merge değil (`bin/tur.py`).

## `bin/kalite.py --check` — kod kalitesi ratchet'i (ADR-0004)

Dosya/fonksiyon boyutu, karmaşıklık ve borç işaretlerini deterministik sayar.
Mevcut borç kabul edilir, **büyümesi bloklanır**. Taban
`.agents/kalite-baseline.json` (proje sahibi; motor ezmez). Tabanı yükseltmek
bilinçli karardır, gerekçesi commit mesajına yazılır.

## Muafiyet sözleşmesi

`.agents/secret-allowlist.txt` — her satır `yol-deseni  # gerekçe`.
**Gerekçe zorunludur**; gerekçesiz satır kullanım hatasıdır (exit 2), "temiz"
değildir. Bastırılan bulgu çıktıda `muaf:` etiketiyle GÖRÜNÜR kalır — sessiz
susturma, kapının olduğu ama korumadığı hâldir. **Kapsam kapı bazındadır**:
işaretsiz satır yalnız secret kapısına uygulanır; başka kapı için gerekçe
`kapı: pii` (ya da `kapı: hepsi`) ile başlar.

## Test kapsamı daralmaz

`validate.py` testleri koşmadan önce KEŞFEDER; bir test dosyası import'ta
çökerse ya da keşif desenine uymuyorsa kesilir. Gerekçe: eksilen test kırmızı
testten tehlikelidir — kırmızı bağırır, yok olan test yalnız "Ran N"i sessizce
küçültür (ölçüm 2026-08-07: PyYAML'sız yorumlayıcıda 220 yerine 186).

Ortam bağımlılığı `tests/ortam.py` üstünden GÖRÜNÜR atlamaya çevrilir ve
`tests/test_ortam.py` eksik ortamı tek bir yüksek sesli hataya bağlar.
Paylaşılan yardımcıyı import eden test önce `tests/` dizinini `sys.path`'e
ekler — yoksa `python3 -m unittest tests.test_x` ModuleNotFoundError verir ve
okuyan "test bozuk" sanar (bekçi: `TekModulImportTest`).

Keşif kuralı METİN DESENİ değil `ast` + `tokenize` ile uygulanır: desen beş
turda beş kez sızdı (takma adlı taban, `async def test_*`, dış taban, fixture
string'i, `self` olmayan ilk parametre). Deseni büyütmek her seferinde yeni
kaçak bıraktı; çözüm dili kendi aracıyla okumaktı (`bin/kapsam_bekcisi.py`).

## Skill doğrulayıcı sözleşmesi (ADR-0003)

`check_*` / `scan_*` önekli skill script'i KAPI doğrulayıcısıdır ve en az bir
kapıya bağlanmak zorundadır (`validate.py` bağlanmamışı reddeder). Yazılmış
ama çağrılmayan doğrulayıcı = kural belgede var sistemde yok (2026-08-05
bulgusu: 3 doğrulayıcı yazılmış, 0'ı çağrılıyordu). Diğer adlar yardımcı
araçtır (ör. `contrast_check.py` — elle renk çifti alır, diff üstünde koşamaz).

## Kernel senkronu çift yönlüdür (ADR-0002)

`/auras` kanonikten projeye taşır; kurulum ÖNCE kaynağı upstream'e ileri
sarar, saramazsa ENGEL — eski çalışma ağacından kurmak bağlı repoya eski
motoru "güncel" damgasıyla yayardı (2026-08-15 ölçümü). Ezme kararı manifest'e
DEĞİL kanonik git geçmişine dayanır: manifest yanılabiliyordu (2026-08-05,
4cast'te projenin kendi içeriğini "el değmemiş" sanıp yerel düzeltmeyi ezmek
üzereydi). Güvenilir ayraç: hedefin içeriği kanonik geçmişte HİÇ görülmediyse
o yerel iştir. Ters yön `bin/auras_geri.py` (commit insanındır).

## Router (UserPromptSubmit) — kapı DEĞİL

Skill yönlendirmesini her isteğe enjekte eder. Proje hook'u
(`.claude/settings.json`, repoyla taşınır) + kullanıcı-global yedek
(`--global-fallback`, proje hook'u varsa susar). **Router asla bloklamaz**
(hatada sessiz exit 0) — kapı değil, pusuladır.

Enjeksiyon TALİMAT taşır, GEREKÇE taşımaz: maliyeti tur sayısıyla çarpılır.
Tavan bekçisi `tests/test_baglam_butcesi.py`; gerekçenin yeri AGENTS.md
"Davranış sözleşmesi" bölümüdür.

## `bin/kopru.py` — kanıt köprüsü (kotanın kapıyı öldürmesini engeller)

### Neyi çözer

Private repolarda ücretsiz Actions kotası (2000 dk/ay) bitince GitHub işleri
BAŞLATMAZ — job 3 saniyede ölür, log yoktur, yalnız şu anotasyon kalır:
*"The job was not started because recent account payments have failed or your
spending limit needs to be increased."* Sonuç: testler koşmaz, `evidence.json`
üretilmez, PR'lar kilitlenir. Kapı bozulmaz — **kapının beslendiği kaynak kesilir.**

Ölçüm 2026-08-16 (Cloud1907): 2000/2000 dakika 16 günde tükendi, borç YOK
(13.21 $ tüketim − 13.21 $ indirim = 0 $), abonelik yok. Aynı gün 4Flow'da 9 PR
bloke, `oicommand-connector` saatlik monitörü sürekli kırmızı.

### Nasıl çalışır

Tek anahtar: repo değişkeni `CI_RUNNER`. Workflow'lar
`runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}` yazar.

| Değişken | Nereye gider |
|---|---|
| set (`mac-bridge`) | yerel self-hosted runner |
| silinmiş | GitHub runner — kendiliğinden döner |

`|| 'ubuntu-latest'` yedeği ZORUNLUDUR: yalnız `${{ vars.CI_RUNNER }}` yazılırsa
değişken silindiğinde `runs-on` boş kalır ve iş sonsuza kadar `queued` bekler —
kırmızı değil, sessiz kilitlenme. `tests/test_kopru.py` bunu kilitler.

### Sert kapı: PUBLIC repo reddi

Public repoda self-hosted runner, **PR açabilen herkese** kurucunun makinesinde
kod çalıştırma hakkı verir. `kur()` `PRIVATE` dışındaki her görünürlüğü (ve
okunamayan görünürlüğü) reddeder — beyaz liste, fail-closed. Ret kurulumu
başlatmadan döner; "sonra temizleriz" yok.

### Ne KAYBEDİLİR — abartma yasağının buradaki karşılığı

AGENTS.md CI kapısını *"aynı doğrulamayı BAĞIMSIZ makinede tekrarlar"* diye
tanımlar. Köprü açıkken bu **yanlıştır**: kanıtı üreten makine ile kodu yazan
makine aynıdır, ortak güven kökü kullanıcının kendisidir — yani CI, yerel guard
setinin bir üyesi hâline gelir. Ek olarak runner kullanıcının yetkisiyle koşar;
`~/.npm`, `~/.nuget`, `~/Library/Caches` geliştirme ortamıyla ORTAKTIR. Hız
buradan gelir, "temiz makine" garantisi de burada kaybolur.

Bu yüzden ayrım kanıdın İÇİNE yazılır, dışına değil:

```json
"runner": { "environment": "self-hosted", "independent": false, "name": "mac-m4-bridge" }
```

`independent` yalnız `github-hosted`'da `true`'dur; yokluk ve bilinmeyen değer
`false` sayılır (fail-closed). Kanıt yine ÜRETİLİR — engellemek kullanıcıyı
kanıtsız çalışmaya iter, doğru davranış etiketlemektir. Bekçi:
`tests/test_kanit_kaynagi.py`.

### Ölçülmüş sınırlar

- Runner kaydı **repo seviyesindedir**. Kişisel hesapta organizasyon runner
  havuzu yoktur (`/orgs/<kullanıcı>/actions/runners` → 404), her repo kendi
  kaydını yapar. Aynı makine hepsine ev sahipliği yapabilir.
- **Artifact yükleme hâlâ GitHub kotasındadır** (500 MB). Köprü dakikayı
  kurtarır, depoyu kurtarmaz.
- **Actions cache servisi kotası bitmiş hesapta yanıt vermez.** `setup-node`'un
  POST `cache-save` adımı 15+ dakika asılı kalır ve iş `in_progress` takılır —
  testler geçtiği hâlde. Köprü modunda önbellek kapatılır (ölçüm 2026-08-16:
  önbelleksiz koşan 3 iş sorunsuz bitti, önbellekli 2 iş asıldı).
- Platforma bağlı adımlar elle kontrol edilir: sabitlenmiş ikili mimarisi
  (`gitleaks_*_linux_x64`), `playwright --with-deps` (yalnız Ubuntu), PEP 668
  (`pip install` Homebrew python3'te reddedilir).

### Geri dönüş

`python3 bin/kopru.py --kaldir SAHIP/REPO` — runner kayıtlarını ve `CI_RUNNER`
değişkenini siler. Köprünün tek meşrulaştırıcısı GEÇİCİ olmasıdır; kalıcılaşırsa
sistem kanıt katmanını sessizce kaybeder ve belge yanlış güven kaynağı olur.

## Bilinen açık

Private repo + Free plan'da dal koruması kapalıdır; koruma yerel kanca +
CI'dır. `kernel` required check yapılamadığı sürece **uzak bütünlük sınırı
yoktur** ve bu açık P1 olarak görünür kalır. Repo public olur ya da Pro
alınırsa ilk iş budur.

## `main` dal koruması — uzak bütünlük sınırı (2026-08-16)

`kernel` required · **PR zorunlu** (`required_approving_review_count: 0`) ·
`enforce_admins` açık · force-push ve dal silme kapalı. Payload: `README.md`.

**PR zorunluluğu opsiyonel değildir.** Yalnız required status check ile,
check'i ZATEN GEÇMİŞ bir SHA doğrudan `main`'e itilebilir: dalı it, CI koşsun,
sonra aynı commit'i main'e it. Bağımsız inceleme bunu P0 olarak yakaladı
(PR #52) ve ilk doğrulamam eksikti — yalnız check'i OLMAYAN bir commit'i
denemiş, "doğrudan push kimse için mümkün değil" diye yazmıştım. Kapının
gücünü olduğundan büyük yazmak, olmayan korumaya güvendirir.

**Kurulum ≠ yürürlük.** Ayar değişikliği saniyeler içinde yerleşir; kurulumdan
hemen sonraki push propagasyon penceresinden geçebilir. 2026-08-16'da bizzat
yaşandı: koruma doğruydu, push geçti. Doğrulama yerleştikten SONRA yapılır ve
reddin **iki gerekçesi** birden aranır:
`Changes must be made through a pull request.` **ve**
`Required status check "kernel" is expected.`
Tek gerekçe görülüyorsa sınır eksiktir.

## Ölçüm yokluğu ihlal değildir (2026-08-16)

Bir kapı, aracı KOŞAMADIĞINDA "kirli" değil "ölçülemedi" demek zorundadır.
Sahte kırmızı, sahte yeşil kadar zararlıdır: ikisi de kanıtı bozar.

- **CI test-önce:** `check_test_first` exit 2 → `skipped`, `failed` değil.
  İlk yazılan ders bu oldu (`evidence.yml:61`).
- **`incele.py`:** kota/kimlik/kurulum/ağ hatası → ENGEL DEĞİL İNSAN. Codex
  kotası bittiğinde ENGEL verip "çıktı ayrıştırılamadı" yazıyordu — oysa çıktı
  diye bir şey yoktu. Zaman aşımı bilinçle DIŞARIDA: araç koştu, iş bitmedi;
  o bir bütçe sorunudur. Biçim hatası da dışarıda: araç koştu, hükmü okunamadı
  — orada fail-closed doğrudur.
- **`anlik.py`:** commit grafiğinden gelen içerik ajanın düzenlemesi sayılmaz.
  PR birleştirilip `git pull` yapılınca tur kapısı "kaynak değişti ama test
  koşmadı" diye bloklamıştı; ajan o dosyaya hiç dokunmamıştı. Ayraç dar:
  yalnız HEAD oynadıysa VE dosya HEAD ile birebir aynıysa dışarıda kalır —
  ajan merge'in üstüne yazdıysa dosya kirlidir ve görünür kalır.

Gevşetme yalnız ETİKETTEDİR. `deny`, kırmızı CI ve kanıtsız merge hiçbir
durumda açılmaz; bunlar politika ve ölçümdür, hüküm değil.
