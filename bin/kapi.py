#!/usr/bin/env python3
"""Tur sonu muhatap kapısı — kanıt yoksa "bitti" yok.

Stop hook'u olarak çalışır. Bu turda ne değiştiğine bakar ve kanıt arar:
kaynak kod değiştiyse SON DÜZENLEMEDEN SONRA koşmuş ve GEÇMİŞ bir test;
risk yüzeyi değiştiyse güvenlik incelemesi. Eksikse turu bloklar ve ajanı
işe geri gönderir.

Codex eleştirisi (2026-07-26) doğrudan buraya işlendi:
- "test dosyası değişti" test kanıtı DEĞİLDİR → testin koştuğu ve geçtiği aranır.
- "skill yüklendi" inceleme kanıtı DEĞİLDİR → risk yüzeyinde skill yüklenmesi
  asgari koşuldur, yeterli değil; kullanıcıya da bu ayrım söylenir.
- Uyarmak yetmez, bloklamak gerekir; yoksa gerekçe yazdırmak bürokrasidir.
- Aynı diff imzası için tek blok: kullanıcı/ajan kapana kısılmaz.

Kullanım (Stop hook):
    python3 bin/kapi.py
Elle deneme:
    echo '{}' | python3 bin/kapi.py --log /tmp/events.jsonl
"""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
# Yüzey sınıflandırması ayrı modülde (bin/yuzey.py): "bu yol ne tür kanıt
# ister" ile "kanıt yeterli mi" ayrı sorulardır.
from yuzey import (BUYUK_DOSYA, BUYUK_SATIR, E2E_CMD_RE,  # noqa: E402
                   KAYNAK_UZANTI, TEST_YOL, UI_UZANTI, UI_YOL,
                   risk_yuzeyi_mi)


