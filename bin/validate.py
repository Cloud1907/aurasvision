#!/usr/bin/env python3
"""Kernel conformance testleri — skill, profil, form, şema ve evidence tutarlılığı.

Koşum: python3 bin/validate.py   (exit 0 = geçti)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("HATA: PyYAML gerekli (pip install pyyaml)")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERRORS = []


def err(msg):
    ERRORS.append(msg)


def check(cond, msg):
    if not cond:
        err(msg)


# CI/kanıt sözleşmesinin doğrulayıcıları ayrı modülde (bin/dogrula_ci.py):
# ayrı değişme sebebi + validate.py'yi kalite ratchet'inin altında tutar.
sys.path.insert(0, os.path.join(ROOT, "bin"))
import dogrula_ci  # noqa: E402

dogrula_ci.kur(check)
test_workflow = dogrula_ci.test_workflow
test_evidence_roundtrip = dogrula_ci.test_evidence_roundtrip
# Görev sınıfı sözleşmesi de ayrı modülde (bin/dogrula_sema.py): sınıf
# listesinin TEK tanımı orada — dört kopya sürüklenme üretiyordu.
import dogrula_sema  # noqa: E402
from dogrula_sema import GOREV_SINIFLARI  # noqa: E402

dogrula_sema.kur(check)
test_profiles = dogrula_sema.test_profiles
test_issue_form = dogrula_sema.test_issue_form


def _router_katmani():
    """route.py + enjekte.py birleşik kaynağı — bekçiler DOSYAYA bakmasın.

    Karşılama hafızası çağrısı 2026-08-16'da `bin/enjekte.py`'ye taşındı
    (route.py 406 satıra çıkıp ratchet'i delince enjeksiyon metni ayrıldı) ve
    `"karsilama_kayitlari" in route.py` diyen bekçi anında kırmızı yandı —
    oysa davranış hiç değişmemişti. Mekanizmanın hangi modülde durduğu bir
    TASARIM kararıdır; kural ise "hafıza gerçekten okunuyor mu". Bekçi
    kuralı ölçmeli, dosya yerleşimini değil.

    Eksik dosya boş dize verir: bekçi ölçemediği şeyde çökmez.
    """
    metin = []
    for ad in ("route.py", "enjekte.py"):
        try:
            with open(os.path.join(ROOT, "bin", ad), encoding="utf-8") as fh:
                metin.append(fh.read())
        except OSError:
            continue
    return "".join(metin)


def _bin_modul(ad):
    """bin/<ad>.py'yi kütüphane olarak yükler (yoksa None)."""
    try:
        import importlib.util
        yol = os.path.join(ROOT, "bin", f"{ad}.py")
        spec = importlib.util.spec_from_file_location(f"_{ad}", yol)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (OSError, ImportError, AttributeError):
        return None


def _kernel_dosyalari():
    """Motor listesinin tek tanımını yükler (yoksa None)."""
    return _bin_modul("kernel_dosyalari")


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    return yaml.safe_load(m.group(1))


def test_skills():
    skills_dir = os.path.join(ROOT, ".agents", "skills")
    names = []
    for d in sorted(os.listdir(skills_dir)):
        full = os.path.join(skills_dir, d)
        if not os.path.isdir(full):
            continue
        md = os.path.join(full, "SKILL.md")
        check(os.path.isfile(md), f"skill '{d}': SKILL.md yok")
        if not os.path.isfile(md):
            continue
        fm = frontmatter(md)
        check(fm is not None, f"skill '{d}': frontmatter yok/bozuk")
        if fm:
            check(fm.get("name") == d,
                  f"skill '{d}': frontmatter name '{fm.get('name')}' dizinle uyuşmuyor")
            desc = fm.get("description", "")
            check(len(desc) >= 40,
                  f"skill '{d}': description çok kısa (seçim sinyali zayıf)")
            check("kullan" in desc.lower(),
                  f"skill '{d}': description ne zaman kullanılacağını söylemiyor")
        body = open(md, encoding="utf-8").read()
        low = body.lower()
        # SKILL.md < 500 satır (Anthropic best-practice; derinlik references/'a iner)
        check(len(body.splitlines()) < 500,
              f"skill '{d}': SKILL.md 500 satırı aştı — derinliği references/'a taşı")
        # İş akışı bölümü: eski 'Prosedür' veya yeni 'İş akışı'
        check("prosedür" in low or "akış" in low,
              f"skill '{d}': iş akışı/prosedür bölümü yok")
        # Gotcha içeriği (tuzak bilgisi) — bölüm adı serbest
        check("gotcha" in low or "tuzak" in low,
              f"skill '{d}': gotcha/tuzak bölümü yok (en yüksek sinyalli içerik)")
        # Eval: '## Eval' bölümü VEYA eval/ klasörü
        has_eval = ("## eval" in low or
                    os.path.isdir(os.path.join(full, "eval")))
        check(has_eval, f"skill '{d}': eval yok (## Eval bölümü ya da eval/ klasörü)")
        # Derin skill sinyali (uyarı değil, bilgi): references/ veya scripts/
        names.append(d)
    check(len(names) >= 4, f"en az 4 çekirdek skill bekleniyor, {len(names)} var")
    return set(names)


def test_kapsam_siniri_yazili():
    """Sistem neyi zorlamadığını AÇIKÇA söylüyor mu.

    Kapsam sınırını gizleyen sistem, kapsamı dar olandan tehlikelidir:
    kullanıcı korunduğunu sanır. AGENTS.md "kanıt > beyan" diyor ama bu
    yalnız doğruluk ve güvenlikte geçerli — tasarım (3), operasyon (8) ve
    ölçme (9) aşamalarında kapı YOK.

    Bekçinin SINIRI: belgenin varlığını ve referansını doğrular, içeriğinin
    güncelliğini doğrulayamaz. Belge bunu kendisi de yazıyor.
    """
    kd = _kernel_dosyalari()
    belge = (kd.yol_coz(ROOT, "docs/yasam-dongusu-kapsami.md") if kd
             else os.path.join(ROOT, "docs", "yasam-dongusu-kapsami.md"))
    check(belge is not None and os.path.isfile(belge),
          "docs/yasam-dongusu-kapsami.md yok — sistemin neyi zorlamadığı "
          "yazılı değil; kullanıcı korunduğunu sanır")
    agents = os.path.join(ROOT, "AGENTS.md")
    if os.path.isfile(agents):
        with open(agents, encoding="utf-8") as fh:
            metin = fh.read()
        check("yasam-dongusu-kapsami" in metin,
              "AGENTS.md kapsam haritasına referans vermiyor — belge yetim "
              "kalır ve okunmaz")


def test_bagimsiz_inceleme():
    """Merge öncesi bağımsız inceleme mekanizması var ve belgeli mi.

    2026-08-07 ölçümü: `bin/codex-review.sh` kurulu ve `codex` CLI çalışır
    durumdaydı ama HİÇBİR yerden çağrılmıyordu — açılan 3 PR'da 0 inceleme
    yorumu. Kullanıcı da PR'ları okumadığını söyledi. Yani "insan merge"
    satırı en güçlü duran ama fiilen boş çalışan halkaydı: ne insan ne
    makine incelemesi vardı.

    `bin/incele.py` merge'ün tek yoludur; bekçi varlığını ve AGENTS.md'de
    belgelendiğini zorlar. Bekçinin SINIRI: aracın çağrıldığını
    doğrulayamaz — merge komutunu doğrudan `gh` ile atmak hâlâ mümkün.
    Bu bir süreç kuralıdır, mekanik kilit değil; öyleymiş gibi sunulmuyor.
    """
    arac = os.path.join(ROOT, "bin", "incele.py")
    check(os.path.isfile(arac),
          "bin/incele.py yok — merge öncesi bağımsız inceleme mekanizması "
          "yok; agent kendi işini onaylıyor demektir")
    kd = _kernel_dosyalari()
    if kd is not None and os.path.isfile(arac):
        check("bin/incele.py" in kd.MOTOR,
              "incele.py motor listesinde değil — bağlı projelere gitmez")
    agents = os.path.join(ROOT, "AGENTS.md")
    if os.path.isfile(agents):
        with open(agents, encoding="utf-8") as fh:
            check("incele.py" in fh.read(),
                  "AGENTS.md merge yolunu belgelemiyor — kural yazılı değilse "
                  "bir sonraki oturumda unutulur")


def test_agents_md():
    path = os.path.join(ROOT, "AGENTS.md")
    check(os.path.isfile(path), "AGENTS.md yok")
    if not os.path.isfile(path):
        return
    lines = open(path, encoding="utf-8").read().splitlines()
    check(len(lines) <= 200, f"AGENTS.md {len(lines)} satır (>200 — kısalt)")
    claude = os.path.join(ROOT, "CLAUDE.md")
    check(os.path.isfile(claude), "CLAUDE.md adapter yok")
    if os.path.isfile(claude):
        check("@AGENTS.md" in open(claude, encoding="utf-8").read(),
              "CLAUDE.md: @AGENTS.md importu yok")
    link = os.path.join(ROOT, ".claude", "skills")
    check(os.path.islink(link) and
          os.path.realpath(link) == os.path.realpath(
              os.path.join(ROOT, ".agents", "skills")),
          ".claude/skills → .agents/skills symlink'i yok/yanlış")


def test_rules():
    """Path-scoped domain kuralları geçerli frontmatter taşıyor mu."""
    rules_dir = os.path.join(ROOT, ".claude", "rules")
    if not os.path.isdir(rules_dir):
        return
    for f in sorted(os.listdir(rules_dir)):
        if not f.endswith(".md"):
            continue
        fm = frontmatter(os.path.join(rules_dir, f))
        check(fm is not None, f"rule {f}: frontmatter yok")
        if fm:
            check("paths" in fm, f"rule {f}: 'paths' scope tanımı yok")
            check(isinstance(fm.get("paths"), list) and fm["paths"],
                  f"rule {f}: 'paths' boş/liste değil")


def test_yetki_politikasi():
    """Capability profili gerçek motor politikasına çevrilmiş mi.

    Denetimin P0'ı (2026-08-15, iki bağımsız rapor): profil YAML'ındaki
    `filesystem`/`commands`/`network` alanları yalnız ŞEMA düzeyinde
    doğrulanıyordu; repoda tek bir `permissions` bloğu yoktu. "İzin sınırı"
    denen şey model talimatıydı.

    Bu bekçi drift'i yakalar: politika değişip dosyaya yazılmazsa kırmızı.
    Sınırı: kuralın motorda GERÇEKTEN uygulandığını doğrulayamaz, yalnız
    yazıldığını doğrular (kapı sınıfı: yerel workflow guard).
    """
    yol = os.path.join(ROOT, "bin", "yetki.py")
    check(os.path.isfile(yol), "bin/yetki.py yok — profil yalnız beyan kalır")
    if not os.path.isfile(yol):
        return
    proc = subprocess.run([sys.executable, yol, "--check"],
                          capture_output=True, text=True, cwd=ROOT)
    check(proc.returncode == 0,
          f"yetki politikası geride: {(proc.stdout or '').strip()[-300:]}")


def test_memory_tool():
    """Hafıza bakım robotu var, çalışıyor ve birim testleri geçiyor mu."""
    path = os.path.join(ROOT, "bin", "memory_hygiene.py")
    check(os.path.isfile(path), "bin/memory_hygiene.py yok")
    if os.path.isfile(path):
        proc = subprocess.run(
            [sys.executable, path, "--today", "2026-07-24"],
            capture_output=True, text=True, cwd=ROOT)
        check(proc.returncode in (0, 1),
              f"memory_hygiene beklenmedik exit: {proc.returncode}")
        check("HAFIZA BAKIMI" in proc.stdout,
              "memory_hygiene beklenen çıktı biçimini üretmedi")
    # Bekçinin bekçisi: araçların kendi birim testleri de koşmalı
    if os.path.isdir(os.path.join(ROOT, "tests")):
        proc = subprocess.run(
            [sys.executable, "-W", "error::ResourceWarning",
             "-m", "unittest", "discover", "-s", "tests", "-q"],
            capture_output=True, text=True, cwd=ROOT)
        check(proc.returncode == 0,
              f"tests/ birim testleri başarısız: {proc.stderr[-300:]}")


def test_routing(skill_names, profil_skills=None):
    """Router mekanizması: tablo eksiksiz mi, hook kayıtlı mı, seçim doğru mu."""
    path = os.path.join(ROOT, ".agents", "routing.yml")
    check(os.path.isfile(path), ".agents/routing.yml yok (skill yönlendirme tablosu)")
    router = os.path.join(ROOT, "bin", "route.py")
    check(os.path.isfile(router), "bin/route.py yok")
    if not (os.path.isfile(path) and os.path.isfile(router)):
        return

    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    routed = set()
    for rule in cfg.get("rules", []):
        skill = rule.get("skill")
        check(skill, f"routing kuralı 'skill' alanı taşımıyor: {rule}")
        check(rule.get("task_class") in GOREV_SINIFLARI,
              f"routing '{skill}': geçersiz task_class '{rule.get('task_class')}'")
        trig = rule.get("triggers") or []
        check(len(trig) >= 3,
              f"routing '{skill}': en az 3 tetik ifadesi gerekli ({len(trig)} var)")
        # Niyet kapısı alanı: yazım hatası ('intent: oku' gibi) kuralı
        # sessizce yazma-niyetli sayar — geçersiz değer burada kesilir.
        check(rule.get("intent") in (None, "read", "write"),
              f"routing '{skill}': geçersiz intent '{rule.get('intent')}' "
              "(izinli: read, write ya da alanı hiç yazma)")
        if rule.get("external"):
            continue  # skill repo dışında (kullanıcı-global) — varlığı doğrulanamaz
        check(skill in skill_names,
              f"routing '{skill}': böyle bir skill yok (kayıtlı: {sorted(skill_names)})")
        routed.add(skill)
    # Analiz katmanı: her iş bir disipline sahiplenir (tek sahip — zincir değil).
    roller = set(cfg.get("roles") or [])
    check(len(roller) >= 5,
          "routing: 'roles' kaydı yok/eksik — analiz 'bu iş kimin işi' sorusunu "
          "cevaplayamaz")
    for rule in cfg.get("rules", []):
        check(rule.get("owner") in roller,
              f"routing '{rule.get('skill')}': geçersiz/eksik owner "
              f"'{rule.get('owner')}' (kayıtlı roller: {sorted(roller)})")
    for d in cfg.get("disciplines", []):
        check(d.get("owner") in roller,
              f"disiplin '{d.get('owner')}': roles kaydında yok")
        check(len(d.get("triggers") or []) >= 3,
              f"disiplin '{d.get('owner')}': en az 3 tetik gerekli")
    # Codex hükmü (2026-07-26): profil "izin sınırı", routing "bu turdaki
    # seçim". Sınır uygulanmıyorsa profil süstür. routing ⊆ profile.skills.
    if profil_skills:
        for rule in cfg.get("rules", []):
            if rule.get("external"):
                continue  # repo dışı skill profil kümesinde aranmaz
            tc, sk = rule.get("task_class"), rule.get("skill")
            izinli = profil_skills.get(tc, set())
            check(sk in izinli,
                  f"routing '{sk}' sınıfı '{tc}' için zorunlu kılıyor ama o "
                  f"sınıfın profilinde yok (izinli: {sorted(izinli)}) — "
                  "ya profili genişlet ya task_class'ı düzelt")
    check(cfg.get("fallback", {}).get("message"),
          "routing: eşleşme yoksa ne yapılacağını söyleyen fallback mesajı yok")

    # always_add tablonun İKİNCİ giriş yoludur: `rules` gibi denetlenmezse
    # profil allowlist'i buradan sessizce delinir. Router'ın öneri süzgeci
    # (route._sinirli) sistemin YÖNETMEDİĞİ adı bilinçli olarak geçirir
    # (eklenti skill'i kapsam dışıdır, dışlama değil) — o kapı burada
    # kapanmazsa fail-open kalır (inceleme 9. tur, PR #49).
    for rule in cfg.get("always_add", []):
        sk = rule.get("skill")
        check(len(rule.get("triggers") or []) >= 1,
              f"always_add '{sk}': tetik yok — hiç eklenmeyecek kayıt")
        check(sk in skill_names,
              f"always_add '{sk}': böyle bir skill yok (kayıtlı: "
              f"{sorted(skill_names)})")
        if profil_skills:
            check(any(sk in izinli for izinli in profil_skills.values()),
                  f"always_add '{sk}': hiçbir capability profilinde yok — "
                  "profile ekle ya da kaydı kaldır; profilsiz öneri izin "
                  "sınırını delermiş gibi görünür")

    # Her skill ya yönlendirilir ya da gerekçeli olarak dışarıda bırakılır —
    # yoksa görünür ama hiç seçilmeyen ölü ağırlık olur.
    excluded = set()
    for entry in cfg.get("not_routed", []):
        skill = entry.get("skill")
        check(skill in skill_names,
              f"not_routed '{skill}': böyle bir skill yok")
        check(len((entry.get("reason") or "").strip()) >= 40,
              f"not_routed '{skill}': yönlendirilmeme gerekçesi yok/çok kısa")
        excluded.add(skill)
    missing = skill_names - routed - excluded
    check(not missing,
          f"routing tablosunda tetiği olmayan skill(ler): {sorted(missing)} "
          f"— tetik ekle ya da not_routed'a gerekçeyle yaz")

    # Hook kayıtlı mı (mekanizma; bağlam değil).
    settings = os.path.join(ROOT, ".claude", "settings.json")
    check(os.path.isfile(settings), ".claude/settings.json yok (router hook'u kayıtsız)")
    if os.path.isfile(settings):
        data = json.load(open(settings, encoding="utf-8"))
        cmds = [h.get("command", "")
                for entry in data.get("hooks", {}).get("UserPromptSubmit", [])
                for h in entry.get("hooks", [])]
        check(any("route.py" in c for c in cmds),
              "settings.json: UserPromptSubmit hook'u route.py'yi çağırmıyor")

    # Karşılamanın hafızası mekanizma mı, temenni mi? 2026-08-15'e kadar
    # temenniydi: metin ajana "hatirla.py ile bak" diyordu, ajan bakmıyordu.
    check("karsilama_kayitlari" in _router_katmani(),
          "router katmanı karşılama hafızasını ÇAĞIRMIYOR — hatirla.py yazılmış "
          "ama kullanılmayan araç olur, 📌 Geçmiş modelin belleğine kalır")

    # Golden vaka: router gerçekten doğru skill'i seçiyor mu (regresyon kapısı).
    # Doğrulama koşumu kullanıcının aktivite kaydını kirletmemeli (izolasyon).
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, AURAS_EVENT_LOG=os.path.join(td, "events.jsonl"))
        _routing_golden_cases(router, env)


