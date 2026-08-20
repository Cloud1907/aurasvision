#!/usr/bin/env python3
"""Kurulum KAYNAĞININ git durumu — /auras neyi kopyalıyor, taze mi?

Neden `kernel_dosyalari.py`'den ayrı: orası "hangi dosyalar motorun" sorusunu
yanıtlar (manifest + sınıflandırma), burası "kaynak ağacın kendisi güncel mi"
sorusunu. İkisi ayrı sebeple değişir — bu ayrım ADR-0002'nin çift yönlü
senkron kararıyla geldi ve o karar manifest'e hiç dokunmadan iki kez değişti.

Git primitivi (`git`) burada yaşar çünkü bu modül git'le KONUŞAN modüldür;
`kernel_dosyalari.sinifla` da onu buradan alır (tek kopya, tek davranış).
"""
import subprocess

FETCH_ZAMAN = 20


def git(kok, *arg, girdi=None, zaman=20):
    """git çıktısı (stdout) ya da None — hata/çökme/timeout hepsi None."""
    try:
        p = subprocess.run(["git", "-C", kok, *arg], capture_output=True,
                           text=True, input=girdi, timeout=zaman)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _yukari_akim(kok):
    """Mevcut dalın upstream'i (ör. `origin/main`) ya da None.

    Dal adı sabitlenmez: `origin/main` varsayan kod, main'den başka dalda
    çalışan projede sessizce "doğrulanamadı"ya düşerdi.
    """
    ref = git(kok, "rev-parse", "--abbrev-ref", "@{upstream}")
    return ref.strip() if ref and ref.strip() else None


def _fark(kok, upstream):
    """(ileri, geri) — HEAD upstream'e göre kaç commit önde/arkada."""
    sayim = git(kok, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    try:
        ileri, geri = sayim.split()[:2]
        return int(ileri), int(geri)
    except (AttributeError, ValueError):
        return None


def _kirli(kok):
    """İzlenen dosyalarda kaydedilmemiş değişiklik var mı.

    İzlenmeyen dosya sayılmaz: scratch dosyası ne ileri sarmayı bozar ne de
    kurulumu durdurmayı hak eder.
    """
    cikti = git(kok, "status", "--porcelain", "--untracked-files=no")
    return bool(cikti and cikti.strip())


def _ileri_sar(kok, upstream, ileri, geri):
    """Geride kalan kaynağı upstream'e taşımayı dener → (durum, mesaj)."""
    geride = f"kaynak {upstream}'in {geri} commit gerisinde"
    if ileri:
        return "engel", f"{geride} ve {ileri} yerel commit var — ileri sarılamaz"
    if _kirli(kok):
        return "engel", f"{geride} ve çalışma ağacı kirli — ileri sarılamaz"
    if git(kok, "merge", "--ff-only", upstream) is None:
        return "engel", f"{geride}; ileri sarma başarısız — elle çöz"
    return "ilerletildi", f"kaynak {geri} commit ileri sarıldı → {upstream}"


def kaynak_tazele(kok):
    """Kurulum kaynağını upstream'e ileri sarmayı dener → (durum, mesaj).

    guncel        — HEAD upstream ile aynı (fetch doğrulandı)
    ilerletildi   — geride idi, fast-forward ile upstream'e taşındı
    engel         — geride ama güvenle ileri sarılamıyor (yerel commit/kirli)
    dogrulanamadi — git yok, upstream yok ya da fetch başarısız

    Neden kapı: `/auras` dosyaları kanonik ÇALIŞMA AĞACINDAN kopyalar. Ağaç
    origin'in gerisindeyse kurulan motor eskidir ama manifest onu "güncel"
    diye damgalar — kapı var, koruma yok. 2026-08-15 ölçümü: ağaç e3f1ec1'de,
    origin/main 2d42b90'daydı; o gün koşulacak her /auras eski niyet kapısını
    yayacaktı. Fast-forward seçilmesi bilinçli: iş kaybettiremeyen tek
    ilerletme biçimidir; sarılamıyorsa kararı insan verir.
    """
    if git(kok, "rev-parse", "--git-dir") is None:
        return "dogrulanamadi", "git deposu değil — kaynak sürümü bilinmiyor"
    upstream = _yukari_akim(kok)
    if upstream is None:
        return "dogrulanamadi", "dalın upstream'i yok — karşılaştıracak uzak sürüm yok"
    taze = git(kok, "fetch", "--quiet", upstream.split("/", 1)[0],
               zaman=FETCH_ZAMAN) is not None
    fark = _fark(kok, upstream)
    if fark is None:
        return "dogrulanamadi", f"{upstream} okunamadı — karşılaştırma yapılamadı"
    ileri, geri = fark
    if geri:
        return _ileri_sar(kok, upstream, ileri, geri)
    if not taze:
        return "dogrulanamadi", f"fetch başarısız — {upstream} tazeliği doğrulanamadı"
    # Push edilmemiş commit ve kaydedilmemiş değişiklik engel DEĞİLDİR —
    # kernel burada geliştirilir. Ama sessiz de kalamaz: ikisi de bağlı
    # repolara İNCELENMEMİŞ içerik taşır ve "guncel" onu görünmez kılar.
    uyari = []
    if ileri:
        uyari.append(f"{ileri} yerel commit henüz uzakta yok")
    if _kirli(kok):
        uyari.append("çalışma ağacı kirli — kaydedilmemiş içerik kurulur")
    ek = f" (uyarı: {'; '.join(uyari)})" if uyari else ""
    return "guncel", f"kaynak {upstream} ile aynı{ek}"
