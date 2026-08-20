#!/usr/bin/env python3
"""Motor (kernel) dosyalarının TEK tanımı + kanonik↔proje karşılaştırması.

Kapsam DIŞI (2026-08-16'da ayrıldı, ikisi de burada kiracıydı): kurulum
kaynağının tazeliği `bin/kaynak.py`, gitleaks yanlış-pozitif muafiyeti
`bin/gitleaks_muaf.py`. İkisi de bu dosyanın docstring'inde hiç anılmıyordu —
adı konmamış sorumluluk, dosyayı sessizce eşiğe (400/400) dayamıştı.

Neden tek tanım: liste iki yerde yaşıyordu (auras-init.sh içi + validate.py
bekçisi) ve üçüncüsü geri-taşımada gerekiyordu. Üç kopya = sürüklenme; tek
tanım + bekçi (validate.py test_onboarding_parity) ile sürüklenme yapısal
olarak imkânsızlaşır.

Neden sınıflandırma git geçmişine bakar: `.kernel-manifest.json`ın "el
değmemiş" demesi YETMEZ. 2026-08-05 bulgusu: 4cast'te manifest projenin kendi
içeriğini kaydetmişti; /auras `bin/kapi.py`'deki yerel düzeltmeyi "temiz" sanıp
sessizce ezecekti. Güvenilir ayraç şudur — hedefin içeriği kanonik geçmişte
HİÇ görülmediyse o yerel iştir; ezilemez, yukarı taşınır.

Kullanım (kütüphane):
    import kernel_dosyalari as kd
    for rel, sinif in kd.karsilastir(kanonik, hedef): ...
"""
import hashlib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Kurulum kimliği ayrı modülde (bin/manifest.py): "hangi dosyalar motorun"
# ile "hangi sürüm kurulu" ayrı sorulardır. Buradan yeniden dışa verilir ki
# çağıranlar (auras-init.sh, testler) tek import yüzeyi görsün.
from manifest import (MANIFEST_SURUM, kurulu_surum,  # noqa: E402,F401
                      manifest_dosyalari, manifest_govde)
# Kurulumun iki ayrı sorusu ayrı modüllerde; import yüzeyi TEK kalsın diye
# buradan yeniden dışa verilir (auras-init.sh ve validate.py `kd.<ad>` çağırır).
from kaynak import kaynak_tazele, FETCH_ZAMAN, git as _git  # noqa: E402,F401
from gitleaks_muaf import (GITLEAKS_CFG, MUAFIYET_BLOGU,  # noqa: E402,F401
                           gitleaks_kullaniyor, manifest_muaf_mi)

# Motorun dosyaları — projenin değil. Her /auras koşumunda senkronlanır.
MOTOR = [
    "bin/validate.py", "bin/make_evidence.py", "bin/route.py",
    "bin/enjekte.py",       # route.py'nin enjeksiyon metni (import'ta şart)
    "bin/skill_kayit.py", "bin/davranis.py", "bin/secim.py",   # route.py'nin bağımlılığı — birlikte taşınmalı
    "bin/niyet.py",         # route.py'nin niyet kapısı — taşınmazsa kapı susar
    "bin/anma.py",          # niyet.py'nin alıntı/anma ayrımı
    "bin/manifest.py",      # kurulum kimliği (provenance)
    "bin/memory_hygiene.py", "bin/hatirla.py", "bin/run_event.py", "bin/durum.py",
    "bin/kapi.py", "bin/araclar.py", "bin/kernel_dosyalari.py",
    "bin/anlik.py",         # kapı'nın worktree ölçüsü — taşınmazsa kabuk
                            # yazımları bağlı projede yine görünmez olur
    "bin/yetki.py",         # profil → motor izin politikası; taşınmazsa
                            # bağlı projede profil yine yalnız beyan kalır
    "bin/kapsam_bekcisi.py",
    "bin/dogrula_ci.py",    # validate.py'nin CI/kanıt doğrulayıcıları
    "bin/dogrula_sema.py",  # görev sınıfı sözleşmesi + sınıf listesinin tek tanımı
    "bin/kalite.py",
    "bin/kalite_rapor.py",  # kalite.py'nin insan raporu (import'ta şart)
    "bin/olukod.py",     # ölü kod tespiti — kalite.py'nin bağımlılığı
    "bin/marj.py",       # eşiğe yakınlık pusulası — kalite.py import eder
    "bin/diller.py",        # dil kapsamının tek tanımı — kapılar buradan okur
    "bin/yuzey.py",         # yol → yükümlülük sınıflandırması (kapi.py'nin ölçüsü)
    "bin/contract.py",      # incele.py'nin contract okuması
    "bin/auras_geri.py", "bin/incele.py", "bin/hukum.py",
    "bin/kaynak.py",        # kurulum kaynağının tazeliği (ADR-0002)
    "bin/gitleaks_muaf.py",  # tarayıcı yanlış-pozitif muafiyeti
    "bin/yorum.py",         # incele.py'nin PR yorum gövdesi (import'ta şart)
    "bin/surec.py",
    "bin/tur.py", "bin/risk.py",   # incele.py'nin bağımlılıkları — birlikte taşınmalı
    "bin/codex-review.sh",
    "bin/kopru.py",         # kanıt köprüsü; taşınmazsa kotası biten proje bloke
                            # kalır ve public-repo reddi elle keşfedilmek zorunda
    "bin/install-hooks.sh", "bin/hooks/pre-push",
    "schemas/evidence.schema.json",
    ".github/workflows/evidence.yml",
    ".github/ISSUE_TEMPLATE/work-contract.yml",
    ".agents/routing.yml",
    ".agents/routing-eval.yml",   # yönlendirme doğruluğunun ölçülen hâli;
                                  # taşınmazsa bağlı projede eval koşamaz
    ".agents/mcp.yml",            # MCP sunucu kaydı — skill'lerle aynı yönetim;
                                  # taşınmazsa bağlı proje MCP'yi yönetemez
    # Motorun kendi kapsamı hakkındaki beyanı. Her projeye gitmeli: kullanıcı
    # hangi aşamada kapı OLMADIĞINI bilmeden korunduğunu sanır. Ayrıca
    # tests/test_evidence_workflow.py bu belgeyi şart koşuyor ve o test her
    # projeye taşınıyor — belge gitmezse kurulum kırmızı başlar (4Flow, 2026-08-07).
    "docs/yasam-dongusu-kapsami.md",
]
# Dizin olarak senkronlananlar (içerik tamamen motorun)
MOTOR_DIZIN = [".agents/skills", ".agents/capability-profiles", "tests",
               ".claude/rules"]

