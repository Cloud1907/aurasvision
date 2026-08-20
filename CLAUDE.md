@AGENTS.md

# Claude adapter notları

- Yukarıdaki AGENTS.md kanonik kaynaktır; bu dosya yalnız Claude-özel ayarları taşır.
- **Proje:** görüntü analitiği platformu — kişi sayma, ALPR, yüz+anonim
  demografi, PTZ kontrolü, ONVIF kamera keşfi, NVDEC GPU pipeline (ADR-0003),
  RBAC (`src/kimlik.py`: yönetici/operator/izleyici, imzalı oturum çerezi),
  semantik görüntü araması (SigLIP), kanıt karesi saklama (KVKK retention),
  Windows/systemd installer. Python 3.11, FastAPI+SPA, Ultralytics YOLO,
  InsightFace, fast-alpr; SQLite veya Postgres/TimescaleDB+pgvector
  (`DATABASE_URL`), Redis, go2rtc. Modüller: `src/{cli,server,worker,ingestor,
  count,face,plate,ptz,recorder,discovery,zones,kimlik,evidence,exporter,
  arama,bildirim,olay,akis,gpu_engine}.py`. Detay: [README.md](README.md),
  [docs/KURULUM.md](docs/KURULUM.md), `docs/rbac-tasarim.md`, mimari kararlar
  `.agent-ofis/decisions/`, KVKK: `.agent-ofis/docs/kvkk-notlari.md`.
  Riskli path'ler (AGENTS.md risk tablosunu besler): `src/kimlik.py` (RBAC/
  oturum imzası), `src/face.py`+`watch_faces` (biyometrik/KVKK), `db/schema.sql`
  (prod migration), `.env`/`AURAS_TOKEN`/`DATABASE_URL`/`REDIS_URL`,
  `evidence.keep_days` retention (kanıt karesi erken silme = deny).
- Kesin yasaklar `.claude/settings.json` `permissions.deny` ile uygulanır;
  kaynak `.agents/capability-profiles/` ve üretici `bin/yetki.py --uygula`
  (drift bekçisi: `validate.py`). NE UYGULANIR: secret/credential okuma-yazma,
  yetki genişletme yüzeyi, bilinen yıkıcı kabuk komutları. NE UYGULANMAZ:
  sınıf başına değişen sınırlar (izinler oturum genelindedir, tur başına
  değişmez) ve kabuk üzerinden yazım — onun karşılığı önleme değil TESPİT'tir
  (`bin/anlik.py`, tur kapısı). Profildeki `filesystem`/`network` alanları bu
  ikinci grup için hâlâ BEYANDIR; güvenlik sınırı sayma.
- Kernel doğrulama: `python3 bin/validate.py` (her değişiklikte koş).
- Proje testi: `source .venv/bin/activate && pytest -q` (model/GPU gerekmez).
- Proje build: `find src -name '*.py' -print0 | xargs -0 python -m py_compile`.
- Proje kurulumu: `./setup.sh` (`--systemd` sahada, `--no-docker` altyapı
  başka makinede, `--check` yalnız denetler) veya elle `python3.11 -m venv
  .venv && pip install -r requirements.txt`.
- Proje çalıştırma: `python -m src.cli count|plate|face|analyze --source ...`
  (tek seferlik) veya `python -m src.server` + `python -m src.worker` +
  `python -m src.ingestor` (sürekli — `docker compose up -d db redis go2rtc`
  altyapısı gerekir).
- Lint/format aracı henüz yok; ekleme kararı verilene kadar mevcut stile
  (tip anotasyonu, docstring, tr-TR yorum) uy.
- CI: kernel `evidence.yml` (bu kurulumla eklendi) yanında projenin kendi
  eski Agent Ofis CI'ı da çalışır — `required-checks.yml` (`enforce` job),
  `qa-api-contract.yml`, `qa-web-e2e.yml`, `windows-installer.yml`; ikisi de
  korunur, birbirini ezmez.
- Kanıt üretimi lokal deneme: `python3 bin/make_evidence.py --out /tmp/evidence.json`
- Skill'ler `.claude/skills` üzerinden görünür (`.agents/skills`'e symlink);
  yeni skill eklerken symlink'i bozma, `.agents/skills/` altına yaz.
- Skill yönlendirmesi iki katmanlıdır:
  - Proje: `.claude/settings.json` UserPromptSubmit hook'u projenin
    `bin/route.py`'sini çalıştırır (repoyla taşınır, `auras-init.sh` kurar).
  - Global yedek: `~/.claude/settings.json` kanonik route.py'yi
    `--global-fallback` ile çağırır — bağlı olmayan projelerde de yönlendirir,
    projenin kendi hook'u varsa sessizce çekilir (çift yönlendirme olmaz).
  Tablo sırası: proje `.agents/routing.yml` → kanonik AurasAgents tablosu.
  Elle deneme: `echo '{"prompt":"..."}' | python3 bin/route.py`
  Hook yeni eklendiyse çalışan oturum görmeyebilir — `/hooks` aç ya da
  Claude Code'u yeniden başlat.
