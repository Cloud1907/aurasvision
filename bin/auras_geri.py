#!/usr/bin/env python3
"""auras_geri — bağlı projedeki kernel iyileştirmesini kanoniğe geri taşır.

`/auras` tek yönlüdür: kanonik → proje. Ters yön yoktu; bu yüzden gerçek
baskının olduğu yerde (bağlı proje) yapılan kernel düzeltmeleri orada mahsur
kalıyordu — 2026-08-05'te 4cast'te üç tane bulundu, biri ezilme riskindeydi.
Bu araç o yolu açar: neyin yerel iş olduğunu tespit eder, gösterir, ve
istenirse kanonik çalışma ağacına alır (commit ETMEZ — inceleme insanındır).

Sınıflandırma kernel_dosyalari.sinifla'dan gelir; ayraç manifest değil kanonik
git geçmişidir (manifest yanılabilir, geçmiş yanılmaz).

Kullanım:
  python3 bin/auras_geri.py <proje-yolu>              # rapor
  python3 bin/auras_geri.py <proje-yolu> --diff       # farkları da bas
  python3 bin/auras_geri.py <proje-yolu> --al <rel>…  # kanoniğe al
  python3 bin/auras_geri.py --tara ~/Developer/GitHub # bağlı projeleri tara
  python3 bin/auras_geri.py <proje-yolu> --check      # yerel iş varsa exit 1
"""
import argparse
import difflib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kernel_dosyalari as kd  # noqa: E402


def _metin(yol):
    try:
        with open(yol, encoding="utf-8") as fh:
            return fh.readlines()
    except (OSError, UnicodeDecodeError):
        return None


def fark_sayisi(kanonik, hedef, rel):
    """(+eklenen, -silinen) — okunamayan/ikili dosyada (None, None)."""
    a = _metin(os.path.join(kanonik, rel))
    b = _metin(os.path.join(hedef, rel))
    if b is None:
        return None, None
    if a is None:
        return len(b), 0
    ekle = sil = 0
    for satir in difflib.unified_diff(a, b, n=0):
        if satir.startswith("+") and not satir.startswith("+++"):
            ekle += 1
        elif satir.startswith("-") and not satir.startswith("---"):
            sil += 1
    return ekle, sil


def diff_metni(kanonik, hedef, rel):
    a = _metin(os.path.join(kanonik, rel)) or []
    b = _metin(os.path.join(hedef, rel)) or []
    return "".join(difflib.unified_diff(
        a, b, fromfile=f"kanonik/{rel}", tofile=f"proje/{rel}"))


def incele(kanonik, hedef):
    yerel, geride = [], []
    ayni = 0
    for rel, sinif in kd.karsilastir(kanonik, hedef):
        if sinif == "ayni":
            ayni += 1
        elif sinif == "yerel":
            ekle, sil = fark_sayisi(kanonik, hedef, rel)
            yeni = not os.path.isfile(os.path.join(kanonik, rel))
            yerel.append({"dosya": rel, "eklenen": ekle, "silinen": sil,
                          "yeni": yeni})
        elif sinif == "geride":
            geride.append({"dosya": rel})
    return {"kanonik": kanonik, "proje": hedef, "yerel": yerel,
            "geride": geride, "ayni": ayni}


def bagli_projeler(kok):
    """Altında .agents/.kernel-manifest.json olan projeler (bir seviye)."""
    bulunan = []
    try:
        girisler = sorted(os.listdir(kok))
    except OSError:
        return bulunan
    for ad in girisler:
        yol = os.path.join(kok, ad)
        if os.path.isdir(yol) and os.path.isfile(
                os.path.join(yol, ".agents", ".kernel-manifest.json")):
            bulunan.append(yol)
    return bulunan


def yazdir(rapor, diff=False):
    ad = os.path.basename(rapor["proje"].rstrip("/"))
    print(f"GERİ TAŞIMA — {ad}")
    print(f"  proje  : {rapor['proje']}")
    print(f"  kanonik: {rapor['kanonik']}")
    print("")
    if rapor["yerel"]:
        print(f"  ▲ YEREL İŞ — kanonikte yok, taşınmayı bekliyor "
              f"({len(rapor['yerel'])})")
        for y in rapor["yerel"]:
            if y["yeni"]:
                olcu = "yeni dosya"
            elif y["eklenen"] is None:
                olcu = "ikili/okunamadı"
            else:
                olcu = f"+{y['eklenen']} -{y['silinen']}"
            print(f"     {y['dosya']:<46} {olcu}")
        print("")
    if rapor["geride"]:
        print(f"  ▼ GERİDE — kanonik daha yeni, /auras güncelleyecek "
              f"({len(rapor['geride'])})")
        for g in rapor["geride"]:
            print(f"     {g['dosya']}")
        print("")
    print(f"  {rapor['ayni']} dosya aynı.")
    if diff:
        for y in rapor["yerel"]:
            print("")
            print(diff_metni(rapor["kanonik"], rapor["proje"], y["dosya"])
                  or f"(fark basılamadı: {y['dosya']})")
    if rapor["yerel"]:
        ornek = rapor["yerel"][0]["dosya"]
        print("")
        print(f"  Fark:  python3 bin/auras_geri.py {rapor['proje']} --diff")
        print(f"  Al  :  python3 bin/auras_geri.py {rapor['proje']} "
              f"--al {ornek}")


def al(kanonik, hedef, rel_ler):
    """Proje dosyalarını kanonik ÇALIŞMA AĞACINA kopyalar (commit etmez)."""
    alinan = []
    for rel in rel_ler:
        kaynak = os.path.join(hedef, rel)
        if not os.path.isfile(kaynak):
            print(f"  atlandı (projede yok): {rel}")
            continue
        varis = os.path.join(kanonik, rel)
        os.makedirs(os.path.dirname(varis), exist_ok=True)
        shutil.copy2(kaynak, varis)
        alinan.append(rel)
        print(f"  alındı: {rel}")
    if alinan:
        print("")
        print("  Kanonik çalışma ağacına yazıldı — COMMIT EDİLMEDİ.")
        print("  Sırada: git diff ile incele, testleri koştur, sonra commit et.")
        print("  Doğrulama: python3 bin/validate.py && "
              "python3 -m unittest discover -s tests -q")
    return alinan


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("proje", nargs="?")
    ap.add_argument("--kanonik", default=ROOT)
    ap.add_argument("--tara", metavar="DIZIN")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--al", nargs="+", metavar="REL")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="taşınmamış yerel iş varsa exit 1")
    args = ap.parse_args(argv)

    kanonik = os.path.abspath(args.kanonik)
    if args.tara:
        hedefler = bagli_projeler(os.path.expanduser(args.tara))
    elif args.proje:
        hedefler = [os.path.abspath(os.path.expanduser(args.proje))]
    else:
        ap.error("proje yolu ya da --tara gerekli")

    hedefler = [h for h in hedefler if os.path.abspath(h) != kanonik]
    if not hedefler:
        print("Bağlı proje bulunamadı.")
        return 0

    if args.al:
        if len(hedefler) != 1:
            print("HATA: --al tek proje ile kullanılır.")
            return 2
        return 0 if al(kanonik, hedefler[0], args.al) else 1

    raporlar = [incele(kanonik, h) for h in hedefler]
    if args.json:
        print(json.dumps(raporlar if args.tara else raporlar[0],
                         ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(raporlar):
            if i:
                print("")
            yazdir(r, diff=args.diff)
    bekleyen = sum(len(r["yerel"]) for r in raporlar)
    return 1 if (args.check and bekleyen) else 0


if __name__ == "__main__":
    raise SystemExit(main())