def _routing_golden_cases(router, env):
    for prompt, expected in (("kullanıcı endpoint'i ekle", "implement-change"),
                             ("bu metrik nerede hesaplanıyor", "research-with-evidence"),
                             ("login akışını güvenlik açısından incele", "security-review")):
        proc = subprocess.run(
            [sys.executable, router],
            input=json.dumps({"prompt": prompt}), capture_output=True,
            text=True, cwd=ROOT, env=env)
        check(proc.returncode == 0, f"route.py exit {proc.returncode} ('{prompt}')")
        check(expected in proc.stdout,
              f"router '{prompt}' → beklenen '{expected}' yönlendirmesi yok")
        check("🧭" in proc.stdout and "🔧" in proc.stdout,
              "router: cevap başlığı biçimini dayatmıyor — kullanıcı yazışmada "
              "hangi skill'in çalıştığını göremez")
        # Yapı denetlenir, içerik değil: bağlı projenin geçmişi başka olur,
        # "kayıt bulunamadı" da meşru sonuçtur. Eksik olan tek şey susmaktır.
        check("📌 Geçmiş" in proc.stdout,
              "router: karşılamada hafıza satırı yok — geçmiş hatırlatması "
              "kayda değil ajanın belleğine kalır")


def test_no_external_roles():
    """Sabit rol dosyası KURMA ilkesi mekanizmaya bağlandı.

    Disiplin bir ETİKETTİR (analiz çıktısı); derinlik yalnız skill'lerde
    yaşar. Router dış rol dosyasına (ör. ~/.claude/agents/*.md) atıf yaparsa
    ikinci bir bilgi otoritesi doğar ve skill'lerle çakışıp bayatlar —
    kullanıcı itirazı 2026-07-26, Codex mutabakatı aynı gün.
    """
    router = os.path.join(ROOT, "bin", "route.py")
    if not os.path.isfile(router):
        return
    metin = open(router, encoding="utf-8").read()
    for yasak in ("~/.claude/agents", ".claude/agents/"):
        check(yasak not in metin,
              f"route.py: dış rol dosyasına atıf ('{yasak}') — disiplin etiket "
              "olmalı, derinlik skill'de yaşamalı")
    check(not os.path.isdir(os.path.join(ROOT, ".agents", "roles")),
          ".agents/roles/ var — sabit rol tanımı skill'lerle çakışır; "
          "derinlik gerekiyorsa skill yaz")


