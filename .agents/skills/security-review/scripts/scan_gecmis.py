#!/usr/bin/env python3
"""Push aralığı secret taraması — geçmişe sızmış sırrı push kapısına çevirir.

Neden var (bağımsız inceleme, Codex 2026-08-12): pre-push'un index taraması
(`scan_secrets --git`) yalnız push ANINDAKİ içeriği görür. Commit A'da
eklenip commit B'de silinen sır index'te görünmez ama iki commit de push'la
uzak GEÇMİŞE gider — ve geçmişten sır geri alınamaz, ancak iptal edilir.
Bu doğrulayıcı remote_sha..local_sha aralığındaki HER commit'in EKLENEN
satırlarını scan_secrets kurallarından geçirir; kural/muafiyet sözleşmesi
tektir, burada kopyalanmaz.

Kullanım:
  python3 scan_gecmis.py --push-range <remote_sha> <local_sha> \
      [--exclude GLOB] <repo_kök>

remote_sha 40 sıfır ise (yeni dal) ya da yerelde yoksa (uzak bizden ileride)
aralık `local_sha --not --remotes` olur: uzak ref'lerin zaten taşıdığı
commit yeniden taranmaz, uzağa YENİ gidecek her şey taranır.

Çıkış: 0 temiz · 1 bulgu · 2 kullanım/araç hatası. Araç hatası "temiz"
DEĞİLDİR — çağıran (pre-push) ikisini de bloklar (fail-closed).

BİLİNEN SINIR: merge commit'in kendi diff'i (evil merge — yalnız merge'te
beliren içerik) taranmaz; `git log -p` merge diff'ini basmaz. Yan dalın
commit'leri aralıktaysa tek tek taranır, vaka bu sınırın dışındadır.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_secrets as ss  # noqa: E402

SIFIR_SHA = "0" * 40
COMMIT_SATIRI = re.compile(r"^[0-9a-f]{40}$")
# core.quotepath=off ile yol UTF-8 basılır; özel karakterde git yine de
# çift tırnak kullanabilir — tırnağı soy, kaçışı çözmeye çalışma (yol
# eşleşmese bile satır TARANIR, yalnız dışlama/şablon isabeti kaybolur).
YENI_DOSYA = re.compile(r'^\+\+\+ "?b/(.*?)"?$')
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def rev_argumanlari(kok, remote_sha, local_sha):
    """Taranacak commit kümesi. Yeni dal / bilinmeyen uzak SHA → yedek küme."""
    if remote_sha != SIFIR_SHA:
        p = subprocess.run(
            ["git", "-C", kok, "cat-file", "-e", remote_sha + "^{commit}"],
            capture_output=True)
        if p.returncode == 0:
            return [local_sha, "--not", remote_sha]
    return [local_sha, "--not", "--remotes"]


def _onizle(deger):
    return deger if len(deger) <= 12 else deger[:6] + "…" + deger[-3:]


def _dosya_atlanir(yol, exclude):
    return (os.path.splitext(yol)[1].lower() in ss.SKIP_EXT
            or ss.is_excluded(yol, exclude))


def gecmis_tara(kok, rev_args, exclude=()):
    """(bulgular, commit_sayısı, hata). Bulgu: (tam_yol, satır, kural,
    önizleme, kısa_sha) — ilk dört alan scan_secrets sözleşmesiyle aynı,
    muafiyet uygulaması oradan ödünç alınır.

    TEK `git log -p` süreci, akış hâlinde: commit başına ayrı süreç büyük
    aralıkta (yüzlerce commit) kapıyı dakikalara çeker; tek geçiş çıktıyı
    belleğe de yığmaz. -U0: bağlam satırı yok, her '+' gerçekten eklenendir.
    --format=%H: commit mesajı basılmaz, mesaj metni diff sanılamaz.
    """
    cmd = ["git", "-C", kok, "-c", "core.quotepath=off", "log",
           "--format=%H", "--no-color", "--no-renames", "-p", "-U0",
           *rev_args]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             errors="replace")
    except OSError as e:
        return None, 0, f"git çalıştırılamadı: {e}"
    bulgular, commit_sayisi = [], 0
    sha, yol, satir_no, sablon = "", None, 0, False
    for ham in p.stdout:
        satir = ham.rstrip("\n")
        if COMMIT_SATIRI.match(satir):
            sha, yol, commit_sayisi = satir, None, commit_sayisi + 1
        elif satir.startswith("+++ "):
            m = YENI_DOSYA.match(satir)
            # /dev/null (silinen dosya) ya da atlanan yol → tarama dışı
            yol = m.group(1) if m else None
            if yol and _dosya_atlanir(yol, exclude):
                yol = None
            sablon = bool(yol) and ss.sablon_dosyasi(yol)
        elif HUNK.match(satir):
            satir_no = int(HUNK.match(satir).group(1))
        elif yol and satir.startswith("+"):
            for kural, deger in ss.scan_line(satir[1:], sablon):
                bulgular.append((os.path.join(kok, yol), satir_no, kural,
                                 _onizle(deger), sha[:12]))
            satir_no += 1
    hata = p.stderr.read().strip()
    p.stdout.close()
    p.stderr.close()
    if p.wait() != 0:
        return None, commit_sayisi, hata or "git log başarısız"
    return bulgular, commit_sayisi, None


def mesaj_tara(kok, rev_args):
    """Commit MESAJLARINDAKİ sırlar — mesaj da push'la uzağa gider.

    Kanıtlanmış vaka (güvenlik denetimi, 2026-08-12): `git commit -m
    "fix: anahtar sk_live_..."` diff'te görünmez, eklenen-satır taraması
    temiz diyordu. %x01/%x02 ayraçları mesaj metninde pratikte geçmez;
    satır tabanlı ayrıştırma mesajın kendisiyle karışamaz.

    Yol tabanlı muafiyet mesaja UYGULANAMAZ (mesajın yolu yok); yanlış
    pozitifin kaçışı placeholder filtresi, son çare --no-verify (bilinçli).
    """
    p = subprocess.run(
        ["git", "-C", kok, "log", "--format=%H%x01%B%x02", *rev_args],
        capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        return None, p.stderr.strip() or "git log (mesaj) başarısız"
    bulgular = []
    for blok in p.stdout.split("\x02"):
        sha, ayrac, mesaj = blok.strip("\n").partition("\x01")
        if not ayrac:
            continue
        for i, satir in enumerate(mesaj.splitlines(), 1):
            for kural, deger in ss.scan_line(satir):
                bulgular.append((sha.strip()[:12], i, kural, _onizle(deger)))
    return bulgular, None


KULLANIM = ("kullanım: scan_gecmis.py --push-range <remote_sha> <local_sha> "
            "[--exclude GLOB] <repo_kök>")


def arguman_coz(argv):
    """((remote, local, exclude, kok), hata)."""
    remote = local = None
    exclude, yollar = [], []
    i = 1
    while i < len(argv):
        if argv[i] == "--push-range":
            if i + 2 >= len(argv):
                return None, "HATA: --push-range iki SHA ister\n" + KULLANIM
            remote, local = argv[i + 1], argv[i + 2]
            i += 3
        elif argv[i] == "--exclude":
            if i + 1 >= len(argv):
                return None, "HATA: --exclude bir GLOB ister\n" + KULLANIM
            exclude.append(argv[i + 1])
            i += 2
        else:
            yollar.append(argv[i])
            i += 1
    if remote is None or len(yollar) != 1 or not os.path.isdir(yollar[0]):
        return None, KULLANIM
    return (remote, local, exclude, yollar[0]), None


def main(argv):
    cozum, hata = arguman_coz(argv)
    if hata:
        print(hata, file=sys.stderr)
        return 2
    remote_sha, local_sha, exclude, kok = cozum
    rev_args = rev_argumanlari(kok, remote_sha, local_sha)
    bulgular, commit_sayisi, hata = gecmis_tara(kok, rev_args, exclude)
    if hata is not None:
        # Aralık kurulamadı ≠ temiz. Kapı bunu bloklamalı (fail-closed).
        print(f"HATA: geçmiş taraması koşamadı: {hata}", file=sys.stderr)
        return 2
    desenler, hata = ss.muafiyet_yukle(kok)
    if hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2
    mesaj_bulgular, hata = mesaj_tara(kok, rev_args)
    if hata is not None:
        print(f"HATA: mesaj taraması koşamadı: {hata}", file=sys.stderr)
        return 2
    bulgular, bastirilan = ss.muafiyet_uygula(bulgular, kok, desenler)
    if bastirilan:
        print(f"scan_gecmis: {len(bastirilan)} bulgu proje muafiyetiyle "
              f"bastırıldı ({ss.MUAFIYET_DOSYA}):")
        for tam, satir, kural, _o, sha in bastirilan:
            rel = os.path.relpath(tam, kok)
            print(f"  muaf: {sha} {rel}:{satir}  [{kural}]")
    return _raporla(kok, commit_sayisi, bulgular, mesaj_bulgular)


def _raporla(kok, commit_sayisi, bulgular, mesaj_bulgular):
    if commit_sayisi == 0:
        # Boş aralık meşrudur (aynı SHA'ya push) — ama görünür söylenir.
        print("scan_gecmis: aralıkta yeni commit yok — geçmiş taraması boş ✓")
        return 0
    if not bulgular and not mesaj_bulgular:
        print(f"scan_gecmis: temiz — {commit_sayisi} commit tarandı, eklenen "
              "satırlarda ve mesajlarda secret deseni yok ✓")
        return 0
    print(f"scan_gecmis: push aralığında {len(bulgular) + len(mesaj_bulgular)}"
          " olası secret ✗")
    for tam, satir, kural, onizleme, sha in bulgular:
        rel = os.path.relpath(tam, kok)
        print(f"  {sha} {rel}:{satir}  [{kural}]  → {onizleme}")
    for sha, satir, kural, onizleme in mesaj_bulgular:
        print(f"  {sha} (commit mesajı):{satir}  [{kural}]  → {onizleme}")
    print("SONUÇ: FAIL — sır GEÇMİŞTE: commit'i yeniden yaz (rebase/amend), "
          "anahtarı döndür (rotate); index'i temizlemek yetmez.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
