#!/usr/bin/env python3
"""Toplu kişisel veri tarayıcı — repoya dökülmüş kişi listesini kapıya çevirir.

Bu bir SIR taraması DEĞİLDİR, ayrı bir boyuttur. Sır tarayıcısı "bu değer bir
anahtar mı" diye sorar; bu tarayıcı "bu dosya bir insan listesi mi" diye sorar.
İkisi farklı sorulardır ve biri diğerinin yerine geçmez.

Neden var (4Flow, 2026-08-07): `dotnet-backend/Unity.API/users_list.json`
bulundu — bir üretim API çıktısının dosyaya dökülmüş hâli; 20 kişinin adı,
soyadı ve kurumsal e-postası. `scan_secrets.py` o dosyaya "temiz" dedi ve
DOĞRU davrandı: parola/anahtar arıyordu, kişisel veri aramıyordu. Kapıda bu
boyut hiç yoktu. Olmayan koruma, zayıf korumadan tehlikelidir — çünkü
kullanıcı korunduğunu sanır.

KVKK bağlamı: ad + kurumsal e-posta kişisel veridir. Kod deposunda hata
ayıklama artığı olarak durması amaçla sınırlılık ve saklama süresi
ilkelerine aykırıdır. Repo private olsa bile: erişim genişleyebilir, repo
public olabilir, klon dışarı çıkabilir — ve geçmişten silmek yıkıcı bir iştir.

Kullanım:
  python3 scan_personal_data.py [--git] [--exclude GLOB] <dosya|dizin> [...]

Çıkış: 0 temiz · 1 bulgu · 2 kullanım/kapsam hatası (hiçbir dosya taranmadı).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Dosya keşfi, dışlama ve git modu scan_secrets ile AYNI olmalı: iki tarayıcı
# farklı dosya kümesi görürse "hangisi doğru" sorusu doğar ve kapı güvenilmez
# hâle gelir. Tek kaynak → tek kapsam.
import scan_secrets as ss  # noqa: E402

# Eşik TEK kayıt değil TOPLU DÖKÜM içindir. Bir yorumdaki iletişim adresi
# ihlal değil; 20 kişilik liste ihlaldir. Tek adres eşiği her repoda yanlış
# pozitif üretir — ve yanlış pozitif bir kapının en pahalı hatasıdır: birkaç
# kez tekrarlarsa insan kapıyı atlamayı öğrenir.
ESIK = 8

EPOSTA_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
# TC kimlik no adayı: 11 hane, ilk hane 0 olamaz. Bu YALNIZ ön elemedir —
# asıl karar tc_gecerli() sağlamasıdır.
TC_ADAY_RE = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")


def tc_gecerli(no):
    """TC kimlik numarası sağlaması tutuyor mu.

    Neden gerekli (denetim bulgusu 2026-08-08): sağlama olmadan 11 haneli
    HER sayı kimlik sayılıyordu. 30 sipariş numarası içeren sıradan bir
    seed dosyası "30 benzersiz TC kimlik no" diye push'u durdurdu. Sipariş
    no, barkod, hesap no — hepsi 11 hane olabilir ve hiçbiri kimlik değildir.
    Yanlış pozitif bir kapının en pahalı hatasıdır: birkaç kez tekrarlarsa
    insan kapıyı atlamayı öğrenir.

    Algoritma rastgele 11 hanelinin ~%99'unu eler:
      10. hane = ((1,3,5,7,9. toplamı)*7 - (2,4,6,8. toplamı)) mod 10
      11. hane = (ilk 10 hanenin toplamı) mod 10
    """
    if len(no) != 11 or not no.isdigit() or no[0] == "0":
        return False
    d = [int(c) for c in no]
    tek = d[0] + d[2] + d[4] + d[6] + d[8]
    cift = d[1] + d[3] + d[5] + d[7]
    if (tek * 7 - cift) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]

# Tanımı gereği kişi listesi olan dosyalar — ihlal değil, konvansiyon.
KISI_LISTESI = re.compile(
    r"(^|/)(AUTHORS|CONTRIBUTORS|CODEOWNERS|MAINTAINERS|\.mailmap|CHANGELOG)"
    r"(\.[\w]+)?$", re.I)


def dokum_mu(yol, metin):
    """(tur, adet) — dosya toplu kişisel veri taşıyor mu (yoksa None).

    Yalnız BENZERSİZ kayıt sayılır: aynı adresin 50 kez geçmesi döküm
    değildir, tekrardır.
    """
    if KISI_LISTESI.search(yol.replace(os.sep, "/")):
        return None
    epostalar = {m.group(0).lower() for m in EPOSTA_RE.finditer(metin)}
    if len(epostalar) >= ESIK:
        return "e-posta", len(epostalar)
    kimlikler = {m.group(0) for m in TC_ADAY_RE.finditer(metin)
                 if tc_gecerli(m.group(0))}
    if len(kimlikler) >= ESIK:
        return "TC kimlik no", len(kimlikler)
    return None


def tara(paths, exclude=(), git_only=False):
    """(bulgular, taranan_dosya_sayısı) — bulgu: (yol, tur, adet)."""
    bulgular, taranan = [], 0
    for yol in ss.iter_files(paths, exclude, git_only):
        taranan += 1
        try:
            if os.path.getsize(yol) > ss.MAX_BYTES:
                continue
            with open(yol, encoding="utf-8", errors="replace") as fh:
                metin = fh.read()
        except (OSError, UnicodeError):
            continue
        sonuc = dokum_mu(yol, metin)
        if sonuc:
            bulgular.append((yol, sonuc[0], sonuc[1]))
    return bulgular, taranan


def main(argv):
    exclude, paths, git_only, hata = ss.arguman_coz(argv)
    if hata:
        print(hata.replace("scan_secrets.py", "scan_personal_data.py"),
              file=sys.stderr)
        return 2
    bulgular, taranan = tara(paths, exclude, git_only)

    kok = (paths[0] if os.path.isdir(paths[0])
           else os.path.dirname(paths[0])) or "."
    desenler, muaf_hata = ss.muafiyet_yukle(kok, kapi="pii")
    if muaf_hata:
        print(f"HATA: {muaf_hata}", file=sys.stderr)
        return 2
    # Muafiyet dosyası SIR kapısıyla ortak ama KAPSAM ayrı: işaretsiz satır
    # yalnız secret kapısına uygulanır. Buraya muaf yazmak için gerekçede
    # açıkça `kapı: pii` (ya da `kapı: hepsi`) denmeli — bir kapının
    # muafiyeti başka kapıyı sessizce kapatamaz (denetim bulgusu 2026-08-08).
    sahte = [(y, 0, t, str(a)) for y, t, a in bulgular]
    kalan, bastirilan = ss.muafiyet_uygula(sahte, kok, desenler)

    if not taranan:
        print("HATA: hiçbir dosya taranmadı (yol yanlış ya da dışlama çok "
              "geniş) — bu 'temiz' DEĞİLDİR", file=sys.stderr)
        return 2
    for yol, _s, tur, adet in bastirilan:
        print(f"  muaf: {yol}  [{adet} benzersiz {tur}]")
    if not kalan:
        print(f"scan_personal_data: temiz — {taranan} dosya tarandı, "
              "toplu kişisel veri bulunamadı ✓")
        return 0
    print(f"scan_personal_data: {len(kalan)} dosyada toplu kişisel veri ✗")
    for yol, _s, tur, adet in kalan:
        print(f"  {yol}  → {adet} benzersiz {tur}")
    print("SONUÇ: FAIL — kişisel veri kod deposunda saklanmaz. Dosyayı kaldır; "
          "gerçekten gerekliyse gerekçesiyle .agents/secret-allowlist.txt'e yaz.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
