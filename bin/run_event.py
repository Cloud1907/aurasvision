#!/usr/bin/env python3
"""Run olay yazıcısı — hook'lardan gelen aktiviteyi görünür kayda çevirir.

Amaç: "hangi skill çağrıldı, ne yapıldı" sorusu ajanın BEYANINDAN değil,
makine kaydından cevaplanabilsin.

Hook kullanımı (.claude/settings.json):
  PostToolUse/Skill  → run_event.py --kind skill      (hangi skill yüklendi)
  SubagentStop       → run_event.py --kind subagent   (hangi rol çağrıldı)
  Stop               → run_event.py --kind stop       (tur kapandı)
  (route olayını bin/route.py kendisi yazar)

Kayıt yeri: `.agents/runtime/events.jsonl` — gitignore'lu, yerel, silinebilir.
KARAR bu kayda bağlanamaz: hiçbir kalıcı iddia (hafıza, rapor, PR gövdesi)
kaynağını buradan alamaz (AGENTS.md hafıza otoritesi, 3. katman).

Tek istisna ve sınırı: tur kapısı (`bin/kapi.py`) bu kaydı okur. Bu yüzden
tur kapısı bir bütünlük sınırı DEĞİL, yerel workflow guard'dır — kayıt
silinirse kapı sessizce geçer (AGENTS.md "Kapıların gerçek sınıfı").

Tasarım kuralı: hook asla bloklamaz. Her hata yolunda exit 0.
"""
import argparse
import contextlib
import datetime as dt
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_LOG = os.path.join(".agents", "runtime", "events.jsonl")
INTENT_MAX = 80

# Diske yazılmasına izin verilen alanlar (allowlist — prompt/araç çıktısı yok).
ALLOWED = ("kind", "skill", "agent", "routed", "extras", "task_class",
           "intent", "session", "file", "cmd", "ok", "src", "sig", "reason",
           "note")

_FALLBACK_SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[0-9A-Za-z-]{10,}"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})", re.I)