def test_skill_validators_wired():
    """Skill'in getirdiği doğrulayıcı bir KAPIYA bağlı olmalı.

    "Bekçisiz kural temennidir" ilkesinin skill katmanındaki karşılığı:
    yazılmış ama hiçbir kapının çağırmadığı doğrulayıcı, kuralı belgede var
    sistemde yok durumuna düşürür (2026-08-05 bulgusu: 3 doğrulayıcı yazılmış,
    0'ı çağrılıyordu).

    Sözleşme: `check_*` / `scan_*` önekli script KAPI doğrulayıcısıdır ve en az
    bir kapı dosyasında çağrılmalıdır. Diğer isimler yardımcı araçtır
    (ör. contrast_check.py — elle renk çifti alır, diff üstünde koşamaz).
    """
    skills_dir = os.path.join(ROOT, ".agents", "skills")
    if not os.path.isdir(skills_dir):
        return
    kapilar = ["bin/hooks/pre-push", "bin/kapi.py", "bin/validate.py",
               ".github/workflows/evidence.yml"]
    metin = ""
    for rel in kapilar:
        yol = os.path.join(ROOT, rel)
        if os.path.isfile(yol):
            metin += open(yol, encoding="utf-8").read()

    for skill in sorted(os.listdir(skills_dir)):
        sdir = os.path.join(skills_dir, skill, "scripts")
        if not os.path.isdir(sdir):
            continue
        for f in sorted(os.listdir(sdir)):
            if not f.endswith(".py"):
                continue
            if not (f.startswith("check_") or f.startswith("scan_")):
                continue        # yardımcı araç — kapı sözleşmesi dışında
            check(f in metin,
                  f"{skill}/scripts/{f} hiçbir kapıya bağlı değil — yazılı "
                  f"kural zorlanmıyor. Kapıya bağla ({', '.join(kapilar)}) "
                  f"ya da yardımcı ise adını 'check_/scan_' önekinden çıkar")


