#!/usr/bin/env python3
"""İnceleme çıktısının hüküm sözleşmesi — ayrıştırma ve tutarlılık.

Neden ayrı modül: `incele.py` merge KARARINI verir (risk sınıfı, CI, git
işlemleri); burası yalnız "inceleyici ne dedi ve dediği kendisiyle tutarlı
mı" sorusunu cevaplar. İkisi ayrı değişme sebebi, ayrı test dosyası.

Sözleşme `bin/codex-review.sh` içinde yazılıdır ve tek satırdır:
    SONUC: TEMIZ            |  SONUC: N bulgu (en yuksek: PX)
Bu modül o iki biçimi BEYAZ LİSTE olarak uygular. Tanınmayan her hüküm
okunamamış sayılır — "okunamadı" ile "temiz" aynı şey değildir.
"""
import re
import unicodedata

# --- Codex çıktısını ayrıştır ---------------------------------------------
BULGU = re.compile(r"\[\s*(P[012])\s*\]\s*(.+)")
# Hüküm KENDİ SATIRINDA olmalı. Sabitlenmemiş desen, inceleyicinin düz
# metin içindeki ANIŞINI ("beklenen biçim: SONUC: TEMIZ") geçerli hüküm
# sayıyordu — inceleme tamamlanamamışken bile "temiz" üretilebiliyordu.
# Boşluk sınıfı SATIR İÇİYLE sınırlı (`[ \t]`, `\s` değil): `\s*` satır
# sonunu da yiyor ve çok satırlı ÇELİŞKİLİ hükmü ilk parçasından
# okuyordu — `SONUC:\nTEMIZ\nDEGIL` bulgusuz çıktıda "temiz" sayılıyordu.
SONUC = re.compile(r"^[ \t]*SONU[CÇ][ \t]*:[ \t]*(.+)$", re.I | re.M)


def bulgulari_ayikla(metin):
    """(bulgular, sonuc_satiri, okunabildi).

    okunabildi=False ise karar ENGEL olur: "ayrıştıramadım" ile "temiz"
    aynı şey DEĞİLDİR. Sessiz geçiş bu sistemin en sık hatası.
    """
    bulgular = {"P0": [], "P1": [], "P2": []}
    for satir in (metin or "").splitlines():
        m = BULGU.search(satir)
        if m:
            bulgular[m.group(1)].append(m.group(2).strip()[:160])
    # TEK hüküm satırı şart. `search` İLK eşleşmeyi alıyordu, yani sonraki
    # ÇELİŞEN hüküm sessizce yok sayılıyordu (`SONUC: 1 bulgu` + `SONUC:
    # TEMIZ DEGIL`). İstem tek satır istiyor; iki hüküm varsa hangisinin
    # geçerli olduğu belirsizdir ve belirsiz çıktı "okunamadı"dır.
    hukumler = SONUC.findall(metin or "")
    if len(hukumler) != 1:
        return bulgular, "", False
    # BİLİNEN AÇIK — hükümden sonraki metin okunmaz. `İnceleme tamamlanamadı /
    # SONUC: TEMIZ / Diff analiz edilmedi` çıktısında son satır görülmez.
    #
    # "Hüküm son satır olmalı" denemesi GERİ ALINDI (2026-08-10): bu fonksiyon
    # modelin ham çıktısını değil, `codex-review.sh`ın sardığı GÖVDEYİ alır ve
    # o gövde hükümden sonra her zaman sabit bir dipnot ekler. Kural konsa
    # HİÇBİR gerçek inceleme ayrıştırılamazdı — kapı kalıcı ENGEL'e düşerdi.
    # Sahte kırmızı burada sahte yeşilden pahalıydı: kapı büsbütün ölürdü.
    #
    # Doğru çözüm metni daha çok zorlamak değil, metin ayrıştırmayı bırakmak
    # (yapılandırılmış çıktı). Alt sınır olarak `test_gercek_sarilmis_cikti_
    # ayristirilir` bu şeklin bozulmamasını kilitler.
    return bulgular, hukumler[0].strip(), True


def _buyut(metin):
    """Türkçe noktalı İ / noktasız ı'yı ASCII'ye indirger, sonra büyütür.

    Gerekçe: `"TEMİZ".upper()` yine `TEMİZ`tir — noktalı İ ASCII I'ya
    dönüşmez. Bu yüzden `"TEMIZ" in sonuc.upper()` Türkçe yazılmış temiz
    hükmü GÖRMÜYORDU ve kapı bulgusuz PR'a ENGEL veriyordu (2026-08-09,
    PR #37). Sahte kırmızı sahte yeşil kadar zararlıdır: tekrarlayan
    sebepsiz ENGEL, insana kapıyı elle atlamayı öğretir.
    """
    # `İ`/`i` noktası üç biçimde gelebilir: tek kod noktası (U+0130),
    # `I`+U+0307, ya da `i`+U+0307. NFC sonuncuyu BİRLEŞTİREMEZ (küçük i
    # için önceden birleştirilmiş biçim yoktur), yani yalnız NFC'ye
    # güvenmek o biçimi "okunamadı" sayıp sahte ENGEL üretirdi.
    # Ayrıştırıp birleşen noktayı DÜŞÜRMEK üçünü de tek biçime indirir;
    # Türkçe bağlamda U+0307 yalnız i/I üstünde bulunur.
    metin = unicodedata.normalize("NFD", metin or "").replace("\u0307", "")
    return metin.replace("ı", "i").upper()


