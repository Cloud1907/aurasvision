#!/usr/bin/env python3
"""Deterministik secret tarayıcı — sızmış kimlik bilgisini merge kapısına çevirir.

Verilen dosya veya dizinde yaygın secret desenlerini (API key, private key,
token, hardcoded parola, .env sızıntısı) regex ile tarar. Bulguyu
dosya:satır + kural adı ile raporlar. Bulgu varsa exit 1; temizse exit 0.

Kullanım:
  python3 scan_secrets.py <dosya|dizin> [<dosya|dizin> ...]
  python3 scan_secrets.py src/ config/app.py

Bağımlılıksız (yalnız stdlib). Yanlış-pozitifi azaltmak için örnek/placeholder
değerler (xx: your_key, example, changeme, <...>) elenir; yine de bir kanıt
sinyalidir, insan teyidi gerekir.
"""
import fnmatch
import os
import re
import subprocess
import sys

# Taranmayacak yollar (gürültü ve kendi kaynağımız).
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__",
             "dist", "build", ".mypy_cache", ".pytest_cache"}
# İkili/irrelevant uzantılar.
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
            ".gz", ".tar", ".woff", ".woff2", ".ttf", ".mp4", ".lock",
            # Derlenmiş çıktı: kaynağın ikili kopyası. Kaynağı zaten
            # tarıyoruz; ikilisini taramak AYNI bulguyu iki kez üretir ve
            # düzeltilemez bir konum gösterir (.pyc'yi düzeltemezsin).
            # 4cast'te commit'lenmiş tests/__pycache__/*.pyc push'u blokladı.
            ".pyc", ".pyo", ".class", ".dll", ".exe", ".so", ".dylib"}
MAX_BYTES = 2_000_000  # >2MB dosyayı atla (üretilmiş/ikili olasılığı)

# Placeholder / örnek işaretçileri: bunları içeren değer bulgu sayılmaz.
PLACEHOLDER = re.compile(
    r"(your[_-]?|example|sample|placeholder|changeme|dummy|redacted|"
    r"xxxx+|\.\.\.|<[^>]+>|\{\{|\$\{|test[_-]?key|fake)", re.I)

