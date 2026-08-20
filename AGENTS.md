# AurasAgents — kanonik çalışma kuralları

Bu dosya motor-bağımsız tek doğruluk kaynağıdır (Claude, Codex, Copilot aynı
kuralları buradan okur). Motor-özel notlar adapter dosyalarındadır
(`CLAUDE.md` vb.). Çelişkide bu dosya kazanır.

## Kimlik ve amaç

AurasAgents, tek kişilik kurucu için kanıt-temelli agent çalışma sistemidir.
Tasarım sözleşmesi: `VIBE_CODING_TASARIM_TEMMUZ_2026.md` (Codex mutabakatlı).
Mimari kararlar: `docs/decisions/` (ADR).

## Kapsam sınırı — sistem neyi zorlamaz

Bu sistem **doğruluk ve güvenliği** deterministik olarak zorlar. Tasarım,
operasyon ve ürün ölçümü aşamalarında **kapı yoktur** — oralarda skill'ler
tavsiye verir, hiçbir mekanizma uyulduğunu denetlemez. "Kanıt > beyan" ilkesi
yalnız kapı olan aşamalarda geçerlidir.

Aşama aşama ölçülmüş kapsam: `docs/yasam-dongusu-kapsami.md`. Bir aşamaya kapı
eklenirse o belge güncellenir; güncellenmemesi belgeyi yanlış-güven kaynağına
çevirir.

## Çalışma ilkeleri

1. Kanıt > beyan. "Bitti" demek kanıt değildir; kanıt CI'dan `evidence.json`
   olarak gelir. LLM incelemeleri (Codex review, /code-review) risk sinyalidir,
   kanıt değildir.
2. Tek yazar. Aynı iş roller arasında bölünmez; paralellik yalnız bağımsız
   işlerde (ayrı worktree/session).
3. Spec-anchored. Kod ground-truth'tur; sözleşme GitHub Issue Form'dur
   (hedef + EARS kabul kriterleri + görev sınıfı + risk). Diff tek cümleyle
   tarif edilebiliyorsa form ve plan atlanır; PR `micro` etiketi alır.
4. Plan mode yalnız belirsiz kapsam veya yüksek riskte zorunludur.
5. Agent kendi işini onaylayamaz, kendi risk/profil sınıfını yükseltemez.

## Hafıza otoritesi

Hiyerarşi (çelişkide üstteki kazanır):

1. `AGENTS.md` + `docs/decisions/` (kanonik, reviewed)
2. Run/PR kayıtları
3. Auto-memory (disposable yerel önbellek — hiçbir iş ona bağımlı olamaz)

Kalıcılaştırma yalnız reviewed PR ile olur. Secret, kullanıcı verisi ve
doğrulanmamış çıkarım kalıcı hafızaya giremez. 90 gün dokunulmamış kayıt
gözden geçirilir. Bakım robotu: `python3 bin/memory_hygiene.py` bayat/
kaynaksız/çelişen kaydı işaretler (silmez — emeklilik reviewed PR ile).

## Risk politikası — üç deterministik sonuç

Risk iki kez hesaplanır: ön sınıf issue form'dan, nihai sınıf diff'ten.
Eskalasyon yalnız yukarı olur. `deny` her zaman önceliklidir.