def secret_re():
    """Secret deseni memory_hygiene'den paylaşılır (tek tanım, DRY)."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_mh", os.path.join(HERE, "memory_hygiene.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SECRET_RE
    except Exception:
        return _FALLBACK_SECRET


# Düz metin kimlik bilgisi/PII — sohbette geçebilir, diske GİRMEMELİ.
# (security-review bulgusu: memory_hygiene regex'i yalnız tırnaklı parolayı
# ve bilinen token biçimlerini yakalıyordu; "password: hunter2", "şifre X",
# TC kimlik no ve e-posta sızıyordu.)
PII_RE = re.compile(
    r"("
    # Türkçe ek alabilir: parola/parolam/parolası, şifre/şifresi/şifremiz…
    r"(?:parola|şifre|sifre|password|passwd|pwd|secret|api[\s_-]?key|token)\w*"
    r"\s*(?:[:=]|\s)\s*['\"]?\S{4,}"          # anahtar kelime + değer
    r"|\b\d{11}\b"                             # TC kimlik no
    r"|\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"        # e-posta
    r"|\b(?:\d[ -]?){13,19}\b"                # kart numarası benzeri dizi
    r")", re.I)


def temizle(text):
    """Secret + düz metin kimlik bilgisini gizle, uzunluğu kırp.

    Kayıt yerel ve gitignore'lu olsa bile veri sızdırmaz: makineye erişen
    biri bu dosyadan kimlik bilgisi toplayamamalı.
    """
    if not text:
        return text
    text = secret_re().sub("[gizlendi]", str(text))
    text = PII_RE.sub("[gizlendi]", text).strip()
    text = " ".join(text.split())
    return text[:INTENT_MAX] + "…" if len(text) > INTENT_MAX else text


def log_path(explicit=None, pdir=None):
    """Kayıt yolu: açık argüman > AURAS_EVENT_LOG env > proje varsayılanı.

    Env override'ın nedeni izolasyon: test ve `bin/validate.py` router'ı gerçek
    isteklerle koşturur; bu koşumlar kullanıcının aktivite kaydını KİRLETMEMELİ.
    """
    if explicit:
        return explicit
    env = os.environ.get("AURAS_EVENT_LOG")
    if env:
        return env
    base = pdir or os.environ.get("CLAUDE_PROJECT_DIR") or ROOT
    # YABANCI REPOYA YAZMA. Global router her projede çalışır; sisteme bağlı
    # olmayan bir repoya kayıt bırakmak orada untracked dosya üretir ve
    # sohbet metni yanlışlıkla commit'lenebilir (gerçek vaka: 4cast/4Flow).
    # Bağlı proje = kendi routing.yml'ini taşıyan proje.
    if os.path.isfile(os.path.join(base, ".agents", "routing.yml")):
        return os.path.join(base, DEFAULT_LOG)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", os.path.abspath(base)).strip("-")[-60:]
    return os.path.expanduser(os.path.join(
        "~", ".claude", "auras", "runtime", f"{slug or 'bilinmeyen'}.jsonl"))


def append(event, path=None):
    """Olayı JSONL'e ekle. Hata yutulmaz — çağıran karar verir (main yutar).

    Yazım KİLİTLİDİR: aynı kaydı birden çok oturum paylaşır (`.claude/worktrees/`
    altında eşzamanlı çalışma ölçüldü, 2026-08-15). O_APPEND küçük yazımları
    çekirdek tamponu içinde atomik tutar ama uzun satır tampon sınırını aşınca
    iki yazıma bölünür ve satırlar iç içe geçer; iç içe geçmiş satır JSON
    olarak okunamaz, yani KANIT SESSİZCE KAYBOLUR. Kilit yoksa (Windows,
    exotic fs) yazım yine yapılır — kayıt disposable'dır, kilit uğruna
    olayı düşürmek daha kötüdür.
    """
    path = path or log_path()
    rec = {k: v for k, v in event.items() if k in ALLOWED and v is not None}
    if "intent" in rec:
        # AURAS_LOG_INTENT=0 → istek metni hiç yazılmaz (en katı gizlilik);
        # skill/sınıf kaydı yine tutulur, tablo çalışmaya devam eder.
        if os.environ.get("AURAS_LOG_INTENT") == "0":
            rec.pop("intent")
        else:
            rec["intent"] = temizle(rec["intent"])
    rec["ts"] = dt.datetime.now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    satir = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        with _kilit(fh):
            fh.write(satir)
    return rec


@contextlib.contextmanager
def _kilit(fh):
    """Dosya kilidi; platform desteklemiyorsa sessizce kilitsiz devam eder."""
    try:
        import fcntl
    except ImportError:                                  # pragma: no cover
        yield
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    except OSError:                                      # pragma: no cover
        yield
        return
    try:
        yield
    finally:
        try:
            fh.flush()
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:                                  # pragma: no cover
            pass


def route_olayi(task_class, routed, extras, intent, session=None, log=None):
    """Yönlendirme kararını kayda yaz.

    `session` ZORUNLU alan değildir ama yazılmazsa kapı turu hangi oturumun
    açtığını bilemez ve eşzamanlı iki oturum birbirinin kanıtını sahiplenir
    (ölçüm 2026-08-15: 286 route olayının 0'ı session taşıyordu — alan
    ALLOWED listesindeydi, yazan yoktu).
    """
    return append({
        "kind": "route",
        "session": (session or "")[:8] or None,
        "task_class": task_class,
        "routed": routed,
        "extras": extras,
        "intent": intent,
    }, log)


# Test/doğrulama komutu imzaları — "test koştu mu" sorusunun cevabı.
TEST_CMD_RE = re.compile(
    r"(unittest|pytest|\bnpm (run )?test|yarn test|dotnet test|go test|vitest"
    r"|jest|playwright|cypress|selenium|puppeteer|validate\.py|scan_secrets\.py|check_citations\.py)", re.I)

# Çıkış kodunu taşıyabilecek alan adları — motorlar arasında ad değişir.
CIKIS_ALANLARI = ("exit_code", "exitCode", "returncode", "returnCode",
                  "exit_status", "status", "code")


def cikis_kodu(tool_response):
    """Payload'daki GERÇEK çıkış kodu (yoksa None).

    bool kabul edilmez: `True` çıkış kodu değildir, ona 1 muamelesi yapmak
    tam da kaçındığımız türden sessiz yanlış çıkarımdır.
    """
    for k in CIKIS_ALANLARI:
        v = tool_response.get(k)
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and re.fullmatch(r"-?\d{1,3}", v.strip()):
            return int(v.strip())
    return None


def test_gecti(tool_response):
    """Testin sonucu: True/False/None(bilinmiyor) — ÇIKIŞ KODUNDAN.

    Neden çıktı sözcüğü değil: 2026-08-07'de bu repoda canlı hook üstünde
    ölçüldü — `exit 1` ile dönen ama çıktısında "passed" geçen komut eski
    oracle'a göre GEÇTİ sayılıyordu. Yani "kapı test kanıtı istiyor" demek,
    pratikte "çıktıda 'OK' sözcüğü geçsin" demekti. Sözcük eşleşmesi
    oracle değildir; kanıt diye sunulması kanıtın kendisinden kötüdür.

    Kanıt yoksa cevap None'dur. Bu fonksiyon ASLA kanıtsız True dönmez.
    """
    if not isinstance(tool_response, dict):
        return None
    if tool_response.get("interrupted"):
        return None       # kullanıcı kesti → sonuç bilinmiyor, "geçti" değil
    kod = cikis_kodu(tool_response)
    return None if kod is None else kod == 0


# Test çağrısından SONRA gelirse çıkış kodunu TESTİN kodu olmaktan çıkaran
# kabuk yapıları. `&&` kasıtlı olarak yok: `a && b` a başarısızsa a'nın
# kodunu döndürür, yani başarısızlığı gizlemez.
MASKE_RE = re.compile(r"\|\||;|\|(?!\|)")


def kod_maskelendi(cmd):
    """Komutun çıkış kodu testin sonucunu temsil etmiyor mu?

    Bulgu (Codex, PR #15): çıkış kodu oracle'ı ancak çıkış kodu TESTİN
    kodu ise geçerlidir. `pytest || true` kabuktan 0 döner, testler
    kalmıştır. `pytest | tail` boruda son halkanın kodunu döndürür.
    Bu durumda doğru cevap "geçti" değil "bilinmiyor"dur.
    """
    if not cmd:
        return False
    son = None
    for son in TEST_CMD_RE.finditer(cmd):
        pass
    if son is None:
        return False
    kuyruk = cmd[son.end():]
    if "pipefail" in cmd:
        # pipefail açıkken boru başarısızlığı gizlemez; `||` ve `;` hâlâ gizler.
        return bool(re.search(r"\|\||;", kuyruk))
    return bool(MASKE_RE.search(kuyruk))


def bash_sonucu(tool_response, cmd=None, olay=None):
    """Canlı hook'tan (ok, kaynak). Kaynak kayda girer.

    Farklı güven seviyeleri karıştırılmamalıdır:

    "exit"  — payload gerçek çıkış kodunu taşıdı. En güçlü kanıt.
    "event" — hook OLAY TÜRÜ sonucu söylüyor: PostToolUseFailure = komut
              çöktü, PostToolUse = sıfırla çıktı. Claude Code sözleşmesi
              (2.1.220'de her iki olay da tanımlı).
    None    — komut kesildi, payload okunamadı ya da çıkış kodu
              maskelenmiş: bilinmiyor. "Geçti" ASLA varsayılan değildir.
    """
    # SIRA ÖNEMLİ: başarısızlık olayında payload `tool_response` yerine
    # `tool_error` taşıyabilir. Olayın kendisi zaten kanıt — önce ona bak,
    # yoksa kırmızı sonuç "payload okunamadı" diye sessizce kaybolur.
    if olay == "PostToolUseFailure":
        return False, "event"
    if not isinstance(tool_response, dict):
        return None, None
    if kod_maskelendi(cmd):
        return None, None
    ok = test_gecti(tool_response)
    if ok is not None:
        return ok, "exit"
    if tool_response.get("interrupted"):
        return None, None
    return True, "event"


# Atlama gerekçesi kodları — serbest metin değil, sayılabilir kategori.
SEBEPLER = ("misroute", "not_applicable", "unavailable", "user_override")


def hook_payload():
    try:
        return json.loads(sys.stdin.read() or "{}") or {}
    except (ValueError, AttributeError):
        return {}


def zaten_yuklendi(skill, log=None):
    """Bu turda (son 'stop'tan sonra) aynı skill zaten kaydedildi mi."""
    try:
        with open(log or log_path(), encoding="utf-8") as fh:
            satirlar = fh.readlines()[-200:]
    except OSError:
        return False
    gorulen = False
    for satir in satirlar:
        try:
            o = json.loads(satir)
        except ValueError:
            continue
        if o.get("kind") == "stop":
            gorulen = False
        elif o.get("kind") == "skill" and o.get("skill") == skill:
            gorulen = True
    return gorulen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True,
                    choices=("route", "skill", "subagent", "stop", "edit",
                             "bash", "ui", "skipped"))
    ap.add_argument("--skill", help="--kind skipped için: atlanan skill")
    ap.add_argument("--reason", choices=SEBEPLER,
                    help="--kind skipped için: sınırlı gerekçe kodu")
    ap.add_argument("--note", default=None, help="tek cümle açıklama")
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)

    try:
        data = hook_payload()
        ti = data.get("tool_input") or {}
        event = {"kind": args.kind, "session": (data.get("session_id") or "")[:8]}
        if args.kind == "skill":
            event["skill"] = ti.get("skill") or ti.get("name")
            if not event["skill"]:
                return 0  # adsız skill olayı bilgi taşımaz — gürültü yazma
            if zaten_yuklendi(event["skill"], args.log):
                return 0  # aynı turda ikinci yükleme: tekrar kaydetme
        elif args.kind == "edit":
            # Hangi dosya değişti — "kanıtsız bitiş" kapısının girdisi.
            event["file"] = ti.get("file_path") or ti.get("path")
            if not event["file"]:
                return 0
        elif args.kind == "bash":
            # Test/doğrulama komutu koştu mu ve GEÇTİ Mİ — beyan değil kanıt.
            cmd = (ti.get("command") or "")[:200]
            if not TEST_CMD_RE.search(cmd):
                return 0  # sıradan komut; gürültü yazma
            event["kind"] = "test"
            tam = ti.get("command") or ""      # maskeleme TAM komutta aranır
            event["cmd"] = cmd
            event["ok"], event["src"] = bash_sonucu(
                data.get("tool_response"), cmd=tam,
                olay=data.get("hook_event_name"))
        elif args.kind == "skipped":
            # Zorunlu skill yüklenmediyse gerekçe KAYDA girer. Bu bir kanıt
            # değil, denetlenebilir beyandır (Codex hükmü 2026-07-26):
            # "gerekçeli"yi "haklı" diye sunmak tiyatrodur.
            if not args.skill or not args.reason:
                return 0
            event["skill"] = args.skill
            event["reason"] = args.reason
            event["note"] = args.note
        elif args.kind == "ui":
            # Tarayıcıda gerçek etkileşim (tıklama/ekran görüntüsü) = kanıt.
            event["cmd"] = (data.get("tool_name") or "")[:80]
        elif args.kind == "subagent":
            event["agent"] = (ti.get("subagent_type") or ti.get("agentType")
                              or data.get("subagent_type"))
        append(event, args.log)
    except Exception:
        return 0  # hook asla bloklamaz
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
