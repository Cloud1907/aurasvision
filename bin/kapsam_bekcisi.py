#!/usr/bin/env python3
"""Kapsam bekçisi — hangi tests/*.py dosyası keşfe girmek ZORUNDA.

Neden ayrı modül: bu mantık kernel_dosyalari.py içinde doğdu ama oraya ait
değil. Orası "motorun hangi dosyaları var, proje sürümü kanoniğe göre nerede"
sorusunu cevaplar; burası "bir test dosyası sessizce kaybolmuş mu" sorusunu.
İkisi ayrı bekçi, ayrı test dosyası, ayrı değişme sebebi.

Kural tek cümle: eksilen test, kırmızı testten tehlikelidir. Kırmızı test
bağırır; keşfe girmeyen test hiç sayılmaz, çıkış kodu 0 kalır ve "Ran N"
daralmasını hiçbir satır söylemez. 2026-08-07 ölçümü: PyYAML'sız yorumlayıcıda
üç modül import'ta çöktü, süit 220 yerine 186 test saydı — 34 test yok olmuştu
ama çıktıda yalnız "3 hata" yazıyordu.
"""
import ast
import io
import os
import re
import tokenize

# Test taşıyan dosyanın imzası — VARSAYILAN "topla", istisna yazılır.
#
# Bu kural beş inceleme turunda beş kez sızdı (Codex, PR #26 ve #30): takma
# adlı taban (`Taban = unittest.TestCase`), `async def test_*`, dış dosyadan
# gelen taban, fixture string'i içindeki muafiyet işareti, `self` olmayan ilk
# parametre. Hepsinin tek bir kök nedeni vardı: METİN DESENİ, kodu koddan
# ayırt edemez. Her tur deseni biraz daha genişletmek yeni bir kaçak bıraktı.
#
# Çözüm deseni büyütmek değil, dili DİLİN KENDİ ARACIYLA okumaktır: yapı
# `ast`ten, yorumlar `tokenize`dan gelir. Bu sınıf kaçak böylece kapanır —
# string içeriği asla yorum, yorum asla kod sayılmaz.
#
# Varsayılan fail-closed: tests/ altında test metodu olan her dosya toplanmak
# ZORUNDADIR; kasıtlı yardımcı `# toplanmaz: <gerekçe>` yorumuyla muaf olur.
# Gerekçe zorunludur — susturma görünür bir karar olmalı (secret-allowlist
# ile aynı sözleşme).
_TOPLANMAZ = re.compile(r"^#[ \t]*toplanmaz:[ \t]*\S")


def _beyan_yorumlari(metin):
    """SÜTUN 0'daki gerçek yorum token'ları — dosya düzeyi beyanlar.

    İki filtre birden gerekli: `tokenize` string içeriğinin yorum sayılmasını
    engeller, sütun kısıtı da muafiyetin bir kod satırının kuyruğunda ya da
    metot gövdesinde KAZARA doğmasını engeller. Muafiyet dosya hakkında
    bilinçli bir beyandır; yan cümle olarak verilemez.
    """
    try:
        akis = tokenize.generate_tokens(io.StringIO(metin).readline)
        return [t.string for t in akis
                if t.type == tokenize.COMMENT and t.start[1] == 0]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return []


# Gövdesi başka gövdeler taşıyan ifadeler. Metot tanımı bilerek DIŞARIDA:
# içine inmek, bir metodun yerel `def test_*` yardımcısını metot sanardı.
#
# Liste tek tek sayılıyor çünkü kural "gövde taşıyan her ifade" — eksik kalan
# her üye bir kaçaktır. `Match` (3.10+) ve `TryStar` (3.11+) `getattr` ile
# alınır: eski yorumlayıcıda AttributeError yerine sessizce listeden düşerler,
# çünkü o sürümde o sözdizimi zaten yazılamaz.
_BLOK = tuple(t for t in (
    ast.If, ast.Try, ast.For, ast.AsyncFor, ast.While, ast.With,
    ast.AsyncWith, ast.ExceptHandler,
    getattr(ast, "Match", None), getattr(ast, "match_case", None),
    getattr(ast, "TryStar", None),
) if t is not None)
# Gövde taşıyan alan adları. `cases` match/case'e, `handlers` except'e ait.
_GOVDE_ALANI = ("body", "orelse", "finalbody", "handlers", "cases")