def test_visibility():
    """Görünürlük katmanı: skill çağrıları ve tur aktivitesi kayda geçiyor mu.

    Kullanıcı 'hangi skill çağrıldı, ne yapıldı' sorusunu benim beyanımdan
    değil makine kaydından cevaplayabilmeli.
    """
    for rel in ("bin/run_event.py", "bin/durum.py"):
        check(os.path.isfile(os.path.join(ROOT, rel)), f"görünürlük aracı yok: {rel}")
    if not all(os.path.isfile(os.path.join(ROOT, r))
               for r in ("bin/run_event.py", "bin/durum.py")):
        return

    settings = os.path.join(ROOT, ".claude", "settings.json")
    if os.path.isfile(settings):
        data = json.load(open(settings, encoding="utf-8"))
        hooks = data.get("hooks", {})
        skill_hook = any(
            "run_event.py" in h.get("command", "")
            for e in hooks.get("PostToolUse", [])
            if "Skill" in (e.get("matcher") or "")
            for h in e.get("hooks", []))
        check(skill_hook,
              "settings.json: PostToolUse/Skill hook'u run_event.py'yi çağırmıyor "
              "— skill çağrıları kayda geçmez")
        check(any("kapi.py" in h.get("command", "")
                  for e in hooks.get("Stop", []) for h in e.get("hooks", [])),
              "settings.json: Stop hook'u kapi.py'yi çağırmıyor — kanıtsız tur "
              "kapanabilir")
        check(any("--kind ui" in h.get("command", "")
                  for e in hooks.get("PostToolUse", []) for h in e.get("hooks", [])),
              "settings.json: tarayıcı etkileşimi kayda geçmiyor — 'tıklama "
              "kanıtı' kapısı çalışmaz")
        check(any("--kind edit" in h.get("command", "")
                  for e in hooks.get("PostToolUse", []) for h in e.get("hooks", [])),
              "settings.json: düzenlemeler kayda geçmiyor — kapı neyin "
              "değiştiğini bilemez")
        # PostToolUseFailure OLMADAN kapı yalnız BAŞARILARI görür: çöken
        # test kayda hiç girmez, "testler kırmızı" dalı ölü kod olur.
        # (Codex bulgusu, PR #15 — ölçümle doğrulandı: Claude Code 2.1.220'de
        # başarısız araç çağrısı PostToolUse'u değil bu olayı tetikliyor.)
        check(any("run_event.py" in h.get("command", "")
                  for e in hooks.get("PostToolUseFailure", [])
                  for h in e.get("hooks", [])),
              "settings.json: PostToolUseFailure hook'u yok — başarısız "
              "komutlar kayda girmez, kapı yalnız başarıları görür")

    # Kayıt disposable ve gitignore'lu olmalı (auto-memory kuralı: hiçbir iş
    # buna bağımlı olamaz, repoya sızmamalı).
    gi = os.path.join(ROOT, ".gitignore")
    check(os.path.isfile(gi) and ".agents/runtime" in open(gi, encoding="utf-8").read(),
          ".gitignore: .agents/runtime yok — disposable kayıt repoya sızar")

    # Uçtan uca: sahte Skill hook payload'u → olay → tabloda görünür.
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "events.jsonl")
        p1 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "run_event.py"),
             "--kind", "skill", "--log", log],
            input=json.dumps({"tool_input": {"skill": "kernel-work"}}),
            capture_output=True, text=True, cwd=ROOT)
        check(p1.returncode == 0, f"run_event.py exit {p1.returncode}")
        p2 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "durum.py"), "--log", log],
            capture_output=True, text=True, cwd=ROOT)
        check(p2.returncode == 0, f"durum.py exit {p2.returncode}")
        check("kernel-work" in p2.stdout,
              "durum.py: kaydedilen skill çağrısı tabloda görünmüyor")


