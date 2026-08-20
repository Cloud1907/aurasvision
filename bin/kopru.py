#!/usr/bin/env python3
"""Kanıt köprüsü: CI'ı GitHub runner'ından yerel makineye alır (ve geri verir).

Neden: private repolarda ücretsiz Actions kotası (2000 dk/ay) bitince BÜTÜN
işler bloke olur — testler koşmaz, kanıt üretilmez, PR'lar kilitlenir. Köprü,
kotadan bağımsız bir yerel runner kurarak işi sürdürür.

NE KAYBEDİLİR (bu araç bunu gizlemez): `AGENTS.md` CI kanıtını "bağımsız
makinede tekrarlanır" diye tanımlar. Köprü açıkken bu YANLIŞTIR — kanıtı
üreten makine ile kodu yazan makine aynıdır, ortak güven kökü kullanıcının
kendisidir. Köprü bir çözüm değil, ölçülü bir ödündür; kota dönünce kaldırılır.

Ölçülmüş sınırlar:
  - Runner kaydı REPO seviyesindedir. Kişisel hesapta organizasyon runner
    havuzu yoktur (ölçüm 2026-08-16: /orgs/<kullanıcı>/actions/runners → 404),
    yani her repo kendi kaydını yapmak zorundadır. Aynı makine hepsine ev
    sahipliği yapabilir; paylaşılan tek şey donanımdır.
  - Runner senin kullanıcı yetkinle koşar: ~/.npm, ~/.nuget, ~/Library/Caches
    geliştirme ortamınla ORTAKTIR. Hız buradan gelir, "temiz makine" garantisi
    de burada kaybolur.
  - PUBLIC repoya kurulum REDDEDİLİR: herkes PR açıp senin makinende kod
    çalıştırabilirdi. Bu bir tercih değil, sert kapıdır.

Kullanım:
  python3 bin/kopru.py --durum                     # hangi repoda köprü var
  python3 bin/kopru.py --kur SAHIP/REPO            # köprüyü kur
  python3 bin/kopru.py --kur SAHIP/REPO --adet 3   # 3 paralel runner
  python3 bin/kopru.py --kaldir SAHIP/REPO         # köprüyü kaldır
  python3 bin/kopru.py --yamala /yol/repo          # workflow'ları anahtara bağla

Anahtar: repo değişkeni `CI_RUNNER`. Workflow'lar
`runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}` yazar; değişken silinince
GitHub runner'ına kendiliğinden döner. Tek anahtar, iki yön.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ETIKET = "mac-bridge"          # runner etiketi = CI_RUNNER değişkeninin değeri
DEGISKEN = "CI_RUNNER"
KOK = os.path.expanduser("~")

RUNS_ON = "runs-on: ${{ vars.%s || 'ubuntu-latest' }}" % DEGISKEN

CONCURRENCY = """concurrency:
  # Aynı PR'a arka arkaya push atıldığında eski koşuyu iptal et.
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

"""


def gh(*args, json_cikti=False):
    """gh CLI çağırır. Hata çıktı koduysa None döner — çağıran karar verir."""
    sonuc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if sonuc.returncode != 0:
        return None
    metin = sonuc.stdout.strip()
    return json.loads(metin) if json_cikti and metin else metin


def repo_dizini(repo):
    return os.path.join(KOK, "actions-runner-" + repo.split("/")[-1].lower())


def gorunurluk(repo):
    return gh("repo", "view", repo, "--json", "visibility", "-q", ".visibility")


def runner_indir(dizin):
    """Resmî runner'ı indirir (zaten varsa dokunmaz). Kaynak: actions/runner."""
    if os.path.isfile(os.path.join(dizin, "config.sh")):
        return True
    surum = (gh("api", "/repos/actions/runner/releases/latest", "-q", ".tag_name") or "").lstrip("v")
    if not surum:
        return False
    mimari = "osx-arm64" if os.uname().machine == "arm64" else "osx-x64"
    url = ("https://github.com/actions/runner/releases/download/"
           f"v{surum}/actions-runner-{mimari}-{surum}.tar.gz")
    os.makedirs(dizin, exist_ok=True)
    tar = os.path.join(dizin, "runner.tar.gz")
    if subprocess.run(["curl", "-sSfL", "-o", tar, url]).returncode != 0:
        return False
    subprocess.run(["tar", "xzf", tar, "-C", dizin], check=True)
    os.remove(tar)
    return True


