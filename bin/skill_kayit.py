#!/usr/bin/env python3
"""Skill kaydı — "bu skill kurulu mu" ve "hangi izin sınırına ait".

Router'ın yönlendirme mantığından ayrı tutulur: burası TABLO değil ENVANTER
sorusu sorar. Otorite capability profilidir (AGENTS.md: profil izin sınırı,
routing o sınır içinden seçim); dolayısıyla bir skill'in görev sınıfını
profil söyler, tetik kelimeleri değil.
"""
import os

# Kanonik kernel kökü: proje kendi profillerini taşımıyorsa buraya düşülür
# (routing tablosunda zaten aynı sıra geçerli — bkz. route.routing_path).
KANONIK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def skill_installed(skill, pdir):
    """Skill bu projede ya da kullanıcı-global dizinde kurulu mu."""
    for base in (os.path.join(pdir, ".agents", "skills"),
                 os.path.join(pdir, ".claude", "skills"),
                 os.path.expanduser("~/.claude/skills")):
        if os.path.isdir(os.path.join(base, skill)):
            return True
    return False


def skill_task_class(skill, pdir):
    """Skill'in görev sınıfı (belirlenemiyorsa None).

    Kaynak sırası: (1) `routing.yml`'deki İLK kural — yazarın açık beyanı,
    (2) skill tam olarak BİR profilde geçiyorsa o profilin sınıfı. İkisi de
    belirsizse None. Bilinmeyen skill'de de None döner; çağıran o zaman
    zorunluluk iddia etmez, çünkü sınıfı uydurmak izin sınırını uydurmaktır.

    Profil hâlâ İZİN sınırıdır (`skill_izinli`, `sinifta_izinli`) ama SINIFIN
    otoritesi değildir: bir skill birden çok sınıfta izinli olabilir ve
    izinden sınıf türetmek yapısal olarak belirsizdir (bkz. aşağıdaki ölçüm).

    Proje profilleri YOKSA kanonik profillere düşülür. Önyükleme durumu:
    repoyu sisteme bağlayan skill, henüz `.agents/`ı olmayan repoda çağrılır;
    orada sınıfsız kalmak dosya yazan işi salt-okunur profile mahkûm ederdi.

    Yedek yalnız YOKLUK içindir, EKSİKLİK için değil: profili olan proje bir
    skill'i bilinçli dışarıda bırakmış olabilir. O durumda kanoniğe düşmek,
    yerel capability kısıtlamasını sessizce geçersiz kılardı — profilin
    otoritesi projede kalır.

    HER profilde izinli skill de None döner ama anlamı farklıdır: o bir
    meta-skill'dir (ör. aurasprime — işi kendi yapmaz, dağıtır) ve sınıfı
    işten gelir. Sınıfı kilitlemek, devrettiği kod işini salt-okunur profile
    mahkûm ederdi. İzinli mi sorusu ayrı fonksiyondadır (`skill_izinli`);
    ikisini karıştırmak "her yerde izinli"yi "hiçbir yerde izinli değil"
    sanmaya yol açar.
    """
    try:
        import yaml  # route.load_rules ile aynı biçim: yoksa sessiz çekil
    except ImportError:
        return None
    kok = pdir if _profil_dizini_var(pdir) else KANONIK
    # 1) routing.yml — YAZARIN beyanı. Sıra oradaki insan kararıdır.
    #
    # Önceki ölçü yalnız profillere bakıyordu ve birden çok profilde geçen
    # skill için `sinirlar[0]`ı döndürüyordu — yani DOSYA ADI ALFABESİNDEN
    # gelen bir sınıf. Dördüncü profil (`design.yml`) eklenince iki sessiz
    # kayma ölçüldü (2026-08-16): `research-with-evidence` incident → design,
    # `security-review` None → code-change; ikisi de o profillere hiç
    # dokunulmadan, yalnızca yeni bir dosya sıraya girdiği için. Aynı şans
    # `implement-change`i de "code-change" yapıyordu (c < i).
    #
    # Profil İZİN sınırıdır ve bir skill birden çok sınıfta izinli olabilir;
    # izinden sınıf türetmek yapısal olarak belirsizdir. `routing.yml` ise
    # sınıfı AÇIKÇA beyan eder ve gözden geçirilmiş bir dosyadır.
    sinif = _routing_sinifi(skill, kok, yaml)
    if sinif:
        return sinif
    # 2) Kuralı olmayan skill: tam olarak BİR profilde geçiyorsa sınıf odur.
    #    Birden çoksa sınıf yoktur — "sınıfı uydurmak izin sınırını uydurmaktır".
    sinirlar, _toplam = _profil_siniflari(skill, kok, yaml)
    return sinirlar[0] if len(sinirlar) == 1 else None


