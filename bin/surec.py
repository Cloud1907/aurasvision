#!/usr/bin/env python3
"""Süreç çalıştırma katmanı — alt süreç ağacını asla yetim bırakmaz.

Neden ayrı modül: `incele.py` KARAR verir (risk sınıfı, bulgu, merge);
burası SÜREÇ yönetir. İkisi 2026-08-07'de aynı dosyadaydı ve dosya kalite
ratchet'inin 400 satır sınırına dayandı — sınır, ayrılması gereken iki
sorumluluğu gösteriyordu.

Buradaki tek kural: **başlatılan ağaç, çıkış yolu ne olursa olsun ölür.**
Ölçüm (2026-08-07): `codex-review.sh` ağacı, onu başlatan süreç öldükten
sonra 2 saat 43 dakika yaşamaya devam etti (PPID 1, altında `codex exec`);
aynı iş normalde ~150s sürüyor. Sızan süreç aynı hesabın oturumunu meşgul
ettiği için sonraki inceleme yavaşlar → o da zaman aşımına uğrayıp bir
süreç daha sızdırır. Kontrollü ölçüm, aynı dondurulmuş diff:
    yetim canlı: 155.8s        yetim ölü: 98.5s / 45.5s / 54.0s
"""
import os
import signal
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# İnceleme bütçesi `gh` çağrılarınınkinden AYRIDIR (önce ikisi de `kos`'un
# genel varsayılanına bağlıydı; birini ayarlamak diğerini sessizce değiştirirdi).
# Ölçüm: 4.4KB→147s, 9.0KB→156s — boyut baskın değil, ~140s sabit taban var.
# Bu yüzden diff boyutuna göre ÖLÇEKLENMİYOR: ölçeklenecek değişken sürücü değil.
INCELEME_BUTCESI = int(os.environ.get("INCELE_BUTCE", "900"))


TERM_SURESI = 3  # kabuğun EXIT tuzağını koşturmasına verilen süre (saniye)


def _sessiz(fn, *a):
    """Temizlik adımı — HİÇBİR şey yarıda kesmesin, ikinci Ctrl-C dahil.

    Temizlik yolu kesilebilir olursa ağaç diri kalır: kullanıcı Ctrl-C'ye
    iki kez basınca ikincisi tam buraya düşer. Yutulan istisna yalnız
    temizliğin kendisine ait; asıl kesinti `kos`'tan yine yükselir.
    """
    try:
        fn(*a)
    except BaseException:
        pass


def _temizle(p, pgid):
    """Öldürme dizisi. Tek tek adımlar `_sessiz`, dizinin BÜTÜNÜ ise
    `agaci_oldur`'daki yeniden deneme ile korunur: iki çağrı ARASINA düşen
    bir kesinti diziyi yarıda bırakabilirdi."""
    if pgid is None:
        _sessiz(p.kill)
    else:
        _sessiz(os.killpg, pgid, signal.SIGTERM)
        _sessiz(p.wait, TERM_SURESI)  # tuzak koşsun; kendi çıkarsa erken döner
        _sessiz(os.killpg, pgid, signal.SIGKILL)
    _sessiz(p.communicate, None, 10)


def agaci_oldur(p, pgid=None):
    """Süreç GRUBUNU öldürür — önce nazikçe, sonra kesin.

    `p.kill()` yalnız doğrudan çocuğu (bash) alır; altındaki ask-codex.sh ve
    `codex exec` yaşar ve PPID 1'e düşer. Bu yüzden GRUBA sinyal gider.

    Neden iki aşama: doğrudan SIGKILL yakalanamaz, kabuğun `EXIT` tuzağı hiç
    koşmaz — `codex-review.sh` prompt'unu `mktemp` ile yazıp tuzakla siliyor,
    tek SIGKILL her zaman aşımında /tmp'ye bir dosya bırakırdı.

    `pgid` DIŞARIDAN gelir: lider çıkıp torun boruyu açık tuttuğunda
    `getpgid` başarısız olur ve grup elde kalmazdı. Spawn anında yakalanan
    değer bu yüzden tercih edilir.
    """
    if pgid is None:
        try:
            pgid = os.getpgid(p.pid)
        except OSError:
            pgid = None
    # Sınırlı yeniden deneme: adımlar arasına düşen ikinci Ctrl-C diziyi
    # yarıda bırakmasın. Sınırlı, çünkü sonsuz döngü kapıyı asardı.
    for _ in range(3):
        try:
            _temizle(p, pgid)
            return
        except BaseException:
            continue


def _grubu_supur(pgid):
    """Lider çıktıktan sonra grupta kalan torunları süpürür.

    Grup boşsa `killpg` ProcessLookupError verir — beklenen hâl, yutulur.
    PID geri-dönüşümü riski: lider reap edildikten sonra aynı pgid'nin
    başkasına düşmesi teorik olarak mümkün. Pencere mikrosaniyeler ve
    süpürme `communicate()` döner dönmez yapılıyor; sızan `codex exec`
    ağacının saatlerce yaşamasına karşı kabul edilmiş takas.
    """
    _sessiz(os.killpg, pgid, signal.SIGKILL)


def kos(*arg, girdi=None, timeout=600):
    """Alt süreci KENDİ oturumunda başlatır; HER çıkış yolunda ağacı öldürür.

    Üç sızıntı yolu da kapalı (üçü de kapının bulduğu gerçek açıklar):
    zaman aşımı (`subprocess.run(timeout=)` ağacı öldürmez), `KeyboardInterrupt`
    (ne OSError ne SubprocessError — dar `except` onu görmez) ve NORMAL dönüş
    (arka plana atılmış, stdio'su yönlendirilmiş torun boruyu tutmaz; kabuk
    çıkar, `communicate()` sorunsuz döner, torun yaşar).
    Gerekçe ve ölçüm: tests/test_surec.py.
    """
    try:
        p = subprocess.Popen(
            arg, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if girdi is not None else None,
            text=True, cwd=ROOT, start_new_session=True)
    except OSError as e:
        return 1, "", str(e)
    pgid = p.pid  # start_new_session=True → çocuk grup lideri, pgid == pid
    try:
        out, err = p.communicate(girdi, timeout=timeout)
        _grubu_supur(pgid)
        return p.returncode, out, err
    except BaseException as e:  # Ctrl-C/SystemExit dahil: ağacı ASLA bırakma
        agaci_oldur(p, pgid)
        _grubu_supur(pgid)
        if isinstance(e, (OSError, subprocess.SubprocessError)):
            return 1, "", str(e)
        raise


def zaman_asimi_notu(butce):
    """Zaman aşımında kullanıcının önüne EYLEM koyar — önünde yol olmayan
    kapı `gh pr merge` ile atlanır, kural belgede kalır sistemde kalmaz."""
    return (
        f"İnceleme {butce}s bütçesinde bitmedi. Karar ENGEL — 'okunamadı' "
        "'temiz' demek değildir. Sırayla dene:\n"
        "1. Asılı süreç: `ps -eo etime,pid,command | grep 'codex exec'` — "
        "YAŞI bu incelemeden eskiyse yetimdir, öldür (eşzamanlı meşru "
        "incelemeyi öldürme). Sızan süreç sonrakini yavaşlatır: 155.8s→45.5s.\n"
        f"2. Bütçeyi yükseltip tekrar koş: "
        f"`INCELE_BUTCE={butce * 2} python3 bin/incele.py <pr>`\n"
        "3. PR'ı böl — tek amaçlı küçük diff hem hızlı hem doğru incelenir "
        "(AGENTS.md: ilgisiz işleri tek PR'da toplama).")