def yol_dosyasi(dizin):
    """LaunchAgent minimal PATH ile koşar; homebrew/dotnet yolları açıkça verilir.

    BİÇİM KRİTİK: runner `.path`i TEK BİR PATH DİZESİ olarak okur — satır satır
    yazılırsa yalnız ilk satır geçerli olur. Ölçüm 2026-08-16 (4Flow): satır
    satır yazılmış `.path` ile ilk koşular geçti (action'lar önbellekteydi),
    yeni bir action indirilmesi gerekince `tar: command not found` ile çöktü —
    yani hata KURULUMDA değil, günler sonra ilgisiz bir yerde patladı.
    """
    yollar = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin",
              "/usr/local/share/dotnet", os.path.join(KOK, ".dotnet/tools"),
              "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    with open(os.path.join(dizin, ".path"), "w") as f:
        f.write(":".join(yollar) + "\n")


def env_dosyasi(dizin):
    """Makineye özgü araç yolları — repoya DEĞİL runner'a yazılır.

    Ölçüm 2026-08-16 (4Flow mobile-tests): workflow yorumu "Android SDK
    ubuntu-latest imajında kurulu gelir" diyor ve bu doğru; self-hosted
    runner'da ise gelmez. Aynı yolu repo workflow'una mutlak olarak yazmak,
    o yolu olmayan HER makinede kapıyı kırar — o yüzden makine bilgisi
    makinede durur. Runner kök dizinindeki `.env`i kendisi okur.
    """
    satirlar = []
    sdk = os.path.join(KOK, "Library", "Android", "sdk")
    if os.path.isdir(sdk):
        satirlar += [f"ANDROID_HOME={sdk}", f"ANDROID_SDK_ROOT={sdk}"]
    if satirlar:
        with open(os.path.join(dizin, ".env"), "w") as f:
            f.write("\n".join(satirlar) + "\n")
    return satirlar


def tek_runner_kur(repo, dizin, ad):
    jeton = gh("api", "-X", "POST",
               f"/repos/{repo}/actions/runners/registration-token", "-q", ".token")
    if not jeton:
        return False
    komut = ["./config.sh", "--url", f"https://github.com/{repo}", "--token", jeton,
             "--name", ad, "--labels", ETIKET, "--work", "_work",
             "--unattended", "--replace"]
    if subprocess.run(komut, cwd=dizin, capture_output=True).returncode != 0:
        return False
    for adim in (["./svc.sh", "install"], ["./svc.sh", "start"]):
        subprocess.run(adim, cwd=dizin, capture_output=True)
    return True


def kur(repo, adet):
    gor = gorunurluk(repo)
    if gor is None:
        print(f"HATA: {repo} okunamadı (gh yetkisi?)", file=sys.stderr)
        return 2
    if gor != "PRIVATE":
        print(f"RED: {repo} {gor}. Public repoda self-hosted runner, PR açan "
              "HERKESE senin makinende kod çalıştırma hakkı verir.", file=sys.stderr)
        return 2

    kurulan = 0
    for sira in range(1, adet + 1):
        dizin = repo_dizini(repo) + ("" if sira == 1 else f"-{sira}")
        if not runner_indir(dizin):
            print(f"  ✗ runner {sira}: indirilemedi", file=sys.stderr)
            continue
        yol_dosyasi(dizin)
        for satir in env_dosyasi(dizin):
            print(f"    .env: {satir}")
        ad = f"{os.uname().nodename.split('.')[0]}-{ETIKET}-{sira}"
        if tek_runner_kur(repo, dizin, ad):
            print(f"  ✓ runner {sira}/{adet}: {ad}")
            kurulan += 1
        else:
            print(f"  ✗ runner {sira}: kaydedilemedi", file=sys.stderr)

    if not kurulan:
        return 1
    gh("variable", "set", DEGISKEN, "--repo", repo, "--body", ETIKET)
    print(f"  ✓ {DEGISKEN}={ETIKET} ayarlandı")
    print(f"\nSıradaki: workflow'ları anahtara bağla → bin/kopru.py --yamala <yerel-yol>")
    print("Kanıt artık BAĞIMSIZ MAKİNEDEN gelmiyor — merge notlarında bunu yaz.")
    return 0