def test_onboarding_parity():
    """auras-init.sh, kernel'in tamamını yeni projeye taşıyor mu.

    Sürüklenme bekçisi: motor listesi TEK yerde (bin/kernel_dosyalari.py)
    yaşamalı. İkinci bir kopya (betiğin içinde elle liste) çıkarsa listeler
    ayrışır ve /auras eksik kurulum yapar — burada kesilir.
    """
    # auras-init.sh yalnız kanonik şablon reposunda bulunur; bağlanmış
    # projelerde yoktur ve orada denetlenecek bir şey de yok.
    path = os.path.join(ROOT, "bin", "auras-init.sh")
    if not os.path.isfile(path):
        return
    text = open(path, encoding="utf-8").read()

    kd = _kernel_dosyalari()
    check(kd is not None, "bin/kernel_dosyalari.py yüklenemedi — motor "
                          "listesinin tek tanımı yok")
    if kd is not None:
        # Listedeki her giriş kanonikte gerçekten var mı (ölü giriş = eksik kurulum)
        for rel in kd.MOTOR + kd.MOTOR_DIZIN:
            check(os.path.exists(os.path.join(ROOT, rel)),
                  f"kernel_dosyalari: '{rel}' listede ama repoda yok")
        # Tek tanım kuralı: betik listeyi kendi içinde YENİDEN tanımlamamalı
        check("import kernel_dosyalari" in text,
              "auras-init.sh motor listesini kernel_dosyalari'ndan almıyor")
        check("MOTOR = [" not in text,
              "auras-init.sh motor listesinin ikinci kopyasını taşıyor — "
              "tek tanım bin/kernel_dosyalari.py'de olmalı")

    # Proje dosyaları (bir kez yazılır, ezilmez) motor listesinde değildir;
    # ayrıca denetlenir.
    for rel in ("AGENTS.md", "CLAUDE.md"):
        check(rel in text,
              f"auras-init.sh '{rel}' taşımıyor — yeni proje doğrulamada kırılır")
    # Güncelleme yolu: motor dosyaları her koşumda senkronlanmalı, hook'lar
    # kaynak settings.json'dan türetilmeli (elle liste tutulursa bayatlar).
    check(".kernel-manifest.json" in text,
          "auras-init.sh: motor dosyaları için güncelleme kaydı yok — bağlı "
          "projeler eski sürümde kalır")
    check('".claude", "settings.json"' in text or '.claude/settings.json' in text,
          "auras-init.sh: hook'ları kaynak settings.json'dan birleştirmiyor")
    # Geri-taşıma yolu: korunan yerel iş için çıkış kapısı gösterilmeli,
    # yoksa sapma sessizce birikir (2026-08-05 bulgusu).
    check("auras_geri.py" in text,
          "auras-init.sh korunan yerel işi geri-taşımaya yönlendirmiyor — "
          "sapma sessizce birikir")
    if kd is not None:
        test_tasinan_testin_ihtiyaclari_da_tasinir(kd)


