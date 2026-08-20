#!/usr/bin/env python3
"""Tur başı anlık görüntüsü — kapının "bu turda ne değişti" ölçüsü.

Neden ayrı modül: `kapi.py` KARAR verir (kanıt yeterli mi), burası ÖLÇER
(çalışma ağacında ne değişti). İkisi ayrı değişme sebebi taşır: karar kuralı
politikadır, ölçü mekaniktir.

Neden tool olayı yetmez: edit olayı yalnız `Edit|Write|NotebookEdit`
matcher'ından gelir (`.claude/settings.json`). Kabuk üzerinden yazım —
`sed -i`, `>` yönlendirmesi, `python3 -c "open(...,'w')"`, `tee`, `patch`,
`git apply` — HİÇBİR edit olayı üretmez. Kaynak değişir, kapı görmez; test
yükümlülüğü de risk yüzeyi incelemesi de hiç doğmaz (bağımsız inceleme
bulgusu, 2026-08-15).

Neden mutlak kirlilik değil DELTA: `git status` kullanıcının kendi
commit'lenmemiş işini de gösterir. Ajanın hiç dokunmadığı bir dosya için test
istemek, kullanıcıya kapıyı baştan yok saymayı öğretir — bu sistemin en
korktuğu sonuç. Bu yüzden ölçü tur BAŞINA göre farktır.

Neden içerik hash'i değil (size, mtime_ns): anlık HER prompt'ta alınır;
maliyeti tur sayısıyla çarpılır. `os.stat` bir syscall'dır, hash dosyayı
okur. Kabuk yazımı mtime'ı her hâlükârda değiştirir; kaçırma senaryosu
(aynı boyut + aynı nanosaniye) pratikte yoktur.
"""
import json
import os
import re
import subprocess

RUNTIME = os.path.join(".agents", "runtime", "anlik")
ZAMAN_ASIMI = 10


def _git(kok, *args):
    """(çıkış kodu, stdout) — git yoksa/çökerse (1, "")."""
    try:
        p = subprocess.run(["git", *args], cwd=kok, capture_output=True,
                           text=True, timeout=ZAMAN_ASIMI)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _kirli_yollar(kok):
    """Çalışma ağacında değişmiş/izlenmeyen yollar (git'in kendi ölçüsü)."""
    kod, out = _git(kok, "status", "--porcelain", "--untracked-files=all")
    if kod != 0:
        return []
    yollar = []
    for satir in out.splitlines():
        if len(satir) < 4:
            continue
        yol = satir[3:]
        # Yeniden adlandırma: "R  eski -> yeni" — ikisi de bu turun konusudur.
        if " -> " in yol:
            yollar.extend(p.strip().strip('"') for p in yol.split(" -> "))
        else:
            yollar.append(yol.strip().strip('"'))
    return yollar


def _damga(kok, yol):
    """Dosyanın kimliği: (boyut, mtime_ns). Yoksa None (silinmiş)."""
    try:
        st = os.stat(os.path.join(kok, yol))
    except OSError:
        return None
    return f"{st.st_size}:{st.st_mtime_ns}"


HEAD_ANAHTARI = "__head__"


def _head(kok):
    """Anlık anındaki HEAD — commit grafiğinin oynadığını anlamak için."""
    kod, out = _git(kok, "rev-parse", "HEAD")
    return out.strip() if kod == 0 else ""


def al(kok):
    """Şu anki kirli yolların anlık görüntüsü {yol: damga|""} + HEAD.

    Silinmiş dosya boş damga taşır: sonradan geri gelirse fark görünür.
    HEAD ayrı anahtarda tutulur (`__head__`) çünkü tur içinde commit grafiği
    oynayabilir ve o hareket ajanın düzenlemesi DEĞİLDİR (bkz. degisenler).
    """
    veri = {yol: (_damga(kok, yol) or "") for yol in _kirli_yollar(kok)}
    head = _head(kok)
    if head:
        # Git dışı dizinde anahtar HİÇ eklenmez: `al()` orada boş sözlük
        # döndürmeye devam etsin (sözleşme değişmesin, bekçi: test_anlik).
        veri[HEAD_ANAHTARI] = head
    return veri


def _temiz_mi(kok, yol):
    """Dosya HEAD ile birebir aynı mı (yani çalışma ağacında değişmemiş)?"""
    kod, out = _git(kok, "status", "--porcelain", "--", yol)
    return kod == 0 and not out.strip()