SINIFLAR = ("yok", "ayni", "geride", "yerel")

# Motorla senkronlanmaz ama kurulumdan SONRA projede bulunur:
# bir kez yazılan proje dosyaları (copy_new) ve kurucunun ürettikleri.
PROJE_DOSYASI = ("AGENTS.md", "CLAUDE.md")
URETILEN = (".agents/kalite-baseline.json",
            # Kurucu üretir: hook'lar birleştirilir (auras-init.sh) ve yetki
            # politikası yazılır (bin/yetki.py --uygula). Projede kurulumdan
            # SONRA bulunur, motor listesinde değildir — projenin dosyasıdır.
            ".claude/settings.json",
            # yetki.py --uygula üretir; kayıt + profil kesişiminden gelir
            ".mcp.json")

# tests/ içinde `os.path.join(ROOT, "a", "b")` biçimindeki dosya bağımlılığı
_ROOT_YOLU = re.compile(r"os\.path\.join\(\s*ROOT\s*,\s*((?:\"[^\"]+\"\s*,?\s*)+)\)")


def yol_coz(kok, rel):
    """Göreli yolu diskte BÜYÜK/küçük harf duyarsız çözer (yoksa None).

    Neden gerekli: projelerin dizin adlandırması farklı (4cast `Docs/`
    kullanıyor, motor `docs/` yazıyor). macOS/Windows dosya sistemi
    duyarsız olduğu için yerelde sorun çıkmıyor ama git yolu YAZILDIĞI
    gibi saklıyor; Linux CI'da dosya "yok" görünüyor ve kapı yanlış yere
    kırmızı yanıyor (4cast, 2026-08-07). Aynı repo platforma göre farklı
    davranıyorsa, bu taşınabilirlik hatasıdır.
    """
    tam = os.path.join(kok, rel)
    if os.path.exists(tam):
        return tam
    parcalar = rel.replace("\\", "/").split("/")
    simdi = kok
    for parca in parcalar:
        try:
            girisler = os.listdir(simdi)
        except OSError:
            return None
        esles = [g for g in girisler if g.lower() == parca.lower()]
        if not esles:
            return None
        simdi = os.path.join(simdi, esles[0])
    return simdi


def kurulumda_bulunur(rel):
    """Bu göreli yol, taze bir kurulumdan sonra projede bulunur mu?"""
    if rel in MOTOR or rel in PROJE_DOSYASI or rel in URETILEN:
        return True
    return any(rel == d or rel.startswith(d + "/") for d in MOTOR_DIZIN)