def _metot_adlari(govde):
    """Sınıf gövdesindeki metot adları — koşul bloklarına iner, metodun
    İÇİNE inmez.

    `ast.walk` iki yönü de kaçırırdı: düz `body` taraması `if`/`try` altındaki
    metodu göremez (yanlış negatif), tam walk ise metot içindeki yerel
    fonksiyonu metot sanar (yanlış pozitif). Doğru kapsam ikisinin arası.
    """
    for dugum in govde:
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield dugum.name
        elif isinstance(dugum, _BLOK):
            for alan in _GOVDE_ALANI:
                yield from _metot_adlari(getattr(dugum, alan, []))


def _testcase_tabanli(dugum):
    """Sınıfın tabanlarından biri `...TestCase` mi (nokta ya da düz ad)."""
    for taban in dugum.bases:
        ad = taban.attr if isinstance(taban, ast.Attribute) else \
            getattr(taban, "id", "")
        if "TestCase" in ad:
            return True
    return False


def _test_tasiyor(metin):
    """Dosya bir sınıf içinde test tanımlıyor mu (yapıdan, desenden değil).

    Ayrıştırılamayan dosya `True` sayılır: tests/ altındaki bozuk dosya zaten
    toplanamaz ve sessiz geçmemelidir (fail-closed).

    BEKÇİNİN SINIRI — statik olarak kapatılamaz: testlerin TAMAMINI dış bir
    tabandan miras alan ve kendisi hiçbir şey tanımlamayan sınıf
    (`from ortak import Taban; class X(Taban): pass`) görünmez. Bunu bilmek
    tabanı IMPORT etmeyi gerektirir; keşif dışı bir dosyayı import etmek ise
    kapının kendisini rastgele kod çalıştıran bir yüzeye çevirir — bedeli
    kazancından büyük. Kapıyı olduğundan güçlü yazmak yasak olduğu için
    (AGENTS.md, "Kapıların gerçek sınıfı") sınır burada yazılıdır: bu bekçi
    dosyanın KENDİ tanımladığı testleri görür, miras aldıklarını değil.
    """
    try:
        agac = ast.parse(metin)
    except (SyntaxError, ValueError):
        return True
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.ClassDef):
            continue
        if _testcase_tabanli(dugum):
            return True
        # Sınıf gövdesi düz liste değil ağaçtır (`if`/`try` altındaki metot da
        # testtir) ama metodun İÇİ sınıfın gövdesi değildir.
        if any(ad.startswith("test") for ad in _metot_adlari(dugum.body)):
            return True
    return False


# --- modül düzeyinde GÖRÜNÜR atlama: meşru mu, yoksa beyan mı ---------------
#
# Bir modülün başına `raise unittest.SkipTest("...")` yazmak, içindeki bütün
# testleri süitten çıkarır ve çıkış kodunu 0 bırakır. Keşif bekçisi bunu
# çökmeden ayırmayı öğrendikten sonra (PR #47) yeni bir sessizlik doğdu: HER
# atlama koşulsuz "ortam bağımlılığı" sayılıyordu. Yani kapı, kendi
# kapattığı kaçağın kapısını yeniden açıyordu — beyan kanıt yerine geçiyordu.
#
# Ölçüt bu yüzden dizge değil YOKLAMADIR: meşru atlamanın sebebi
# `tests/ortam.py`nin `MESRU_ATLAMALAR` kaydında ilan edilir ve kayıt her
# sebebi bir ön-koşul yoklamasına bağlar. Bekçi atlamayı ancak yoklama "bu
# makinede o bağımlılık gerçekten yok" derse meşru sayar. Kayıtlı bir sebebi
# kopyalayan modül, bağımlılığın VAR olduğu bir makinede blok alır.
#
# SINIR (abartma yasak — AGENTS.md, "Kapıların gerçek sınıfı"): bağımlılığın
# gerçekten eksik olduğu bir makinede kopyalanan sebep geçer. Orada iddia
# zaten doğrudur; bu bekçi yalanı değil, ortamla ÇELİŞKİYİ yakalar. Kazanç
# şudur: yeni bir meşru atlama, tek ve gözden geçirilen bir yerde ilan
# edilmeden var olamaz.
ATLAMA_MESAJI = {
    "kayitsiz": ("sebebi tests/ortam.py'deki MESRU_ATLAMALAR kaydında YOK — "
                 "modül düzeyinde atlama beyanla meşrulaşmaz; ön-koşulu "
                 "oraya yoklamasıyla birlikte yaz ya da atlamayı kaldır"),
    "yanlis": ("sebep kayıtlı ama bu makinede ön-koşul SAĞLANIYOR — atlamayı "
               "ortam açıklamıyor, testler koşmalı"),
    "okunamadi": ("tests/ortam.py'deki MESRU_ATLAMALAR kaydı okunamadı — "
                  "'okunamadı' ile 'meşru' aynı şey değildir (fail-closed)"),
}