def test_tasinan_testin_ihtiyaclari_da_tasinir(kd):
    """Taşınan bir test, taşınmayan bir dosyayı şart koşamaz.

    Mantık `kernel_dosyalari.eksik_test_bagimliliklari()` içinde yaşıyor
    (saf fonksiyon, birim testi var); burada yalnız kapıya bağlanır.
    """
    for test_dosya, rel in kd.eksik_test_bagimliliklari(ROOT):
        err(f"tests/{test_dosya} '{rel}' dosyasını şart koşuyor ama o dosya "
            f"kurulumdan sonra projede bulunmaz — bağlı proje kurulumdan "
            f"kırmızı çıkar. kernel_dosyalari.MOTOR'a ekle ya da testi "
            f"kanonik-özel yap")


# Testleri KOŞMADAN yalnız keşfeder: hangi modül kaç test üretti, hangisi
# import'ta çöktü. Ayrı süreç, çünkü keşif her test modülünü import eder.
# Sonuç SENTINEL'li tek satırda döner: keşif import sırasında modüllerin
# kendi çıktısını da stdout'a alır ve tüm akışı JSON sanmak, ilgisiz bir
# `print` yüzünden bekçiyi sahte kırmızıya düşürürdü (Codex bulgusu, PR #26).
_KESIF_ISARET = "AURAS_KESIF:"
_KESIF_KODU = """\
import json, sys, unittest
sys.path.insert(0, "tests")
try:
    import ortam
    # Kayıt keşiften ÖNCE yoklanıp dondurulur: keşif her test modülünü import
    # eder ve sonradan yüklenen bir modül kaydı değiştirebilseydi bekçi tam da
    # denetlediği koda bağımlı olurdu. Yoklama süitin KOŞTUĞU yorumlayıcıda
    # çalışmalı — "bu makinede PyYAML var mı" sorusunu ancak o cevaplayabilir.
    kayit = {s: bool(y()) for s, y in ortam.MESRU_ATLAMALAR.items()}
except Exception:
    kayit = None       # okunamadı != boş; hüküm tarafı fail-closed davranır
sayim, hatali, atlanan = {}, [], []
def gez(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            gez(t)
        elif type(t).__module__ == "unittest.loader":
            # ÇÖKME ile GÖRÜNÜR ATLAMA aynı yere düşer ama aynı şey değildir:
            # unittest ilkini _FailedTest, ikincisini ModuleSkipped yapar.
            # Ayırmazsak sistemin kendi önerdiği çare ("koşullu atlamaya
            # çevir") uygulandığında bile kırmızı kalır (Agent Ofis, 2026-08-12).
            ad = t.id().rsplit(".", 1)[-1]
            if type(t).__name__ == "ModuleSkipped":
                # Sebep de taşınır: onsuz atlamanın MEŞRU olup olmadığı
                # sınanamaz ve her atlama beyanla geçerdi. unittest sebebi
                # atlama sarmalayıcısının üstünde saklar.
                fn = getattr(type(t), t._testMethodName, None)
                atlanan.append([ad, getattr(fn, "__unittest_skip_why__", "")])
            else:
                hatali.append(ad)
        else:
            m = type(t).__module__
            sayim[m] = sayim.get(m, 0) + 1
gez(unittest.TestLoader().discover("tests"))
print("%s" + json.dumps({"sayim": sayim, "hatali": hatali,
                         "atlanan": atlanan, "ortam": kayit}))
""" % _KESIF_ISARET


def _atlanan_modul_adlari(kb, veri):
    """Modül düzeyinde atlananları hükme bağlar; görülen adları döndürür.

    Meşru atlama BİLGİ satırıdır — kapsam daraldı ama gizlenmedi. Ortam
    kaydına bağlanmayan atlama BLOK'tur: aksi hâlde "Ran N", modül başına
    yazılan tek bir `raise unittest.SkipTest` ile beyan üzerine daraltılır
    (Codex bağımsız incelemesi, PR #47, P1). Ölçüt `kapsam_bekcisi`de.
    """
    adlar = set()
    for ad, sebep, hukum in kb.atlama_hukmu(veri.get("atlanan", []),
                                            veri.get("ortam")):
        adlar.add(ad)
        if hukum == "ortam":
            print(f"  ↷ tests/{ad}.py görünür biçimde atlandı ({sebep}) — "
                  f"testleri KOŞMADI, kapsam o kadar dar")
        else:
            err(f"tests/{ad}.py modül düzeyinde atlandı, testleri süitten "
                f"düştü: {kb.ATLAMA_MESAJI[hukum]} (sebep: {sebep!r})")
    return adlar