def _run_event():
    spec = importlib.util.spec_from_file_location(
        "_re", os.path.join(HERE, "run_event.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bu_turun_olaylari(olaylar, session=None):
    """Bu oturumun son 'stop'undan sonraki olaylar = içinde bulunduğumuz tur.

    Session süzmesi ZORUNLU değil ama olmadığında kapı yanlış şeyi görür:
    olay kaydı tek dosyadır ve `.claude/worktrees/` altında eşzamanlı
    oturumlar çalışır (2026-08-15'te bu repoda 5 worktree ölçüldü). Süzme
    yokken B oturumunun testi A oturumunun düzenlemesine kanıt sayılıyordu.

    `session` None ise süzme YAPILMAZ: kayıttaki eski satırlar bu alanı
    taşımıyor ve onları yok saymak geçmiş kanıtı silmek olurdu (geriye uyum).
    """
    if session:
        olaylar = [o for o in olaylar
                   if o.get("session") in (None, session)]
    son_stop = -1
    for i, o in enumerate(olaylar):
        if o.get("kind") == "stop":
            son_stop = i
    return olaylar[son_stop + 1:]


def duzenlenen_dosyalar(olaylar, session=None):
    """Bu turda düzenlenen dosyalar (doğrulayıcı seçimi için)."""
    return [o["file"] for o in bu_turun_olaylari(olaylar, session)
            if o.get("kind") == "edit" and o.get("file")]


def calistir_dogrulayici(rel, *arg):
    """Bir skill doğrulayıcısını koşar → (çıkış_kodu, son_satır) veya None.

    Skill'lerin yazılı kuralı burada zorlanır: doğrulayıcı yoksa (bağlanmamış
    proje, eksik kurulum) kapı sessizce geçer — mekanizma kullanıcıyı
    kilitlemez, ama validate.py bağlanmamış doğrulayıcıyı zaten reddeder.
    """
    yol = os.path.join(ROOT, ".agents", "skills", rel)
    if not os.path.isfile(yol):
        return None
    try:
        p = subprocess.run([sys.executable, yol, *arg], capture_output=True,
                           text=True, cwd=ROOT, timeout=30)
        satirlar = [s for s in (p.stdout or "").splitlines() if s.strip()]
        return p.returncode, (satirlar[-1] if satirlar else "")
    except (OSError, subprocess.SubprocessError):
        return None


def dogrulayici_sonuclari(duzenlenen):
    """Bu turda hangi doğrulayıcılar geçerliyse onları koşar."""
    sonuc = {}
    if any(f.lower().endswith(KAYNAK_UZANTI) and not TEST_YOL.search(f)
           for f in duzenlenen):
        sonuc["test_first"] = calistir_dogrulayici(
            "implement-change/scripts/check_test_first.py")
    # dict.fromkeys: tekilleştir ama sırayı koru. Aynı rapor turda birden çok
    # kez düzenlenince kaynak denetimi her düzenleme için tekrar koşuyor ve
    # kapı aynı uyarıyı N kez basıyordu (2026-08-06 gürültü bulgusu).
    raporlar = list(dict.fromkeys(
        f for f in duzenlenen
        if ".agents/reports/" in f.replace("\\", "/") and f.endswith(".md")))
    if raporlar:
        sonuc["kaynak"] = [(f, calistir_dogrulayici(
            "research-with-evidence/scripts/check_citations.py", f))
            for f in raporlar]
    return sonuc


def degisen_satir_sayisi():
    """git ile net değişen satır — olay sayımından daha güvenilir kanıt."""
    try:
        p = subprocess.run(["git", "diff", "--numstat", "HEAD"],
                           capture_output=True, text=True, cwd=ROOT, timeout=10)
        if p.returncode != 0:
            return 0
        toplam = 0
        for satir in p.stdout.splitlines():
            parca = satir.split("\t")
            if len(parca) >= 2 and parca[0].isdigit() and parca[1].isdigit():
                toplam += int(parca[0]) + int(parca[1])
        return toplam
    except Exception:
        return 0


def degerlendir(olaylar, satir_sayisi=0, dogrulayici=None, session=None,
                ek_dosyalar=()):
    """(bulgular, imza) — bulgu listesi boşsa tur temiz demektir.

    dogrulayici: skill doğrulayıcılarının sonucu, DIŞARIDAN enjekte edilir
    (satir_sayisi deseni). Böylece bu fonksiyon saf kalır ve testler gerçek
    alt süreç koşturmadan her dalı deneyebilir.

    session: verilirse tur penceresi o oturuma daraltılır (bkz.
    bu_turun_olaylari).

    ek_dosyalar: tool olayı ÜRETMEDEN değişen yollar (bkz. bin/anlik.py).
    Kabuk üzerinden yazım — `sed -i`, `>`, `tee`, `patch` — edit olayı
    üretmez; bu liste olmadan kapı kaynağın değiştiğini hiç görmez.
    """
    dogrulayici = dogrulayici or {}
    tur = bu_turun_olaylari(olaylar, session)

    duzenlenen, son_edit_idx = [], -1
    test_olaylari, skiller = [], []
    zorunlu, atlanan = [], []
    for i, o in enumerate(tur):
        kind = o.get("kind")
        if kind == "edit" and o.get("file"):
            duzenlenen.append(o["file"])
            son_edit_idx = i
        elif kind == "test":
            test_olaylari.append((i, o))
        elif kind == "skill" and o.get("skill"):
            skiller.append(o["skill"])
        elif kind == "route" and o.get("routed"):
            zorunlu.append(o["routed"])
        elif kind == "skipped" and o.get("skill"):
            atlanan.append(o["skill"])

    # Tool olayı üretmeyen yazımlar (kabuk) burada katılır: kaynak kaynaktır,
    # hangi araçla yazıldığı yükümlülüğü değiştirmez.
    for yol in ek_dosyalar:
        if yol not in duzenlenen:
            duzenlenen.append(yol)

    ui = [f for f in duzenlenen
          if f.lower().endswith(UI_UZANTI) or UI_YOL.search(f)]
    kaynak = [f for f in duzenlenen
              if f.lower().endswith(KAYNAK_UZANTI) and not TEST_YOL.search(f)]
    riskli = [f for f in duzenlenen if risk_yuzeyi_mi(f)]

    bulgular = []
    if kaynak:
        sonrakiler = [o for i, o in test_olaylari if i > son_edit_idx]
        if not sonrakiler:
            bulgular.append((
                "BLOK", "test kanıtı yok",
                f"{len(kaynak)} kaynak dosyası değişti ama son düzenlemeden "
                f"sonra test/doğrulama koşmadı: {', '.join(kaynak[:4])}"))
        elif any(o.get("ok") is False for o in sonrakiler):
            bulgular.append((
                "BLOK", "testler kırmızı",
                "Son koşan test/doğrulama başarısız sonuç işareti taşıyor."))
        elif all(o.get("ok") is None for o in sonrakiler):
            bulgular.append((
                "UYARI", "test sonucu belirsiz",
                "Test komutu koştu ama çıktısından geçti/kaldı okunamadı."))

    # Test-önce disiplini: kaynak değişti ama HİÇ test değişmediyse kes.
    # (implement-change skill'inin yazılı kuralı — burada zorlanır.)
    tf = dogrulayici.get("test_first")
    if kaynak and tf and tf[0] == 1:
        bulgular.append((
            "BLOK", "test-önce bozuldu",
            f"{len(kaynak)} kaynak dosyası değişti ama hiçbir test dosyası "
            f"değişmedi. {tf[1]} Testi yaz (önce kırmızıyı gör). Gerçekten "
            "test gerektirmeyen yüzeyse: check_test_first.py --allow '<glob>'"))

    # Araştırma raporu yazıldıysa kaynak disiplini ölçülür (sinyal, hakem değil).
    for dosya, sonuc in dogrulayici.get("kaynak", []):
        if sonuc and sonuc[0] == 1:
            bulgular.append((
                "UYARI", "rapor kaynak sinyali zayıf",
                f"{dosya}: {sonuc[1]} Kaynak ekle ya da iddiayı "
                "'spekülatif' etiketle."))

    if ui:
        tiklama = [o for i, o in enumerate(tur)
                   if o.get("kind") == "ui" or
                   (o.get("kind") == "test" and E2E_CMD_RE.search(o.get("cmd") or ""))]
        if not tiklama:
            bulgular.append((
                "BLOK", "tıklama kanıtı yok",
                f"Görünür yüzey değişti ({', '.join(ui[:3])}) ama kimse "
                "tıklamadı. E2E koştur ya da tarayıcıda aç-tıkla-ekran görüntüsü "
                "al. Projede E2E aracı yoksa bunu SÖYLE ve kurulum öner "
                "(python3 bin/araclar.py)."))

    # Zorunlu skill karşılıksız kalamaz: ya yüklenir ya gerekçesi kayda geçer.
    # (Codex hükmü: gerekçe kanıt değil, denetlenebilir beyandır.)
    # Süreç borcu UYARI, güvenlik borcu BLOK (bağımsız inceleme şartı,
    # 2026-08-15). Gerekçe: bir blok +1 tam ajan turudur ve bağlamı yeniden
    # okutur — kabaca 100 turluk router enjeksiyonu kadar pahalı. Yüklenmemiş
    # bir süreç skill'i için bu bedeli ödemek token'ı korumaya değil törene
    # harcar. Risk yüzeyi incelemesi AŞAĞIDA ayrıca BLOK'tur; yani "güvenlik
    # borcu uyarıya indi" DEĞİLDİR — yalnız süreç borcu indi.
    karsiliksiz = [z for z in zorunlu if z not in skiller and z not in atlanan]
    if karsiliksiz:
        bulgular.append((
            "UYARI", "zorunlu skill karşılıksız",
            f"Router {', '.join(karsiliksiz)} skill'ini zorunlu kıldı; ne "
            "yüklendi ne gerekçesi kayda geçti. Yükle ya da şunu koş: "
            "python3 bin/run_event.py --kind skipped --skill <ad> --reason "
            "<misroute|not_applicable|unavailable|user_override> --note '<tek cümle>'"))

    if riskli and "security-review" not in skiller:
        bulgular.append((
            "BLOK", "risk yüzeyi incelenmedi",
            f"Risk yüzeyine dokunuldu ({', '.join(riskli[:3])}) ama "
            "security-review yüklenmedi. Not: skill'i yüklemek inceleme "
            "KANITI değildir; bulgular dosya:satır ile raporlanmalı."))

    if (len(kaynak) >= BUYUK_DOSYA or satir_sayisi >= BUYUK_SATIR) and kaynak:
        bulgular.append((
            "UYARI", "bağımsız inceleme önerilir",
            f"{len(kaynak)} kaynak dosyası / ~{satir_sayisi} satır değişti — "
            "bu boyut tek yazarın kendi denetimini aşar."))

    return bulgular, imzala(duzenlenen, bulgular, karsiliksiz + riskli)


def imzala(duzenlenen, bulgular, ekler=()):
    """Bu turun BORÇ imzası: dosyalar + bulgu türleri + borcun ÖZNESİ.

    `ekler` borcun neye ait olduğunu ayırır: iki ayrı düzenlemesiz turda
    farklı skill'ler karşılıksız kalırsa bulgu BAŞLIĞI aynıdır ("zorunlu
    skill karşılıksız") ve yalnız başlığa bakan imza ikisini tek borç sayardı
    — birinci blok ikinciyi muaf kılardı. Özne (karşılıksız skill adı, risk
    dosyası) imzaya girer.

    Neden bulgu türü de girer (2026-08-15 ölçümü): imza yalnız düzenlenen
    dosyalardan üretiliyordu. Düzenleme yoksa `"|".join([])` boş dizeydi ve
    imza SABİT `e3b0c44298fc` çıkıyordu — kayıttaki 92 gate olayının 39'u bu
    imzayı taşıyordu ve `zaten_bloklandi` tüm geçmişte aradığı için ilki
    dışındaki 38 tur "bu borç zaten bloklandı" sayılıp muaf kaldı. Yani kod
    değiştirmeyen HER tur (araştırma, denetim, plan, sohbet) kalıcı olarak
    kapı dışındaydı.

    "Aynı borçla ikinci kez kapana kısılma" kuralı korunur (AGENTS.md), ama
    "aynı borç" artık gerçekten aynı borçtur: farklı bulgu = farklı imza.
    """
    parcalar = (sorted(set(duzenlenen)) + sorted({b[1] for b in bulgular})
                + sorted(set(ekler)))
    return hashlib.sha256(
        "|".join(parcalar).encode("utf-8")).hexdigest()[:12]


def _kabuk_yazimlari(session):
    """Kabuk üzerinden yazılan yollar (ölçü bin/anlik.py'de)."""
    try:
        import anlik
        return anlik.tur_delta(ROOT, session)
    except Exception:
        return []


def zaten_bloklandi(olaylar, imza):
    """Aynı diff imzası daha önce bloklandıysa tekrar bloklama (kapan yok)."""
    return any(o.get("kind") == "gate" and o.get("sig") == imza
               for o in olaylar)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}") or {}
    except (ValueError, AttributeError):
        payload = {}

    try:
        re_mod = _run_event()
        yol = args.log or re_mod.log_path()
        olaylar = []
        try:
            with open(yol, encoding="utf-8") as fh:
                for satir in fh:
                    satir = satir.strip()
                    if satir:
                        try:
                            olaylar.append(json.loads(satir))
                        except ValueError:
                            continue
        except OSError:
            olaylar = []

        session = (payload.get("session_id") or "")[:8] or None
        ek = _kabuk_yazimlari(session)
        duzenlenen = duzenlenen_dosyalar(olaylar, session) + ek
        bulgular, imza = degerlendir(
            olaylar, degisen_satir_sayisi(),
            dogrulayici_sonuclari(duzenlenen),
            session=session, ek_dosyalar=ek)
        bloklar = [b for b in bulgular if b[0] == "BLOK"]
        # Sonsuz döngü koruması: hook zaten blokladıysa ya da aynı imza daha
        # önce bloklandıysa tekrar bloklamaz — ama SESSİZ de kalmaz (aşağıda
        # uyarı basılır). Sessiz geçiş, borcu temizlenmiş gösterirdi.
        tekrar = payload.get("stop_hook_active") or zaten_bloklandi(olaylar, imza)

        if bulgular:
            re_mod.append({"kind": "gate", "sig": imza,
                           "cmd": ";".join(b[1] for b in bulgular)}, yol)

        if bloklar and not tekrar:
            # Bloklanan tur KAPANMADI: 'stop' yazılmaz. Yazılsaydı bir sonraki
            # değerlendirme boş pencere görür ve kanıtsız düzenlemeler sessizce
            # geçmiş tura gömülürdü (Codex ölçümü, 2026-08-12). 'stop' yalnız
            # gerçekten kapanan turda yazılır (aşağıda).
            gerekce = "\n".join(f"[{b[0]}] {b[1]} — {b[2]}" for b in bulgular)
            print(json.dumps({
                "decision": "block",
                "reason": ("AurasAgents kapısı: kanıt olmadan tur kapanmaz.\n"
                           + gerekce +
                           "\nYap: eksik kanıtı üret (testi koştur / incelemeyi "
                           "yap), sonra bitir. Gerçekten gereksizse kullanıcıya "
                           "tek cümleyle gerekçesini söyle."),
                "systemMessage": f"⛔ kapı: {', '.join(b[1] for b in bloklar)}",
            }, ensure_ascii=False))
            return 0

        re_mod.append({"kind": "stop"}, yol)
        if bulgular:
            # Kapan kurulmaz ama iz bırakılır: bu tur kanıt borcuyla kapandı.
            print(json.dumps({
                "systemMessage": "⚠️ kapı: " + ", ".join(b[1] for b in bulgular)
                                 + (" — tur kanıt borcuyla kapandı"
                                    if bloklar else ""),
            }, ensure_ascii=False))
    except Exception:
        return 0  # kapı çökerse tur bloklanmaz — mekanizma kullanıcıyı kilitlemez
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