# Hüküm BAŞTAN SONA eşleşmeli. `"TEMIZ" in hukum` alt dize araması olumsuz
# hükmü olumlu sanıyordu: `TEMIZ DEGIL` + ayrıştırılamamış bulgu listesi =
# "tutarlı ve temiz" → auto riskli PR otomatik birleşirdi. Kapının
# verebileceği en pahalı hata budur (2026-08-09, Codex bulgusu PR #38).
# Hoşgörü YALNIZ anlamsız noktalama ve boşluk için: `\W*` yazmak tüm
# sözcük-dışı karakterleri kabul ediyordu, yani hükmü TERSİNE çeviren simgeyi
# de (`TEMIZ ❌` temiz sayılıyordu — Codex bulgusu PR #38).
_TEMIZ_HUKUM = re.compile(r"^TEMIZ[.\s]*$")
# Sayı hem BAŞTAN hem SONA sabitlenir ve parantez SERBEST METİN DEĞİL, tam
# olarak istemin dayattığı biçimdir (`(en yuksek: PX)`). Gevşek bırakılan her
# uç bir kaçak üretti: ortadaki sayı (`TEMIZ DEGIL — 0 bulgu`), sondaki ek
# (`0 BULGU DEGIL`), serbest parantez (`0 BULGU (en yuksek: P0)`) — üçü de
# sıfır bulguyla "tutarlı" sayılıp auto riskli PR'ı otomatik birleştirirdi.
# Basamak sayısı SINIRLI: Python 3.11+ 4300 basamaktan uzun dizeyi
# `int()`e çevirmeyi reddediyor, yani sınırsız `\d*` kapıyı ÇÖKERTİYORDU.
# Çökme fail-closed ENGEL ile aynı şey değildir — biri karar üretir,
# diğeri aracı kırar. 9999 bulgu gerçekçi üst sınırın çok üstünde.
# Parantez ZORUNLU ve sayı en az 1: istem "bulgu yoksa TEMIZ yaz" diyor,
# yani `0 bulgu` ve parantezsiz `N bulgu` sözleşmede YOKTUR. Opsiyonel
# bırakmak, ilan edilen beyaz listeyi sessizce gevşetiyordu.
_BULGU_HUKMU = re.compile(
    r"^([1-9]\d{0,3})\s*BULGU\b\s*\(\s*EN\s*Y[UÜ]KSEK\s*:\s*(P[012])\s*\)[.\s]*$")


def _en_yuksek(bulgular):
    """Ayrıştırılan bulguların en yüksek önceliği (hiç yoksa None)."""
    for p in ("P0", "P1", "P2"):
        if bulgular.get(p):
            return p
    return None


def tutarli_mi(bulgular, sonuc):
    """P1 · Hüküm satırı ile ayrıştırılan bulgular birbirini tutuyor mu.

    Hüküm TANINAN İKİ BİÇİMDEN biri olmak zorundadır: baştan sona `TEMIZ`,
    ya da baştan sona `<sayı> bulgu [(...)]`. Başka her metin OKUNAMAMIŞ
    sayılır ve tutarsızdır.

    Neden beyaz liste: bu fonksiyon dört turda dört kez sızdırdı (Codex,
    PR #38) ve hepsi aynı kalıptı — serbest bırakılan her uç bir kaçak
    üretti. Serbest uç bırakmayan tek tasarım, geçerli biçimleri saymak ve
    gerisini reddetmektir. Eski `sayi > 0` fallback'i özellikle tehlikeliydi:
    tek bir P2 bulgusu + `SONUC: TEMIZ DEGIL` "tutarlı" sayılıyor, P2 merge'i
    durdurmadığı için auto riskli PR otomatik birleşiyordu.

    Bu deponun kendi kuralı burada da geçerli: "okunamadı" ile "temiz" aynı
    şey değildir.
    """
    sayi = sum(len(v) for v in bulgular.values())
    hukum = _buyut(sonuc).strip()
    if _TEMIZ_HUKUM.match(hukum):
        return sayi == 0
    m = _BULGU_HUKMU.match(hukum)
    if m:
        # Sayı VE parantezdeki öncelik iddiası, ayrıştırılan bulgularla
        # birlikte tutmalı; yalan iddia da tutarsızlıktır.
        return (int(m.group(1)) == sayi
                and m.group(2) == _en_yuksek(bulgular))
    return False


# İnceleyicinin HİÇ KOŞAMADIĞI durumlar. Bunlar hüküm değildir — ölçüm
# yokluğudur. `evidence.yml:61` aynı ayrımı zaten yapıyordu:
#   "Araç hatası (exit 2) disiplin ihlali DEĞİLDİR — sahte kırmızı üretmek,
#    sahte yeşil kadar zararlıdır: ikisi de kanıtı bozar."
# `incele.py` o dersi almamıştı: 2026-08-16'da Codex kotası bitince ENGEL
# verip gerekçe olarak "çıktı ayrıştırılamadı" yazdı — oysa çıktı diye bir
# şey YOKTU. Yanlış teşhis, kullanıcıya var olmayan sorunu aratır.
ARAC_YOK = re.compile(
    r"usage limit|rate limit|quota|insufficient.credit"      # kota
    r"|not logged in|unauthor|authentication|401|403"        # kimlik
    r"|command not found|no such file|ENOENT|exit 127"       # kurulum
    r"|connection refused|network is unreachable|ECONNREFUSED",  # ağ
    re.I)


def arac_kosamadi(hata):
    """İnceleyici KOŞAMADI mı (kota/kimlik/kurulum/ağ) — hüküm veremedi mi?

    Zaman aşımı BİLİNÇLE dışarıda: araç vardı ve koştu, iş bitmedi. O bir
    bütçe sorunudur ve kendi notunu (`zaman_asimi_notu`) zaten taşır.
    Biçim hatası da dışarıda: araç koştu, hükmü okunamadı — orada
    fail-closed doğru davranıştır.
    """
    if not hata:
        return False
    if "zaman aşımı" in hata:
        return False
    return bool(ARAC_YOK.search(hata))