# Her kural: (ad, regex). regex bir "değer" grubu içerebilir (grup 1) ya da
# tamamı imza olabilir. Değer grubu varsa placeholder elemesi ona uygulanır.
RULES = [
    ("AWS Access Key ID",
     re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("AWS Secret Access Key",
     re.compile(r"(?i)aws.{0,20}?(?:secret|key).{0,3}['\"]([A-Za-z0-9/+=]{40})['\"]")),
    ("Private key blok",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("GitHub token",
     re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,255})\b")),
    ("Slack token",
     re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("Google API key",
     re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b")),
    ("Stripe secret key",
     re.compile(r"\b((?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,})\b")),
    ("OpenAI/Anthropic key",
     re.compile(r"\b(sk-(?:ant-)?[A-Za-z0-9_\-]{20,})\b")),
    ("JWT",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b")),
    ("Generic API key/token atama",
     re.compile(r"(?i)(?:api[_-]?key|secret|token|access[_-]?key|auth)"
                r"\s*[:=]\s*['\"]([A-Za-z0-9_\-/+=]{16,})['\"]")),
    ("Hardcoded parola",
     re.compile(r"(?i)(?:password|passwd|pwd|db[_-]?pass)"
                r"\s*[:=]\s*['\"]([^'\"\s]{6,})['\"]")),
    ("Bağlantı dizesinde parola",
     re.compile(r"(?i)(?:postgres|mysql|mongodb|redis|amqp)(?:ql)?://"
                r"[^:/\s]+:([^@/\s]{4,})@")),
]


def is_placeholder(text):
    return bool(PLACEHOLDER.search(text))


# Sır OLAMAYACAK değer biçimleri. Kural yanlış yakalıyorsa düzeltilecek yer
# KURALDIR, muafiyet listesi değil — muafiyet "bilinen sırrı affet" demektir,
# oysa burada ortada sır YOK. (4Flow kurulumu 2026-08-07: 6 dosya yalnız rota
# yolu ve değişken referansı yüzünden kapıya takıldı; her repoya muafiyet
# yazmak sorunu N kez taşımak olurdu.)
DEGER_DEGIL = (
    # Rota/URL yolu: "api/auth/change-password", "/account/reset-password"
    re.compile(r"^[./]*([\w.-]+/)+[\w.-]+$"),
    re.compile(r"^https?://"),
    # Değişken/şablon referansı: $Var, ${VAR}, {{ vault }}, %s, {0}, <VALUE>
    #
    # DİKKAT — bu desen DAR tutulmalı. İlk hâli `^[$%]` idi ve bcrypt
    # hash'ini ($2b$12$...) sessizce atlıyordu: `$` ile başlayan her şeyi
    # değişken sanmak, `$` ile başlayan gerçek sırları kör noktaya çevirir.
    # Artık yalnız TAM bir değişken ADI eşleşir; içinde `$` geçen değer değil.
    re.compile(r"^\$[A-Za-z_]\w*$"),
    re.compile(r"^%[A-Za-z]$"),
    re.compile(r"^\$?\{[^}]*\}$"),
    re.compile(r"^\{\{.*\}\}$"),
    re.compile(r"^<[^>]+>$"),
)


# Şablon dosyaları: adı gereği ÖRNEK değer taşırlar ve commit edilmeleri
# beklenir (.env.example standart konvansiyondur). Placeholder filtresi
# yalnız İngilizce kalıpları tanıyor; "yerel-parolasi" gibi yerelleştirilmiş
# doldurma metinleri kaçıyordu. Dosya adına bakmak daha güvenilir.
SABLON_DOSYA = re.compile(r"\.(example|sample|template|dist)$"
                          r"|\.(example|sample|template)\.[\w]+$", re.I)


def sablon_dosyasi(yol):
    return bool(SABLON_DOSYA.search(os.path.basename(yol)))


def deger_degil(text):
    """Eşleşen metin bir SIR olamayacak biçimde mi (yol, değişken, şablon)."""
    t = text.strip()
    return any(rx.search(t) for rx in DEGER_DEGIL)


# Şablon dosyalarında SUSTURULAN kurallar — yalnız düşük güvenli olanlar.
# Bir `.env.example`'da "buraya-parolani-yaz" beklenir; ama oraya YANLIŞLIKLA
# gerçek bir Stripe/AWS anahtarı yapıştırmak en sık görülen sızıntı biçimidir.
# Dosyayı tamamen atlamak o vakayı kör noktaya çevirirdi.
SABLONDA_SUSAN = {"Hardcoded parola", "Generic API key/token atama",
                  "Bağlantı dizesinde parola"}


def scan_line(line, sablon=False):
    """Bir satırda bulunan (kural, eşleşme) listesini döndür."""
    hits = []
    for name, rx in RULES:
        if sablon and name in SABLONDA_SUSAN:
            continue
        for m in rx.finditer(line):
            value = m.group(1) if m.groups() else m.group(0)
            if value and (is_placeholder(value) or deger_degil(value)):
                continue
            hits.append((name, value))
    return hits


def is_excluded(path, patterns):
    """Yol dışlama glob'larından birine uyuyor mu (normalize edilmiş '/' ile).

    normpath baştaki './'yi zaten atar. lstrip('./') KULLANILMAZ: karakter
    kümesi siler, önek değil — '.agents/...' yolunu 'agents/...' yapıp nokta
    ile başlayan desenleri sessizce eşleşmez kılıyordu (denetim bulgusu).
    """
    norm = os.path.normpath(path).replace(os.sep, "/")
    return any(fnmatch.fnmatch(norm, g) or fnmatch.fnmatch("./" + norm, g)
               for g in patterns)


def git_izlenen(kok):
    """Bir depodaki git-izlenen dosyalar (index). Depo değilse/hata olursa None.

    Çalışma ağacının tamamını taramak, .gitignore'lu yerel `.env.local`
    yüzünden push'u bloklar — kullanıcı `--no-verify` alışkanlığı edinir,
    kapı ölür. Bu mod o yanlış bloku keser.

    SINIR: kapsam INDEX'tir, push edilen commit ARALIĞI değil. Bir commit'te
    eklenip sonraki commit'te silinen secret burada görünmez — o vakayı
    pre-push'taki scan_gecmis.py (aralık taraması) yakalar; iki tarama
    birbirinin yerine geçmez.
    """
    try:
        p = subprocess.run(["git", "-C", kok, "ls-files", "-z"],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    ham = p.stdout.decode("utf-8", "replace").split("\0")
    return [os.path.join(kok, x) for x in ham if x]


def _atlanir(tam, exclude):
    return (os.path.splitext(tam)[1].lower() in SKIP_EXT
            or is_excluded(tam, exclude))


def _izlenen_dosyalar(p, exclude):
    """Yalnız git-izlenen dosyalar (push kapısı kapsamı)."""
    izlenen = git_izlenen(p)
    if izlenen is None:
        print(f"HATA: git deposu değil ya da git okunamadı: {p}",
              file=sys.stderr)
        return
    for tam in izlenen:
        if not _atlanir(tam, exclude) and os.path.isfile(tam):
            yield tam


def _agac_dosyalari(p, exclude):
    """Çalışma ağacının tamamı (izlenmeyenler dâhil)."""
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            tam = os.path.join(root, f)
            if not _atlanir(tam, exclude):
                yield tam


def iter_files(paths, exclude=(), git_only=False):
    kaynak = _izlenen_dosyalar if git_only else _agac_dosyalari
    for p in paths:
        if os.path.isfile(p):
            if not is_excluded(p, exclude):
                yield p
        elif os.path.isdir(p):
            yield from kaynak(p, exclude)
        else:
            print(f"UYARI: yol bulunamadı: {p}", file=sys.stderr)


def scan(paths, exclude=(), git_only=False):
    """(bulgular, taranan_dosya_sayısı).

    Sayı önemlidir: HİÇBİR dosya taranmadıysa sonuç 'temiz' DEĞİLDİR —
    çağıran bunu kullanım hatası olarak raporlamalı (denetim bulgusu:
    hatalı çağrı 'temiz ✓' diyip exit 0 dönüyordu).
    """
    findings = []
    taranan = 0
    for path in iter_files(paths, exclude, git_only):
        taranan += 1
        try:
            if os.path.getsize(path) > MAX_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                sablon = sablon_dosyasi(path)
                for i, line in enumerate(fh, 1):
                    for name, value in scan_line(line, sablon):
                        preview = value if len(value) <= 12 else value[:6] + "…" + value[-3:]
                        findings.append((path, i, name, preview))
        except (OSError, UnicodeError):
            continue
    return findings, taranan


MUAFIYET_DOSYA = os.path.join(".agents", "secret-allowlist.txt")


def muafiyet_yukle(kok, kapi="secret"):
    """(desenler, hata) — projenin kendi muafiyet listesi.

    Neden var (4Flow, 2026-08-07): projede meşru fixture olabiliyor
    (localhost'a dummy kullanıcı yaratan betikteki `password123`). Tarayıcının
    projeye özel çıkış yolu yoktu; proje ya kapıyı hiç geçemeyecek ya motor
    dosyasını çatallayacaktı — ikisi de yanlış.

    Biçim: her satır `yol-deseni  # gerekçe`. GEREKÇE ZORUNLUDUR. Sessiz
    susturma en tehlikeli muafiyettir: kapı durur ama kimse bilmez. Gerekçesiz
    satır kullanım hatasıdır (exit 2), "temiz" değildir.
    """
    yol = os.path.join(kok, MUAFIYET_DOSYA)
    if not os.path.isfile(yol):
        return [], None
    desenler = []
    try:
        with open(yol, encoding="utf-8") as fh:
            satirlar = fh.readlines()
    except OSError as e:
        return [], f"{MUAFIYET_DOSYA} okunamadı: {e}"
    for no, ham in enumerate(satirlar, 1):
        satir = ham.rstrip("\n")
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        if "#" not in satir:
            return [], (f"{MUAFIYET_DOSYA}:{no} gerekçe yok — her muafiyet "
                        f"satırı `yol  # neden` biçiminde olmalı. Sessiz "
                        f"susturma kabul edilmez.\n    {satir.strip()}")
        desen, _, gerekce = satir.partition("#")
        if not desen.strip():
            continue                      # yalnız yorum satırı
        # Kapı kapsamı: işaretsiz satır YALNIZ secret kapısına uygulanır.
        # Denetim bulgusu 2026-08-08: dosya iki kapı arasında ortaktı ve
        # "sır taraması için muaf" gerekçesiyle yazılan satır kişisel veri
        # kapısını da susturuyordu — yazan kişi ikinci kapıyı kapattığını
        # bilmiyordu. Bir kapının muafiyeti başka kapıyı kapatamaz.
        m = re.match(r"\s*kapı:\s*([\w]+)\s*(?:[—-]\s*)?(.*)$", gerekce)
        if m:
            hedef, gerekce = m.group(1).lower(), m.group(2)
        else:
            hedef = "secret"
        if not gerekce.strip():
            return [], (f"{MUAFIYET_DOSYA}:{no} gerekçe boş — neden muaf "
                        f"olduğunu yaz.\n    {satir.strip()}")
        if hedef in (kapi, "hepsi"):
            desenler.append(desen.strip())
    return desenler, None


def muafiyet_uygula(findings, kok, desenler):
    """(kalan, bastirilan) — muaf yollara düşen bulgular ayrılır."""
    if not desenler:
        return findings, []
    kalan, bastirilan = [], []
    for f in findings:
        rel = os.path.relpath(f[0], kok).replace(os.sep, "/")
        if any(fnmatch.fnmatch(rel, d) or fnmatch.fnmatch(f[0], d)
               for d in desenler):
            bastirilan.append(f)
        else:
            kalan.append(f)
    return kalan, bastirilan


KULLANIM = ("kullanım: scan_secrets.py [--git] [--exclude GLOB] "
            "<dosya|dizin> [...]")


def arguman_coz(argv):
    """(exclude, paths, git_only, hata_mesaji)."""
    exclude, paths, git_only = [], [], False
    i = 1
    while i < len(argv):
        if argv[i] == "--git":
            git_only = True
            i += 1
            continue
        if argv[i] == "--exclude":
            # Değersiz --exclude sessizce yol sanılıyordu → tarama boşa
            # düşüp "temiz ✓" veriyordu. Kapıda bu, sahte yeşildir.
            if i + 1 >= len(argv):
                return None, None, None, "HATA: --exclude bir GLOB ister\n" + KULLANIM
            exclude.append(argv[i + 1])
            i += 2
            continue
        paths.append(argv[i])
        i += 1
    if not paths:
        return None, None, None, KULLANIM
    return exclude, paths, git_only, None


def main(argv):
    # --exclude GLOB (tekrarlanabilir): kasıtlı fixture'ları dışarıda tutar.
    # Dışlama gate KONFİGÜNDE görünür olsun diye tarayıcıya gömülmez —
    # neyin taranmadığı gizli kalmamalı.
    exclude, paths, git_only, hata = arguman_coz(argv)
    if hata:
        print(hata, file=sys.stderr)
        return 2
    findings, taranan = scan(paths, exclude, git_only)

    # Proje muafiyeti: kök, taranan ilk yolun deposu/dizinidir.
    kok = (paths[0] if os.path.isdir(paths[0])
           else os.path.dirname(paths[0])) or "."
    desenler, hata = muafiyet_yukle(kok)
    if hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2
    findings, bastirilan = muafiyet_uygula(findings, kok, desenler)

    if not taranan:
        # "Hiç dosya taranmadı" ASLA "temiz" değildir: yanlış yol, fazla
        # geniş dışlama ya da bozuk kurulum — hepsi kapıyı kör eder.
        print("HATA: hiçbir dosya taranmadı (yol yanlış ya da dışlama çok "
              "geniş) — bu 'temiz' DEĞİLDİR", file=sys.stderr)
        return 2
    # Bastırılan bulgu SESSİZ KAYBOLMAZ — neyin taranmadığı görünür olmalı.
    if bastirilan:
        print(f"scan_secrets: {len(bastirilan)} bulgu proje muafiyetiyle "
              f"bastırıldı ({MUAFIYET_DOSYA}):")
        for path, line, name, _p in bastirilan:
            print(f"  muaf: {path}:{line}  [{name}]")
    if not findings:
        print(f"scan_secrets: temiz — {taranan} dosya tarandı, secret "
              "deseni bulunamadı ✓")
        return 0
    print(f"scan_secrets: {len(findings)} olası secret bulundu ✗")
    for path, line, name, preview in findings:
        print(f"  {path}:{line}  [{name}]  → {preview}")
    print("SONUÇ: FAIL — secret'ı kaldır, geçmişten temizle, anahtarı döndür (rotate).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