def kaldir(repo):
    kayitli = gh("api", f"/repos/{repo}/actions/runners", json_cikti=True) or {}
    for runner in kayitli.get("runners", []):
        gh("api", "-X", "DELETE", f"/repos/{repo}/actions/runners/{runner['id']}")
        print(f"  ✓ runner silindi: {runner['name']}")
    if gh("variable", "delete", DEGISKEN, "--repo", repo) is not None:
        print(f"  ✓ {DEGISKEN} silindi — CI GitHub runner'ına döndü")
    print("\nYerel servisler duruyor. Tamamen kaldırmak için:")
    print(f"  cd {repo_dizini(repo)} && ./svc.sh stop && ./svc.sh uninstall")
    return 0


def durum():
    depolar = gh("repo", "list", "--limit", "100", "--json",
                 "nameWithOwner,visibility", json_cikti=True) or []
    basildi = False
    for depo in depolar:
        ad = depo["nameWithOwner"]
        akis = gh("api", f"/repos/{ad}/actions/workflows", "-q",
                  "[.workflows[] | select(.state==\"active\")] | length")
        if not akis or akis == "0":
            continue
        degisken = gh("variable", "list", "--repo", ad)
        acik = degisken is not None and DEGISKEN in degisken
        runner = gh("api", f"/repos/{ad}/actions/runners", "-q", ".total_count") or "0"
        isaret = "🔴 KÖPRÜ AÇIK" if acik else "  github"
        print(f"  {isaret:16} {ad:34} {akis} workflow, {runner} runner "
              f"({depo['visibility'].lower()})")
        basildi = True
    if not basildi:
        print("  aktif workflow'u olan repo yok")
    return 0


def yamala(yol):
    """Yerel checkout'taki workflow'ları anahtara bağlar + concurrency ekler."""
    dizin = os.path.join(yol, ".github", "workflows")
    if not os.path.isdir(dizin):
        print(f"HATA: {dizin} yok", file=sys.stderr)
        return 2
    for ad in sorted(os.listdir(dizin)):
        if not ad.endswith((".yml", ".yaml")):
            continue
        dosya = os.path.join(dizin, ad)
        with open(dosya) as f:
            metin = onceki = f.read()
        if not metin.strip():
            continue
        metin = re.sub(r"^(\s*)runs-on: ubuntu-latest\s*$",
                       lambda m: m.group(1) + RUNS_ON, metin, flags=re.M)
        if "concurrency:" not in metin:
            metin = re.sub(r"^jobs:", CONCURRENCY + "jobs:", metin, count=1, flags=re.M)
        if metin != onceki:
            with open(dosya, "w") as f:
                f.write(metin)
            print(f"  ✓ {ad}")
    print("\nDeğişiklikleri gözden geçir ve commit et. Platforma bağlı adımlar "
          "(indirilen ikililerin mimarisi, apt bağımlılıkları) elle kontrol edilmeli.")
    return 0


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    grup = ayristirici.add_mutually_exclusive_group(required=True)
    grup.add_argument("--durum", action="store_true", help="köprü durumunu listele")
    grup.add_argument("--kur", metavar="SAHIP/REPO", help="köprüyü kur (yalnız private)")
    grup.add_argument("--kaldir", metavar="SAHIP/REPO", help="köprüyü kaldır")
    grup.add_argument("--yamala", metavar="YOL", help="yerel workflow'ları anahtara bağla")
    ayristirici.add_argument("--adet", type=int, default=3, help="runner sayısı (varsayılan 3)")
    arg = ayristirici.parse_args()

    if arg.durum:
        return durum()
    if arg.kur:
        return kur(arg.kur, max(1, arg.adet))
    if arg.kaldir:
        return kaldir(arg.kaldir)
    return yamala(arg.yamala)


if __name__ == "__main__":
    sys.exit(main())