def skill_izinli(skill, pdir):
    """Skill en az bir capability profilinde izinli mi (sınır sorusu)."""
    try:
        import yaml
    except ImportError:
        return False
    kok = pdir if _profil_dizini_var(pdir) else KANONIK
    return bool(_profil_siniflari(skill, kok, yaml)[0])


def sinifta_izinli(skill, task_class, pdir):
    """Skill, verilen sınıfın profilinde izinli mi (eskalasyon sınırı)."""
    try:
        import yaml
    except ImportError:
        return False
    kok = pdir if _profil_dizini_var(pdir) else KANONIK
    return task_class in _profil_siniflari(skill, kok, yaml)[0]


def profil_disinda(skill, pdir):
    """Sistemin YÖNETTİĞİ bir skill, otoriter profilde dışarıda mı bırakılmış?

    Üç durumu ayırır:
      - yönetilmeyen skill (eklenti/global, `.agents/skills` altında yok)
        → False: kapsam dışıdır, dışlama değil. /dataviz'i reddetmek
        router'ı kullanıcının aracına karşı çalıştırmak olurdu.
      - yönetilen ve profilde → False.
      - yönetilen ama profilde YOK → True: bilinçli dışlama. "Kullanıcı
        istedi, yükle" demek kısıtlamayı tavsiyeye çevirir.

    Senkron etkileşimi (ADR-0002): /auras yerel üretilmiş profili EZMEZ,
    yani kanoniğe yeni eklenen bir üyelik bağlı projeye kendiliğinden
    gitmez. Bu kasıtlıdır — sınırın sahibi projedir — ve sonucu artık
    görünür: o projede komut sessizce zorunlu kılınmaz, "izin sınırı
    dışında" denir. Üyelik gerekiyorsa projenin profiline reviewed PR ile
    eklenir.
    """
    kok = pdir if _profil_dizini_var(pdir) else KANONIK
    yonetilen = (os.path.isdir(os.path.join(kok, ".agents", "skills", skill))
                 or os.path.isdir(os.path.join(KANONIK, ".agents", "skills",
                                               skill)))
    if not yonetilen:
        return False
    return not skill_izinli(skill, pdir)


def _profil_dizini_var(kok):
    """Kökün kendi capability profilleri var mı (tek .yml yeter)."""
    pd = os.path.join(kok, ".agents", "capability-profiles")
    try:
        return any(ad.endswith(".yml") for ad in os.listdir(pd))
    except OSError:
        return False


SALT_OKUNUR_VARSAYILAN = frozenset({"research"})