| Sonuç | Tetik (path/aksiyon kuralı) | Davranış |
|---|---|---|
| auto | docs/**, tests/**, *.md, küçük refactor (izinli path içinde) | Uçtan uca; CI yeşilse merge'e hazır |
| approval | uygulama kodu, bağımlılık değişikliği, auth/ödeme komşusu path; bu projede: `src/kimlik.py` (RBAC/oturum), `src/face.py` (biyometrik/KVKK), `db/schema.sql` | Plan onayı + insan merge |
| deny | secret/credential dosyaları, veri silme, prod migration, permission genişletme; bu projede: `.env`, `ROLLER` rol matrisi genişletme, `evidence.keep_days` retention kısaltma/kanıt silme, kamera RTSP kimlik bilgisi | Varsayılan red; break-glass süreli + gerekçeli + kayıtlı |

## Push politikası

- Araştırma / ideation / mikro iş → push yok (yerel checkpoint yeter).
- Bütünlüklü değişiklik → tek PR; git işlemlerini agent yapar.
- Kritik veya cloud'da süren iş → contract + PR + CI kanıtı.
- Auto-merge yalnız dar path-allowlist'li mekanik işlerde.
- İlgisiz işleri tek PR'da toplama (bisect/rollback/kanıt izini bozar).

## Skill ve capability mekanizması

- Kanonik skill kaynağı: `.agents/skills/` (Agent Skills açık standardı).
- Görev sınıfı (`code-change` | `research` | `incident` | `design`) →
  `.agents/capability-profiles/<sınıf>.yml` profili → izinli skill/araç/ağ
  kümesi. Agent seçimini yalnız bu küme içinde yapar ve seçim loglanır.
- Skill seçimi takdire bırakılmaz: `.agents/routing.yml` tabloya bağlar,
  `bin/route.py` her istekte (UserPromptSubmit hook'u) görev sınıfı + zorunlu
  skill üretir. Yönlendirilen skill yüklenmeden işe başlanmaz; yanlış
  yönlendirme sessizce atlanmaz, gerekçelendirilip kullanıcıya söylenir.
- **MCP sunucuları skill'lerle AYNI yönetime tabidir** (2026-08-16): kayıt
  `.agents/mcp.yml`, sınır profil `mcp:` alanı, üretici `bin/yetki.py`,
  bekçi `validate.py` + `tests/test_mcp_kaydi.py`. Kural: **kayıtsız sunucu
  yapılandırılamaz, profilsiz sunucu kayıtta duramaz.** Kayıt her sunucunun
  ağ erişimini beyan eder — profil `network` alanının MCP ayağı budur.
  Sınırı: MCP yapılandırması OTURUM genelindedir, tur başına zorlanamaz.
- Yeni skill kuralı: aynı iş tipi üçüncü kez elle tarif ediliyorsa skill'dir.
  Yayın koşulu üçlüdür: eval + routing.yml tetiği + en az bir profil kaydı.
  Kasten yönlendirilmeyen skill `routing.yml` `not_routed`'a gerekçesiyle yazılır.

## Deterministik kapılar

Kapıların NE olduğu burada; NASIL çalıştığı ve hangi ölçümün onu bu hâle
getirdiği `.agents/skills/kernel-work/references/kapilar.md` dosyasında
(bu dosya her oturumda tam yüklenir, o yalnız kernel işinde okunur).

| Kapı | Ne yapar | Bilinen sınırı |
|---|---|---|
| `bin/hooks/pre-push` | kernel doğrulama + sır/PII/geçmiş taraması + proje kapısı; hepsi fail-closed | `git push --no-verify` |
| CI `evidence` job | aynı doğrulamayı bağımsız makinede tekrarlar; `main`'de **zorunlu** check — evidence.yml'ın tek job'ı `kernel` (ölçüm 2026-08-16, doğrula: `gh api .../branches/main/protection`) | köprü açıksa (`CI_RUNNER`, `bin/kopru.py`) **self-hosted runner'da bağımsızlık YOK** |
| `bin/kapi.py` (Stop) | kanıtsız tur kapanmaz: test / inceleme / tıklama | olay kaydı silinirse susar |
| `bin/incele.py` | merge yolu: P0 → RED, P1/araç-yok → insan, `deny` → insan | `gh pr merge` doğrudan |
| `bin/kalite.py --check` | borç büyümesini bloklar (ADR-0004) | taban bilinçle yükseltilir |
| UserPromptSubmit router | skill yönlendirmesi enjekte eder | **kapı değil, pusula** — asla bloklamaz |

- **Muafiyet gerekçelidir.** `.agents/secret-allowlist.txt`: her satır
  `yol-deseni  # gerekçe`. Gerekçesiz satır kullanım hatasıdır (exit 2),
  "temiz" değildir; bastırılan bulgu `muaf:` etiketiyle GÖRÜNÜR kalır.
  Kapsam kapı bazındadır (`kapı: pii` / `kapı: hepsi`).
- **Test kapsamı daralmaz.** Keşfe girmeyen test kırmızı testten tehlikelidir:
  kırmızı bağırır, yok olan test yalnız "Ran N"i sessizce küçültür.
- **Skill doğrulayıcı sözleşmesi (ADR-0003).** `check_*` / `scan_*` önekli
  script en az bir kapıya bağlanmak zorundadır; bağlanmamışı `validate.py`
  reddeder — yazılmış ama çağrılmayan doğrulayıcı, kuralı belgede bırakır.
- **Kernel senkronu çift yönlüdür (ADR-0002).** Kurulum önce kaynağı ileri
  sarar; ezme kararı manifest'e değil kanonik git geçmişine dayanır. Ters
  yön `bin/auras_geri.py`.
- **Uzak bütünlük sınırı KURULDU (2026-08-16).** `main` dal koruması altında:
  `kernel` required, **PR zorunlu** (`required_approving_review_count: 0`),
  `enforce_admins` açık, force-push ve dal silme kapalı. Bu, sistemdeki TEK
  kapıdır ki agent'ın yazamadığı bir yerde çalışır. Bedeli: `main`'e doğrudan
  push kimse için mümkün değil (admin dâhil). Break-glass = korumayı bilinçle
  kapatmak; GitHub audit log'a yazar (süreli + gerekçeli + kayıtlı).
  PR zorunluluğu OPSİYONEL DEĞİLDİR ve doğrulama kurulumdan SONRA yapılır —
  ikisinin de ölçülmüş gerekçesi `references/kapilar.md`'de, payload
  `README.md`'de.

## Kapıların gerçek sınıfı

Bir kapının gücünü olduğundan büyük yazmak, olmayan korumaya güvendirir.
Bu tablo her kapının NE OLDUĞUNU söyler; abartma yasaktır.

| Kapı | Sınıf | Neyi engelleyemez |
|---|---|---|
| `permissions.deny` (`bin/yetki.py`) | motor-uygulamalı izin | Yalnız MUTLAK yasakları kapatır (secret/credential, yetki genişletme, yıkıcı komut). Sınıf başına sınır uygulayamaz (izinler oturum genelindedir); kabuk üzerinden yazımı engellemez |
| `bin/kapi.py` (tur/Stop) | yerel workflow guard | Agent olay kaydını silebilir/yazabilir; kayıt yoksa sessizce geçer. Aynı borçla ikinci kapanışı BLOKLAMAZ — yalnız "⚠️ kanıt borcuyla kapandı" izi bırakır (tek blok + görünür feragat) |
| `bin/hooks/pre-push` | yerel workflow guard | `git push --no-verify` ile atlanır; kanca kurulu değilse hiç koşmaz |
| `bin/incele.py` (merge) | süreç kuralı | `gh pr merge` ile doğrudan birleştirmeyi engellemez |
| CI `evidence` job'ı | bağımsız makine kanıtı | Kanıtın DOĞRU olduğunu değil, üretildiğini gösterir |
| `main` dal koruması | **bütünlük sınırı** — tek gerçek olan | Repo yöneticisi korumayı kapatabilir (audit log'a yazılır). Kapatılırsa sistem yeniden yalnız yerel guard setidir |

Yerel kapılar **güvenlik sınırı değildir**: hepsi agent'ın yazabildiği aynı
dosya sisteminde, aynı kullanıcı yetkisiyle çalışır — ortak güven kökü
agent'ın kendisidir. İşlevleri hatayı ucuzken yakalamaktır, kötü niyeti
durdurmak değil.

Gerçek bütünlük sınırı yalnız remote'ta, agent'ın değiştiremediği zorunlu
check ile kurulur — ve **2026-08-16'da kuruldu**. Artık sistem "yerel
workflow guard seti" DEĞİL; yerel guard'lar + bir bütünlük sınırıdır. Ayrım
korunmalı: yerel kapılar hâlâ atlanabilir ve hâlâ öyle adlandırılır; yalnız
`main`'e giden yol kapanmıştır. Koruma kapatılırsa bu paragraf da eski hâline
döner — abartma yasağı sınırın varlığına değil, DOĞRU adlandırılmasına
bağlıdır.

**Ölçüm yokluğu ihlal değildir.** Kapı, aracı KOŞAMADIĞINDA "kirli" değil
"ölçülemedi" der — sahte kırmızı, sahte yeşil kadar zararlıdır. Uygulandığı
yerler: CI test-önce (exit 2 → `skipped`), `incele.py` (kota/kimlik/ağ →
İNSAN), `anlik.py` (commit grafiğinden gelen içerik ajanın işi sayılmaz).
Gevşetme yalnız ETİKETTEDİR: `deny`, kırmızı CI ve kanıtsız merge açılmaz.

Sonuç: kapı çıktısı "doğrulandı" değil "bu turda şu kanıt görüldü" demektir.
Kanıtın kaynağı kayda yazılır (`src`: `exit` = gerçek çıkış kodu, `event` =
hook olay türü). Çıkış kodu maskeleyen komut (`pytest || true`,
`pytest | tail`) "geçti" sayılmaz — kabuğun kodu testin kodu değildir.

## Kimlik ve erişim

- GitHub işleri `gh` CLI ile; kimlik kısa ömürlü GitHub App installation
  token (kalıcı geniş PAT yasak).
- Ağ erişimi profil allowlist'ine tabidir; varsayılan kapalıdır.
- Production secret agent ortamına girmez.

## Davranış sözleşmesi

Router her turda kısa TALİMAT enjekte eder; GEREKÇE burada durur, çünkü
enjeksiyonun maliyeti tur sayısıyla çarpılır ama bu dosya oturum başına bir
kez yüklenir (ölçüm 2026-08-15: sabit iskele 1732 → 890 karakter, tam
enjeksiyon ~%45 küçüldü). Tavan bekçisi: `tests/test_baglam_butcesi.py`.

- **Görünürlük.** Kullanıcı yazışmadan ne olduğunu anlamalı: hangi skill
  yüklendi, iş kimin, ne yapıldı. Görünmeyen süreç denetlenemez — bu yüzden
  başlık temenni değil her turda dayatılan biçimdir.
- **İtiraz yükümlülüğü.** İsteğin yanlış, eksik ya da riskli olduğunu
  düşünüyorsan uygulamadan ÖNCE tek paragraf itiraz yaz: neyi, neden,
  alternatif ne. Sessiz uyum kabul edilmez; itirazdan sonra kullanıcı ısrar
  ederse karar uygulanır ve bu belirtilir. Router bu satırı yalnız `auto`
  dışı turlarda enjekte eder — itiraz edilecek mutasyon yokken her sohbet
  turuna ödeme yapmak kuralı güçlendirmez, bağlamı pahalılaştırır.
- **Sahiplik tektir.** Disiplin bir ETİKETTİR; derinlik rol dosyasında değil
  yüklenen SKILL'de yaşar. Aynı iş roller arasında bölünmez. Ayrı ajan yalnız
  iki durumda: bağımsız doğrulama ve izole araştırma.
- **Karşılama.** Yeni iş isteğinde üç satır (anladığım · geçmiş · veriyorum);
  mikro işte ve aynı işin takip turunda atlanır — yeni konu takip turu
  değildir. Derinlik: `.agents/skills/aurasprime/SKILL.md`.

## Konvansiyonlar

- Dil: tr-TR (kod tanımlayıcıları İngilizce).
- Commit: küçük, tek amaçlı, açıklayıcı mesaj; contract'lı işte PR
  gövdesinde contract ID.
- Kanıt: her contract'lı PR'da CI `evidence.json` üretir
  (şema: `schemas/evidence.schema.json`).