def test_test_kapsami_daralmaz():
    """Her test dosyası keşfe girmeli — eksilen test sessiz kapsam kaybıdır.

    2026-08-07 ölçümü: PyYAML'sız yorumlayıcıda üç modül import'ta çöktü.
    Süit "Ran 186 / 3 hata" dedi; PyYAML'lı yorumlayıcıda "Ran 220 / OK".
    Çıktının hiçbir satırı 34 testin HİÇ KOŞMADIĞINI söylemiyordu — sayının
    kendisi yanıltıcıydı. Kırmızı test bağırır; yok olan test bağırmaz.

    Bu bekçi üç sessizliği kapar: (1) import'ta çöküp süitten düşen modül,
    (2) keşif desenine uymadığı için hiç toplanmayan dosya — ikincisinde
    çıkış kodu 0'dır, yani mevcut `returncode == 0` kontrolü onu göremez,
    (3) modül düzeyinde GÖRÜNÜR atlama: görünür olması meşru olması demek
    değildir; sebep `tests/ortam.py` kaydında yoklanmadan geçemez.

    Bekçinin SINIRI: dosya bazında çalışır. Bir modülün İÇİNDEN silinen tek
    testi göremez; onu ancak kanıt-tarafı bir sayaç yakalayabilir.
    """
    kb = _bin_modul("kapsam_bekcisi")
    if kb is None or not os.path.isdir(os.path.join(ROOT, "tests")):
        return
    proc = subprocess.run([sys.executable, "-c", _KESIF_KODU],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        err(f"test keşfi koşamadı (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-300:]}")
        return
    satir = next((s for s in reversed(proc.stdout.splitlines())
                  if s.startswith(_KESIF_ISARET)), None)
    try:
        veri = json.loads(satir[len(_KESIF_ISARET):])
    except (TypeError, ValueError):
        err("test keşfi çıktısı ayrıştırılamadı — 'okunamadı' ile 'temiz' "
            "aynı şey değildir (fail-closed)")
        return
    for ad in veri["hatali"]:
        err(f"tests/{ad}.py import'ta çöktü — içindeki testler süitten yok "
            f"oldu ve 'Ran N' sessizce daraldı. Ortam bağımlılığıysa "
            f"tests/ortam.py üstünden koşullu atlamaya çevir")
    # Çöken modül keşif tarafından GÖRÜLDÜ; sorunu import'tur, adı değil —
    # ikinci kez ve yanlış çareyle raporlanmasın.
    gorulen = (set(veri["sayim"]) | set(veri["hatali"])
               | _atlanan_modul_adlari(kb, veri))
    for f in kb.toplanmayan_testler(ROOT, gorulen):
        err(f"tests/{f} TestCase tanımlıyor ama keşfe hiç girmiyor — testleri "
            f"koşmuyor ve çıkış kodu 0 kalıyor (görünmez kapsam kaybı). "
            f"Adını 'test_*.py' yap")


def test_gitleaks_manifest_muafiyeti():
    """gitleaks kullanan projede kernel manifest'i muaf tutulmuş mu.

    `.agents/.kernel-manifest.json` yalnız sha256 özeti taşır ama gitleaks'in
    generic-api-key kuralı uzun hex bloklarını anahtar sanıyor. 4cast'te bu
    7 yanlış pozitif üretip CI'ı bir haftadan uzun kırmızıda tuttu
    (2026-08-07). Dosyayı kernel ÜRETTİĞİ için sorun bağlı her projede
    tekrarlanır — bu yüzden kurulumun sorumluluğu.

    gitleaks kullanmayan projede sessiz geçer (kural uydurmaz).
    """
    kd = _kernel_dosyalari()
    if kd is None or not kd.gitleaks_kullaniyor(ROOT):
        return
    check(kd.manifest_muaf_mi(ROOT),
          "gitleaks kullanılıyor ama .agents/.kernel-manifest.json muaf "
          "değil — sha256 özetleri 'generic-api-key' sanılıp CI'ı kilitler. "
          "/auras yeniden koş ya da .gitleaks.toml'a allowlist ekle")


def test_quality_gate():
    """Kod kalitesi ölçülüyor ve ölçüm bir kapıya bağlı mı.

    "Ölçmediğin şeyde standardın yok, tercihin var" — dosya/fonksiyon boyutu,
    karmaşıklık ve borç işaretleri için tek bir sayı yoksa 'temiz kod' kuralı
    uygulanamaz. Ölçüm deterministik olmalı (LLM yorumu değil) ve regresyon
    ratchet ile kesilmeli.
    """
    arac = os.path.join(ROOT, "bin", "kalite.py")
    check(os.path.isfile(arac), "bin/kalite.py yok — kod kalitesi ölçülmüyor")
    if not os.path.isfile(arac):
        return
    kd = _kernel_dosyalari()
    if kd is not None:
        check("bin/kalite.py" in kd.MOTOR,
              "kalite.py motor listesinde değil — bağlı projelere gitmez")
    ci = os.path.join(ROOT, ".github", "workflows", "evidence.yml")
    if os.path.isfile(ci):
        check("kalite.py" in open(ci, encoding="utf-8").read(),
              "CI kalite ölçümünü koşmuyor — ratchet regresyonu yakalanmaz")
    # Ölçüm çalışıyor ve beklenen çıktı sözleşmesini üretiyor mu
    proc = subprocess.run([sys.executable, arac, "--json"],
                          capture_output=True, text=True, cwd=ROOT, input="")
    check(proc.returncode in (0, 1),
          f"kalite.py beklenmedik exit: {proc.returncode}")
    try:
        veri = json.loads(proc.stdout or "{}")
        check("sayaclar" in veri and "kapsam" in veri,
              "kalite.py --json beklenen alanları üretmiyor (sayaclar, kapsam)")
    except ValueError:
        err("kalite.py --json geçerli JSON üretmiyor")


def test_project_gate_hook():
    """Proje kapısı uzantı noktası: proje-özel yasak motoru çatallamadan koşar.

    Neden: projeye özel pazarlıksız yasaklar ("localStorage'da token yok")
    mekanizmaya bağlanmalı, ama bunun için motor dosyasını (pre-push,
    validate.py) düzenlemek çatal üretir — ADR-0002'nin çözdüğü sorunun
    kaynağı. Motor genel çağrıyı taşır, kural projenin olur.

    Sözleşme: `bin/hooks/proje-kapisi` VARSA çalıştırılabilir olmalı ve
    pre-push onu koşmalı. Dosya motor listesinde DEĞİLDİR (proje sahibidir,
    /auras ezmez, geri-taşımada yukarı gitmez).
    """
    kanca = os.path.join(ROOT, "bin", "hooks", "pre-push")
    if os.path.isfile(kanca):
        check("proje-kapisi" in open(kanca, encoding="utf-8").read(),
              "pre-push proje kapısını çağırmıyor — proje-özel yasak "
              "mekanizmaya bağlanamaz, motor çatallanır")
    kd = _kernel_dosyalari()
    if kd is not None:
        check("bin/hooks/proje-kapisi" not in kd.MOTOR,
              "proje-kapisi motor listesinde — proje dosyası motorca "
              "ezilemez (sahibi proje)")
    proje = os.path.join(ROOT, "bin", "hooks", "proje-kapisi")
    if os.path.isfile(proje):
        check(os.access(proje, os.X_OK),
              "bin/hooks/proje-kapisi çalıştırılabilir değil — kapı sessizce "
              "atlanır (chmod +x)")


def test_mechanisms():
    """Deterministik kapılar ve risk sinyali araçları yerinde mi."""
    for rel in ("bin/hooks/pre-push", "bin/install-hooks.sh",
                "bin/codex-review.sh"):
        path = os.path.join(ROOT, rel)
        check(os.path.isfile(path), f"mekanizma eksik: {rel}")
        if os.path.isfile(path):
            check(os.access(path, os.X_OK), f"{rel}: çalıştırma izni yok")
    hook = os.path.join(ROOT, "bin", "hooks", "pre-push")
    if os.path.isfile(hook):
        check("validate.py" in open(hook, encoding="utf-8").read(),
              "pre-push kancası kernel doğrulamasını koşmuyor")
    # Kurulu kanca makineye özel durumdur; CI'da .git/hooks yoktur ve CI
    # zaten aynı doğrulamayı doğrudan koşar.
    installed = os.path.join(ROOT, ".git", "hooks", "pre-push")
    if os.path.isdir(os.path.join(ROOT, ".git")) and not os.environ.get("CI"):
        check(os.path.isfile(installed) and os.access(installed, os.X_OK),
              "pre-push kancası kurulu değil (bash bin/install-hooks.sh)")


def test_kapi_siniflari_durust():
    """Her kapı NE OLDUĞUNU yazmak zorunda — güvenlik sınırı taklidi yasak.

    Neden bekçi: bir kapının gücünü belgede abartmak, olmayan korumaya
    güvenmeye yol açar. Tur kapısı agent'ın kendi makinesinde, agent'ın
    yazabildiği dosyalarla çalışır; agent kaydı silebilir, doğrulayıcıyı
    değiştirebilir, `--no-verify` ile push edebilir. Bu bir iş akışı
    yardımcısıdır, bütünlük sınırı değildir. Bu bölüm silinirse ya da
    'güvenlik sınırı' iddiasına dönerse kernel doğrulaması düşer.
    """
    path = os.path.join(ROOT, "AGENTS.md")
    if not os.path.isfile(path):
        return
    metin = open(path, encoding="utf-8").read()
    check("## Kapıların gerçek sınıfı" in metin,
          "AGENTS.md: 'Kapıların gerçek sınıfı' bölümü yok — her kapının "
          "ne olduğu (yerel guard mı, bütünlük sınırı mı) yazılmalı")
    check("yerel workflow guard" in metin,
          "AGENTS.md: tur/push kapıları 'yerel workflow guard' olarak "
          "adlandırılmamış (Codex hükmü 2026-08-07: yetki ayrımı yoksa "
          "güvenlik sınırı deme)")
    check("güvenlik sınırı değildir" in metin,
          "AGENTS.md: yerel kapıların güvenlik sınırı OLMADIĞI açıkça "
          "yazılmamış")
    for kapi in ("bin/kapi.py", "bin/hooks/pre-push", "bin/incele.py"):
        check(kapi in metin, f"AGENTS.md: '{kapi}' sınıflandırılmamış")


def test_test_oracle_exit_koduna_bagli():
    """Test sonucu çıktı sözcüğünden değil çıkış kodundan okunmalı.

    2026-08-07 ölçümü: `exit 1; echo passed` eski oracle'da GEÇTİ sayıldı.
    Bu bekçi sözcük-eşleşmeli oracle'ın geri gelmesini engeller.
    """
    path = os.path.join(ROOT, "bin", "run_event.py")
    if not os.path.isfile(path):
        return
    metin = open(path, encoding="utf-8").read()
    check("BASARILI_RE" not in metin,
          "run_event.py: çıktı sözcüğüne bakan 'geçti' deseni geri gelmiş — "
          "test sonucu yalnız çıkış kodundan/platform sinyalinden okunur")
    check("exit_code" in metin,
          "run_event.py: test oracle'ı çıkış kodunu okumuyor")


def main():
    skill_names = test_skills()
    profil_skills = test_profiles(skill_names)
    test_issue_form()
    test_workflow()
    test_evidence_roundtrip()
    test_kapsam_siniri_yazili()


    test_bagimsiz_inceleme()
    test_agents_md()
    test_rules()
    test_yetki_politikasi()
    test_memory_tool()
    test_routing(skill_names, profil_skills)
    test_no_external_roles()
    test_skill_validators_wired()
    test_visibility()
    test_onboarding_parity()
    test_test_kapsami_daralmaz()
    test_gitleaks_manifest_muafiyeti()
    test_quality_gate()
    test_project_gate_hook()
    test_mechanisms()
    test_kapi_siniflari_durust()
    test_test_oracle_exit_koduna_bagli()
    if ERRORS:
        print(f"KERNEL DOĞRULAMA: {len(ERRORS)} hata")
        for e in ERRORS:
            print(f"  ✗ {e}")
        return 1
    print("KERNEL DOĞRULAMA: tüm kontroller geçti ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
