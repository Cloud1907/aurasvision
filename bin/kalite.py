#!/usr/bin/env python3
"""Deterministik kod kalitesi ölçümü + ratchet (kötüleşemez) kapısı.

Neden: "temiz kod" yazılı bir tavsiyeydi, ölçülmüyordu. Ölçülmeyen kuralın
standardı yoktur, tercihi vardır. Bu araç LLM yorumu ÜRETMEZ — yalnız sayar.
Sayılar ratchet ile kilitlenir: mevcut borç kabul edilir ama BÜYÜYEMEZ.

Dürüstlük sınırı: fonksiyon analizi Python (girinti) ve süslü-parantezli
diller için yapılır; diğerlerinde yalnız dosya satırı sayılır. Kapsam her
raporda yazılır — ölçülmeyen şeyi ölçülmüş gibi göstermez.

Kullanım:
  python3 bin/kalite.py                 # insan raporu
  python3 bin/kalite.py --json          # makine çıktısı
  python3 bin/kalite.py --baseline      # mevcut durumu ratchet tabanı yap
  python3 bin/kalite.py --check         # eşik + ratchet; regresyonda exit 1

Eşikler: .agents/kalite.yml (proje sahibi; yoksa aşağıdaki varsayılanlar).
Taban  : .agents/kalite-baseline.json (proje sahibi; motor ezmez).
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import diller  # noqa: E402  (dil kapsamının tek tanımı)
import marj  # noqa: E402  (eşiğe yakınlık — pusula, kapı değil)
from kalite_rapor import (bulgu_yaz, ratchet_yaz,  # noqa: E402
                          sayac_yaz)
from olukod import olu_importlar  # noqa: E402  (ölü kod ayrı konu)

TABAN_YOL = os.path.join(ROOT, ".agents", "kalite-baseline.json")
AYAR_YOL = os.path.join(ROOT, ".agents", "kalite.yml")

VARSAYILAN = {
    "max_dosya_satir": 400,
    "max_fonksiyon_satir": 50,
    "max_dal": 10,
}

# Dil kapsamı TEK kaynaktan (bin/diller.py) — bekçi: tests/test_diller.py
KOD_UZANTI = set(diller.KALITE)
# Fonksiyon gövdesi süslü parantezle sınırlanan diller. Ruby (def…end) ve
# Python burada DEĞİL — "hepsi analiz edildi" demek dürüst olmazdı; analiz
# edilmeyen dosya kapsam raporunda 'yalnız satır sayılan' olarak görünür.
SUSLU = set(diller.SUSLU)
ATLA = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
        "build", ".next", "obj", "coverage", "vendor", "Pods", ".mypy_cache",
        ".pytest_cache", "site-packages", ".agents/runtime"}

PY_FONK = re.compile(r"^(\s*)(?:async\s+)?def\s+\w+")
JS_FONK = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+\w+|"
    r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|"
    r"(?:public|private|protected|internal|static|\s)*[\w<>\[\],\s]+\s+\w+\s*\([^;]*\)\s*\{)")
DAL = re.compile(r"(?<![\w.])(if|elif|else\s+if|for|while|case|catch|except)"
                 r"(?![\w])|&&|\|\||\?\?|\?[^.:]")


BORC = re.compile(r"(?<![\w])(TODO|FIXME|XXX|HACK)(?![\w])")
# Desen parçalı kurulur: düz yazılırsa bu dosyanın KENDİSİ bulgu üretir
# (tarayıcının kendini yakalaması — tests/test_skill_validators.py'deki
# secret konvansiyonuyla aynı).
DEBUG = re.compile(r"console\.(log|debug)\s*\(|(?<![\w])" + "debug" + r"ger(?![\w])")


def ayarlar():
    esik = dict(VARSAYILAN)
    if os.path.isfile(AYAR_YOL):
        try:
            import yaml
            veri = yaml.safe_load(open(AYAR_YOL, encoding="utf-8")) or {}
            for k in VARSAYILAN:
                if isinstance(veri.get(k), int):
                    esik[k] = veri[k]
        except Exception:
            pass          # ayar okunamazsa varsayılan; ölçüm durmaz
    return esik


def ayri_calisma_agaci(yol):
    """Alt dizin kendi başına bir git çalışma ağacı mı (nested repo/worktree)?

    Neden gerekli: agent worktree'leri repo İÇİNE açılıyor
    (`.claude/worktrees/<ad>/`). Taranırlarsa her dosya iki kez sayılır ve
    ratchet gerçek borç büyümüş gibi kırmızı yanar. 2026-08-07'de bizzat
    oldu: 28 dosya 56 göründü, her sayaç tam iki katına çıktı ve merge
    bloklandı. `.git` adı ATLA'da vardı ama worktree'de `.git` bir DOSYA
    (gitdir işaretçisi), dizin değil — filtreye takılmıyordu.

    Kural genel tutuldu: kendi `.git`'i olan alt dizin bu projenin kodu
    değildir (worktree, submodule, iç içe klon — hepsi aynı sebeple).
    """
    return os.path.exists(os.path.join(yol, ".git"))


def kod_dosyalari(kok):
    for dizin, altlar, isimler in os.walk(kok):
        altlar[:] = [d for d in altlar if d not in ATLA
                     and not ayri_calisma_agaci(os.path.join(dizin, d))
                     and not
                     os.path.join(os.path.relpath(dizin, kok), d)
                     .replace(os.sep, "/").startswith(".agents/runtime")]
        for i in isimler:
            if os.path.splitext(i)[1] in KOD_UZANTI:
                yield os.path.join(dizin, i)


def py_fonksiyonlar(satirlar):
    """(ad_satiri, uzunluk, dal_sayisi) — girinti tabanlı, Python."""
    sonuc = []
    for i, s in enumerate(satirlar):
        m = PY_FONK.match(s)
        if not m:
            continue
        girinti = len(m.group(1))
        son = i
        for j in range(i + 1, len(satirlar)):
            t = satirlar[j]
            if not t.strip():
                continue
            mevcut = len(t) - len(t.lstrip())
            if mevcut <= girinti:
                break
            son = j
        govde = satirlar[i:son + 1]
        sonuc.append((i + 1, len(govde), len(DAL.findall("\n".join(govde)))))
    return sonuc


def suslu_fonksiyonlar(satirlar):
    """(ad_satiri, uzunluk, dal_sayisi) — süslü parantez eşleme."""
    sonuc = []
    for i, s in enumerate(satirlar):
        if not JS_FONK.match(s) or s.strip().endswith(";"):
            continue
        derinlik, basladi, son = 0, False, i
        for j in range(i, len(satirlar)):
            derinlik += satirlar[j].count("{") - satirlar[j].count("}")
            if "{" in satirlar[j]:
                basladi = True
            son = j
            if basladi and derinlik <= 0:
                break
        govde = satirlar[i:son + 1]
        if len(govde) > 1:
            sonuc.append((i + 1, len(govde),
                          len(DAL.findall("\n".join(govde)))))
    return sonuc


def olc(kok=ROOT, esik=None):
    esik = esik or ayarlar()
    sayac = {"buyuk_dosya": 0, "uzun_fonksiyon": 0, "karmasik_fonksiyon": 0,
             "borc_isareti": 0, "debug_artigi": 0, "olu_import": 0}
    bulgular = []
    dosya_sayisi = fonk_analizli = 0
    for yol in sorted(kod_dosyalari(kok)):
        rel = os.path.relpath(yol, kok)
        try:
            with open(yol, encoding="utf-8", errors="replace") as fh:
                metin = fh.read()
        except OSError:
            continue
        satirlar = metin.splitlines()
        dosya_sayisi += 1

        if len(satirlar) > esik["max_dosya_satir"]:
            sayac["buyuk_dosya"] += 1
            bulgular.append((rel, 1, "buyuk_dosya",
                             f"{len(satirlar)} satır (> {esik['max_dosya_satir']})",
                             len(satirlar)))
        n = len(BORC.findall(metin))
        sayac["borc_isareti"] += n
        d = len(DEBUG.findall(metin))
        sayac["debug_artigi"] += d
        if d:
            bulgular.append((rel, 1, "debug_artigi", f"{d} adet", d))

        uzanti = os.path.splitext(yol)[1]
        if uzanti == ".py":
            olu = _olu_import_bulgulari(rel, metin)
            sayac["olu_import"] += len(olu)
            bulgular.extend(olu)
            fonklar = py_fonksiyonlar(satirlar)
        elif uzanti in SUSLU:
            fonklar = suslu_fonksiyonlar(satirlar)
        else:
            continue
        fonk_analizli += 1
        for satir, uzunluk, dal in fonklar:
            if uzunluk > esik["max_fonksiyon_satir"]:
                sayac["uzun_fonksiyon"] += 1
                bulgular.append((rel, satir, "uzun_fonksiyon",
                                 f"{uzunluk} satır (> {esik['max_fonksiyon_satir']})",
                                 uzunluk))
            if dal > esik["max_dal"]:
                sayac["karmasik_fonksiyon"] += 1
                bulgular.append((rel, satir, "karmasik_fonksiyon",
                                 f"{dal} dal (> {esik['max_dal']})", dal))
    return {
        "sayaclar": sayac,
        "esikler": esik,
        "kapsam": {"kod_dosyasi": dosya_sayisi,
                   "fonksiyon_analizli": fonk_analizli,
                   "yalniz_satir_sayilan": dosya_sayisi - fonk_analizli},
        "bulgular": [{"dosya": d, "satir": s, "tur": t, "detay": x,
                      "buyukluk": b}
                     for d, s, t, x, b in bulgular],
        "buyuklukler": buyuklukler(bulgular),
    }


def _olu_import_bulgulari(rel, metin):
    """Ölü import bulgularını ölçüm biçimine çevirir (olc'yi sade tutar)."""
    return [(rel, satir, "olu_import",
             f"'{ad}' import edilmiş ama kullanılmıyor", 1)
            for satir, ad in olu_importlar(metin)]


def buyuklukler(bulgular):
    """{kimlik: büyüklük} — mevcut ihlallerin BOYUTU, sayısı değil.

    H. Demir denetimi (2026-08-15): ratchet yalnız eşiği aşan NESNE SAYISINI
    kıyaslıyordu. `validate.py` ADR-0004 zamanında 601 satırdı, ölçüm günü
    952 — %58 büyüme; `buyuk_dosya` sayacı ise hep 1 kaldı ve kapı yeşil
    yandı. Yani "mevcut borç kabul, büyümesi bloklanır" iddiası, borcun
    BÜYÜKLÜĞÜ için hiç çalışmıyordu.

    Kimlik dosya + tür; satır numarası KASITLI olarak dışarıda: fonksiyon
    birkaç satır kayınca kimliği değişmemeli, yoksa her düzenleme sahte
    "yeni ihlal" üretir.
    """
    en = {}
    for dosya, _satir, tur, _detay, boyut in bulgular:
        anahtar = f"{dosya}#{tur}"
        en[anahtar] = max(en.get(anahtar, 0), boyut)
    return en


def taban_oku():
    try:
        with open(TABAN_YOL, encoding="utf-8") as fh:
            return json.load(fh).get("sayaclar", {})
    except (OSError, ValueError):
        return None


def taban_buyuklukleri():
    """Tabandaki ihlal büyüklükleri. Alan yoksa None (eski taban biçimi)."""
    try:
        with open(TABAN_YOL, encoding="utf-8") as fh:
            return json.load(fh).get("buyuklukler")
    except (OSError, ValueError):
        return None


def regresyonlar(sayac, taban):
    """Ratchet: hiçbir sayaç tabandan BÜYÜK olamaz."""
    return [(k, taban.get(k, 0), v) for k, v in sorted(sayac.items())
            if v > taban.get(k, 0)]


def buyumeler(simdiki, taban):
    """Mevcut bir ihlal BÜYÜDÜ mü — sayı değişmese bile.

    Ratchet'in eksik yarısı buydu: aynı dosya 601'den 952 satıra çıkarken
    sayaç 1'de kaldığı için kapı hiç kırmızı yanmadı. Yeni ihlal sayaç
    tarafından, mevcut ihlalin BÜYÜMESİ burada yakalanır.

    Taban bu alanı taşımıyorsa (eski biçim) boş döner: geriye uyum, ama
    `main` bunu görünür bir uyarıya çevirir — sessizce korumasız kalmaz.
    """
    if not taban:
        return []
    return [(k, taban[k], v) for k, v in sorted(simdiki.items())
            if k in taban and v > taban[k]]


def _taban_yaz(rapor):
    """Mevcut ölçümü ratchet tabanı olarak diske yazar."""
    os.makedirs(os.path.dirname(TABAN_YOL), exist_ok=True)
    with open(TABAN_YOL, "w", encoding="utf-8") as fh:
        json.dump({"sayaclar": rapor["sayaclar"],
                   "buyuklukler": rapor["buyuklukler"],
                   "not": "Ratchet tabanı: sayaçlar bunun üstüne çıkamaz "
                          "VE mevcut ihlaller büyüyemez (buyuklukler). "
                          "Düşürmek serbest ve teşvik edilir."},
                  fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"kalite: taban yazıldı → {os.path.relpath(TABAN_YOL, ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--baseline", action="store_true",
                    help="mevcut ölçümü ratchet tabanı olarak yaz")
    ap.add_argument("--check", action="store_true",
                    help="ratchet regresyonunda exit 1")
    ap.add_argument("--path", default=ROOT)
    args = ap.parse_args(argv)

    rapor = olc(args.path)
    taban = taban_oku()

    if args.baseline:
        _taban_yaz(rapor)
        return 0

    kotu = regresyonlar(rapor["sayaclar"], taban) if taban is not None else []
    taban_b = taban_buyuklukleri()
    buyuyen = buyumeler(rapor["buyuklukler"], taban_b)
    rapor["taban"] = taban
    rapor["regresyon"] = [{"sayac": k, "taban": a, "simdi": b}
                          for k, a, b in kotu]
    rapor["buyume"] = [{"ihlal": k, "taban": a, "simdi": b}
                       for k, a, b in buyuyen]
    # Eşiğe yakınlık PUSULADIR: rapora girer, çıkış koduna GİRMEZ (bin/marj.py).
    rapor["yaklasan"] = [{"oran": round(o, 3), "tur": t, "kimlik": k,
                          "deger": d, "limit": lim}
                         for o, t, k, d, lim in marj.bul(args.path,
                                                         rapor["esikler"])]

    if args.json:
        print(json.dumps(rapor, ensure_ascii=False, indent=2))
        return 1 if (args.check and (kotu or buyuyen)) else 0

    sayac_yaz(rapor, taban)
    ratchet_yaz(taban, taban_b, kotu, buyuyen)
    bulgu_yaz(rapor)
    return 1 if (args.check and (kotu or buyuyen)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