def salt_okunur_siniflar(pdir):
    """Dosya sistemine YAZMAYAN sınıflar — profilin kendi beyanından.

    Kaynak `tools.filesystem == "read-only"`; sabit liste DEĞİL. Sabit liste
    tam da bu sorunu doğurdu: `niyet.py` `"research"`i tek salt-okunur sınıf
    sayıyordu ve `design` açılınca (o da read-only) okuma niyetli design
    kuralı `research`e düşürülüp aracını kaybediyordu (ADR-0005 §5).

    Ölçüm yoksa EN KISITLI varsayıma düşer (`{"research"}`): bilinmeyen bir
    sınıfı "yazmıyor" saymak, kapıyı ölçmediği şey için gevşetmek olurdu.
    """
    try:
        import yaml
    except ImportError:
        return SALT_OKUNUR_VARSAYILAN
    # pdir None gelebilir (router yolu): burada çökmek router'ı bloklardı.
    kok = pdir if (pdir and _profil_dizini_var(pdir)) else KANONIK
    pd = os.path.join(kok, ".agents", "capability-profiles")
    bulunan = set()
    try:
        adlar = sorted(os.listdir(pd))
    except OSError:
        return SALT_OKUNUR_VARSAYILAN
    for ad in adlar:
        if not ad.endswith(".yml"):
            continue
        try:
            with open(os.path.join(pd, ad), encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            continue
        if (data.get("tools") or {}).get("filesystem") == "read-only":
            bulunan.add(data.get("task_class"))
    return frozenset(bulunan) or SALT_OKUNUR_VARSAYILAN


def _routing_sinifi(skill, kok, yaml):
    """routing.yml'de bu skill'e ait İLK kuralın task_class'ı (yoksa None).

    "İlk" dosya sırasıdır ve bu bilinçlidir: `routing.yml` elle yazılan,
    gözden geçirilen bir tablodur — sırası yazarın kararıdır. Aynı skill'in
    ikinci kuralı ikincil bağlamdır (ör. `implement-change` önce code-change,
    sonra incident); birincisi varsayılan sınıftır.
    """
    yol = os.path.join(kok, ".agents", "routing.yml")
    try:
        with open(yol, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except (OSError, ValueError):
        return None
    for kural in cfg.get("rules") or []:
        if isinstance(kural, dict) and kural.get("skill") == skill:
            return kural.get("task_class")
    return None


def _profil_siniflari(skill, kok, yaml):
    """Skill'i izinli sayan TÜM profillerin sınıfları (dosya adı sırasıyla)."""
    pd = os.path.join(kok, ".agents", "capability-profiles")
    try:
        adlar = sorted(os.listdir(pd))
    except OSError:
        return [], 0
    bulunan, toplam = [], 0
    for ad in adlar:
        if not ad.endswith(".yml"):
            continue
        # Dar except BİLİNÇLİ: geniş `except Exception` bir NameError'ı
        # sessizce yutup bu fonksiyonu hep None döndürmüştü — profil
        # otoritesi hiç çalışmadı, kimse görmedi (inceleme 11. tur).
        try:
            with open(os.path.join(pd, ad), encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            continue
        toplam += 1
        if skill in (data.get("skills") or []):
            bulunan.append(data.get("task_class"))
    return bulunan, toplam


def kuralsiz_komut_kurali(explicit, pdir):
    """Kuralsız ama kurulu bir /komut için sentetik kural (değilse None).

    Kullanıcı komutla seçimini yapmışken anahtar kelimeyle başka skill'i
    zorunlu kılmak, açık iradeyi ezmektir. Sınıf profilden gelir: komut,
    izin sınırını düşürmemeli — dosya yazan skill'i salt-okunur profile
    mahkûm etmek işi sessizce kırar.

    Risk de taşınır: aynı işi yapan iki komuttan birinin approval
    diğerinin auto sayılması, riski komut seçimine bağlardı. Kuralsız
    skill'in beyan edilmiş riski olmadığından KATI taraf seçilir — research
    dışı her sınıf approval (fazla temkin, eksik temkinden iyidir).

    Profilde OLMAYAN skill (ör. yalnız kullanıcı-global dizinde duran üçüncü
    taraf skill) zorunlu kılınmaz: sınırı tanımlı değilse sınıfını ve riskini
    uydurmak, izin sınırının kendisini uydurmaktır. Router yine "kullanıcı
    açıkça /X istedi" der — çağrı kaybolmaz, yalnız zorunluluk iddia edilmez.

    Meta-skill (her profilde izinli) sınıfını işten alır: kural üretilir ama
    `task_class` boş bırakılır, çağıran kelime puanlamasının sınıfını korur.
    """
    if not (explicit and skill_installed(explicit, pdir)):
        return None
    if not skill_izinli(explicit, pdir):
        return None
    sinif = skill_task_class(explicit, pdir)
    return {"skill": explicit, "task_class": sinif,
            "risk": "auto" if sinif == "research" else "approval"}