def eksik_test_bagimliliklari(kok):
    """[(test_dosyasi, rel)] — taşınan testin istediği ama taşınmayan yollar.

    Neden: `tests/` bir motor dizinidir, yani her test her projeye gider.
    Test ROOT'a göre bir dosya şart koşuyorsa o dosya da gitmeli. 2026-08-07'de
    4Flow kurulumunda bizzat oldu: KapsamSiniriTest her projeye taşındı ama
    şart koştuğu `docs/yasam-dongusu-kapsami.md` motor listesinde yoktu —
    yeni proje kurulumdan KIRMIZI çıktı. Kutudan kırmızı çıkan kurulum,
    insana kapıyı baştan yok saymayı öğretir.

    Yalnız kanonikte GERÇEKTEN var olan ve dosya olan yollar denetlenir:
    üretilen/geçici yollar ile yol kökü olarak kullanılan dizinler (ör. "bin")
    bir kurulum bağımlılığı değildir.

    Çıkış yolu: dosyanın başına `# kanonik-özel: <sebep>` yazan test denetim
    dışıdır. Bazı testlerin bağlı projede karşılığı YOKTUR (ör. kurucunun
    kendisi projeye taşınmaz) — o testler bağlı projede atlanmalı, kırmızı
    vermemeli. İşaret gerekçesiyle birlikte GÖRÜNÜR olsun diye zorunlu.
    """
    tests_dir = os.path.join(kok, "tests")
    if not os.path.isdir(tests_dir):
        return []
    eksik = []
    for f in sorted(os.listdir(tests_dir)):
        if not f.endswith(".py"):
            continue
        with open(os.path.join(tests_dir, f), encoding="utf-8") as fh:
            icerik = fh.read()
        if "kanonik-özel:" in icerik:
            continue
        for m in _ROOT_YOLU.finditer(icerik):
            rel = "/".join(re.findall(r"\"([^\"]+)\"", m.group(1)))
            tam = os.path.join(kok, rel)
            if not os.path.isfile(tam):
                continue
            if not kurulumda_bulunur(rel):
                eksik.append((f, rel))
    return eksik


def sha(yol):
    with open(yol, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def dosyalar(kok, rel):
    """rel bir dosyaysa kendisini, dizinse altındaki dosyaları verir."""
    tam = os.path.join(kok, rel)
    if os.path.isfile(tam):
        yield rel
    elif os.path.isdir(tam):
        for dizin, _alt, isimler in os.walk(tam):
            for i in isimler:
                if i.endswith(".pyc") or "__pycache__" in dizin:
                    continue
                yield os.path.relpath(os.path.join(dizin, i), kok)


def motor_dosyalari(kok):
    """Bir kökteki tüm motor dosyalarının göreli yolları (sıralı, tekrarsız)."""
    bulunan = set()
    for giris in MOTOR + MOTOR_DIZIN:
        bulunan.update(dosyalar(kok, giris))
    return sorted(bulunan)


MANIFEST_REL = ".agents/.kernel-manifest.json"
def gecmis_blob_idler(kanonik, rel):
    """rel için kanonik git geçmişindeki TÜM sürümlerin blob id'leri.

    None döner = geçmiş okunamadı (git yok / dosya hiç izlenmemiş). Çağıran
    bunu 'bilinmiyor' sayıp temkinli davranmalı (yerel kabul et).
    """
    log = _git(kanonik, "log", "--format=%H", "--", rel)
    if log is None:
        return None
    commitler = [c for c in log.split() if c]
    if not commitler:
        return set()
    istek = "".join(f"{c}:{rel}\n" for c in commitler)
    cikti = _git(kanonik, "cat-file", "--batch-check=%(objectname)",
                 girdi=istek)
    if cikti is None:
        return None
    return {s for s in cikti.split() if len(s) == 40}


def blob_id(yol):
    """Bir dosyanın git blob id'si (repo gerektirmez)."""
    try:
        p = subprocess.run(["git", "hash-object", yol], capture_output=True,
                           text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def sinifla(kanonik, hedef, rel):
    """Hedefteki motor dosyasının kanoniğe göre durumu.

    yok    — hedefte dosya yok (kurulacak)
    ayni   — içerik kanonikle birebir
    geride — içerik kanoniğin ESKİ bir sürümü (güvenle güncellenebilir)
    yerel  — içerik kanonik geçmişte hiç görülmedi → YEREL İŞ, ezilemez
    """
    k_yol, h_yol = os.path.join(kanonik, rel), os.path.join(hedef, rel)
    if not os.path.isfile(h_yol):
        return "yok"
    if os.path.isfile(k_yol) and sha(k_yol) == sha(h_yol):
        return "ayni"
    gecmis = gecmis_blob_idler(kanonik, rel)
    if gecmis is None:
        return "yerel"          # geçmiş bilinmiyor → temkinli: koru
    return "geride" if blob_id(h_yol) in gecmis else "yerel"


def karsilastir(kanonik, hedef):
    """[(rel, sinif)] — iki kökün motor dosyalarının birleşimi üstünde."""
    rel_ler = set(motor_dosyalari(kanonik)) | set(motor_dosyalari(hedef))
    return [(rel, sinifla(kanonik, hedef, rel)) for rel in sorted(rel_ler)]