def degisenler(kok, onceki):
    """Anlıktan BERİ değişen yollar (yeni, düzenlenen, silinen).

    COMMIT GRAFİĞİNDEN gelen içerik SAYILMAZ (öz-denetim, 2026-08-16): PR
    birleştirilip `git pull` yapılınca çalışma ağacı değişiyor ve kapı
    "kaynak değişti ama test koşmadı" diye BLOKLUYORDU — ajan o dosyaya hiç
    dokunmamıştı. Ölçü doğruydu, ETİKET yanlıştı; `evidence.yml:61`'in
    "araç hatası ihlal değildir" ayrımıyla aynı aile.

    Ayraç dar tutuldu: yalnız (a) HEAD oynadıysa VE (b) dosya HEAD ile
    birebir aynıysa dışarıda bırakılır. Ajan merge'in üstüne yazdıysa dosya
    kirlidir ve GÖRÜNÜR kalır — gevşetme yalnız "içerik commit'ten geldi ve
    kimse üstüne dokunmadı" hâlini kapsar. O commit'ler kendi kapılarından
    geçti; ikinci kez kanıt istemek, kanıtı değil gürültüyü çoğaltır.
    """
    if onceki is None:
        return []
    simdi = al(kok)
    eski_head = onceki.get(HEAD_ANAHTARI, "")
    head_oynadi = bool(eski_head) and eski_head != simdi.get(HEAD_ANAHTARI, "")

    degisen = [yol for yol, damga in simdi.items()
               if yol != HEAD_ANAHTARI and onceki.get(yol) != damga]
    # Anlıkta kirliyken şimdi temiz olan yol da bu turda değişmiştir
    # (geri alındı ya da commit'lendi) — görünmezse kapı yanlış sayar.
    degisen += [yol for yol in onceki
                if yol != HEAD_ANAHTARI and yol not in simdi]
    if head_oynadi:
        degisen = [yol for yol in degisen if not _temiz_mi(kok, yol)]
    return sorted(set(degisen))


def _guvenli_ad(session):
    """Session'ı yol bileşeni olarak GÜVENLİ hâle getirir.

    Öz-denetim bulgusu (2026-08-16): session doğrulanmadan `os.path.join`e
    veriliyordu. `session="../../ele"` anlığı runtime dizininin dışına
    yazdırıyordu. Sömürü sınırlıydı (`session[:8]` kırpması traversal'ı iki
    seviyeyle sınırlıyor, session_id harness'tan geliyor) ama doğrulanmamış
    yol bileşeni, sınırın kırpmaya bağlı kaldığı hâldir — kırpma yarın
    değişebilir.
    """
    temiz = re.sub(r"[^A-Za-z0-9_-]", "", str(session or ""))
    return temiz or "bilinmeyen"


def _yol(kok, session):
    return os.path.join(kok, RUNTIME, f"{_guvenli_ad(session)}.json")


def kaydet(kok, session, veri):
    """Anlığı diske yaz (best-effort; kapı bunun yokluğunda çökmez)."""
    yol = _yol(kok, session)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as fh:
        json.dump(veri, fh)
    return yol


def getir(kok, session):
    """Kaydedilmiş anlık, yoksa None.

    None ile boş sözlük AYRI anlamlar taşır: None "ölçü yok, eski davranışa
    düş" demektir; {} "tur temiz bir ağaçta başladı" demektir. İkisini
    karıştırmak, ölçüsüz turda uydurma delta üretirdi.
    """
    try:
        with open(_yol(kok, session), encoding="utf-8") as fh:
            veri = json.load(fh)
    except (OSError, ValueError):
        return None
    return veri if isinstance(veri, dict) else None


def temizle(kok, session):
    """Tur kapandıktan sonra anlığı sil (kayıt disposable)."""
    try:
        os.remove(_yol(kok, session))
    except OSError:
        pass


def tur_basi_al(pdir, session):
    """Tur BAŞI anlığını al ve yaz (router çağırır; asla bloklamaz).

    Yalnız sisteme BAĞLI projede alınır — global yedek router yabancı repoda
    dosya bırakmaz (`run_event.log_path` ile aynı ölçü).
    """
    if not (session and os.path.isfile(
            os.path.join(pdir, ".agents", "routing.yml"))):
        return None
    try:
        return kaydet(pdir, session[:8], al(pdir))
    except OSError:
        return None


def tur_delta(kok, session):
    """Tur başından beri değişmiş ama tool olayı üretmemiş yollar (kapı için).

    Anlık yoksa boş döner ve kapı ESKİ ölçüye düşer — uydurma delta üretmez.
    Sınır: anlık ne zaman değiştiğini söylemez, yalnız değiştiğini söyler.
    """
    if not session:
        return []
    try:
        return degisenler(kok, getir(kok, session))
    except OSError:
        return []