def atlama_hukmu(atlanan, ortam_kaydi):
    """[(ad, sebep, hüküm)] — her modül atlaması ortam kaydına bağlanıyor mu.

    `atlanan`: keşfin bulduğu (modül adı, atlama sebebi) çiftleri.
    `ortam_kaydi`: {sebep: yoklama_sonucu} — `tests/ortam.py`nin ilan ettiği
    ön-koşullar, süitin KOŞTUĞU yorumlayıcıda yoklanmış hâliyle. True =
    bağımlılık gerçekten yok. `None` = kayıt okunamadı; hiçbir atlama meşru
    sayılmaz, çünkü okunamayan kayıt boş kayıt değildir.

    Hüküm "ortam" ise atlama meşrudur (bilgi satırı); diğer hepsi BLOK'tur ve
    gerekçesi `ATLAMA_MESAJI`de yazılıdır.
    """
    hukumler = []
    for ad, sebep in atlanan:
        if ortam_kaydi is None:
            hukum = "okunamadi"
        elif sebep not in ortam_kaydi:
            hukum = "kayitsiz"
        elif not ortam_kaydi[sebep]:
            hukum = "yanlis"
        else:
            hukum = "ortam"
        hukumler.append((ad, sebep, hukum))
    return hukumler


def toplanmayan_testler(kok, toplanan):
    """[dosya_adi] — TestCase tanımlayan ama keşfe HİÇ girmeyen tests/*.py.

    Neden bekçi: eksilen test, kırmızı testten daha tehlikelidir. Kırmızı test
    bağırır; keşfe girmeyen test hiç sayılmaz, çıkış kodu 0 kalır ve "Ran N"
    daralmasını hiçbir satır söylemez. 2026-08-07 ölçümü: PyYAML'sız
    yorumlayıcıda üç modül import'ta çöktü, süite 220 yerine 186 test saydı —
    34 test yok olmuştu ama çıktıda yalnız "3 hata" yazıyordu.

    `toplanan`: keşfin GERÇEKTEN test ürettiği modül adları (uzantısız).
    Test metodu OLMAYAN yardımcılar (ör. tests/ortam.py) zaten denetim
    dışıdır; test metodu taşıyan kasıtlı yardımcı, SATIR BAŞINA yazılmış
    `# toplanmaz: <gerekçe>` yorumuyla muaf olur. Gerekçesiz işaret ya da
    string literal içindeki metin muafiyet SAYILMAZ.
    """
    tests_dir = os.path.join(kok, "tests")
    if not os.path.isdir(tests_dir):
        return []
    eksik = []
    for f in sorted(os.listdir(tests_dir)):
        if not f.endswith(".py") or f[:-3] in toplanan:
            continue
        with open(os.path.join(tests_dir, f), encoding="utf-8",
                  errors="replace") as fh:
            metin = fh.read()
        if not _test_tasiyor(metin):
            continue
        if not any(_TOPLANMAZ.match(y) for y in _beyan_yorumlari(metin)):
            eksik.append(f)
    return eksik
