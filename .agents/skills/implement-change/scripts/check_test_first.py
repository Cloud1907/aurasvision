#!/usr/bin/env python3
"""TDD disiplini sinyali — değişen kaynağa karşılık test değişmiş mi?

Git diff'e bakar; değişen kaynak dosyaları ile değişen test dosyalarını ayırır.
Kaynak değişmiş ama HİÇ test değişmemişse uyarır (exit 1) — bu, test-önce
disiplininin bozulduğuna dair güçlü bir sinyaldir. Her kaynak için ad-eşleşmeli
test bulunamazsa bilgi notu düşer (exit 0; tek test birden çok kaynağı
kapsayabilir).

Bu bir SİNYAL'dir, kanıt değil — nihai kanıt CI test job'ıdır (AGENTS.md:
"kanıt > beyan"). RED aşamasını bu araç göremez; onu sen görürsün.

Kullanım:
  python3 check_test_first.py                 # çalışma ağacını HEAD ile kıyasla
  python3 check_test_first.py --base main     # main'e göre kıyasla (PR diff'i)
  python3 check_test_first.py --allow 'src/config/*' --allow '*.generated.ts'

Çıkış: 0 = disiplin sinyali temiz, 1 = kaynak değişmiş test değişmemiş,
2 = kullanım/git hatası.
"""
import argparse
import fnmatch
import os
import subprocess
import sys

# Test kabul edilen dosyalar (yaygın diller). Kaynak sayımından düşülür.
TEST_DIR_MARKERS = ("tests/", "test/", "__tests__/", "spec/", "specs/")
TEST_NAME_GLOBS = (
    "test_*.py", "*_test.py",             # Python (pytest/unittest)
    "*.test.js", "*.test.jsx", "*.test.ts", "*.test.tsx",
    "*.spec.js", "*.spec.jsx", "*.spec.ts", "*.spec.tsx",  # JS/TS
    "*_test.go",                          # Go
    "*Test.cs", "*Tests.cs", "*.Tests.cs",  # .NET
    "*_test.rb", "*_spec.rb",             # Ruby
    "*Test.java", "*Tests.java",          # Java
)

# Test gerektiren kaynak uzantıları.
SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".cs", ".go", ".rb", ".java",
    ".kt", ".php", ".rs", ".swift", ".vue", ".scala", ".c", ".cc", ".cpp",
    ".h", ".hpp", ".m", ".mm", ".ex", ".exs",
}

# Varsayılan olarak test gerektirmeyen yollar (dokümantasyon, konfig, meta).
DEFAULT_IGNORE_GLOBS = (
    "docs/*", "*.md", ".github/*", ".agents/*", ".claude/*",
    "*.json", "*.yml", "*.yaml", "*.toml", "*.ini", "*.cfg", "*.lock",
    "*.txt", "*.sql", "*.sh", "*.env", ".env*", "*.gitignore",
    "migrations/*", "**/migrations/*",
)


def _run_git(args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(2)
    return proc.stdout


def _durumlu(cikti):
    """`--name-status` çıktısını {yol: durum} sözlüğüne çevirir."""
    esleme = {}
    for satir in cikti.splitlines():
        if not satir.strip():
            continue
        parca = satir.split("\t")
        if len(parca) < 2:
            continue
        # Yeniden adlandırma (R100 eski yeni) → YENİ yol dikkate alınır.
        esleme[parca[-1].replace(os.sep, "/")] = parca[0][0]
    return esleme


def changed_files(base):
    """Değişen dosya yolları — SİLİNENLER HARİÇ (posix, repo köküne göre).

    Neden silme dışarıda: bu kural TDD'yi zorlamak için var — yeni davranışın
    önce testi yazılsın. SİLİNEN davranışın testi olmaz; olsa da o test de
    silinir. Ölü kod temizliğini "test yaz" diye bloklamak, temizliği pahalı
    yapar ve borcu büyütür.

    4Flow'da yaşandı (2026-08-07): kişisel veri taşıyan iki hata ayıklama
    artığı silindi, hiçbir kod onlara bağımlı değildi, tek satır davranış
    değişmedi — kapı yine de CI'ı kırdı. Kapı doğru şeyi yanlış vakada
    zorluyordu.

    Silme YANINDA bir değişiklik varsa o değişiklik normal kurala tabidir:
    muafiyet yalnız SAF silmeye uygulanır, silmenin arkasına gizlenen
    düzenlemeye değil.
    """
    durumlar = {}
    if base:
        durumlar.update(_durumlu(
            _run_git(["diff", "--name-status", f"{base}...HEAD"])))
        # Base kıyasında bile yerel commit'lenmemiş değişiklikleri kat.
        durumlar.update(_durumlu(_run_git(["diff", "--name-status", "HEAD"])))
    else:
        durumlar.update(_durumlu(_run_git(["diff", "--name-status", "HEAD"])))
        # Henüz izlenmeyen (yeni) dosyalar — durum bilgisi yok, "A" sayılır.
        for l in _run_git(["ls-files", "--others", "--exclude-standard"]).splitlines():
            if l:
                durumlar[l.replace(os.sep, "/")] = "A"
    return {yol for yol, durum in durumlar.items() if durum != "D"}


def is_test(path):
    p = path.lower()
    if any(m in p + "/" for m in TEST_DIR_MARKERS):
        return True
    base = os.path.basename(path)
    return any(fnmatch.fnmatch(base, g) or fnmatch.fnmatch(base.lower(), g.lower())
               for g in TEST_NAME_GLOBS)


def is_ignored(path, allow_globs):
    for g in (*DEFAULT_IGNORE_GLOBS, *allow_globs):
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(os.path.basename(path), g):
            return True
    return False


def is_source(path, allow_globs):
    ext = os.path.splitext(path)[1].lower()
    if ext not in SOURCE_EXT:
        return False
    if is_test(path):
        return False
    if is_ignored(path, allow_globs):
        return False
    return True


def has_matching_test(source, test_files):
    """source'un stem'iyle ad-eşleşmeli bir test değişti mi?"""
    stem = os.path.splitext(os.path.basename(source))[0]
    # .test/.spec zincirini de temizle (foo.component -> foo).
    for t in test_files:
        tbase = os.path.basename(t)
        if stem and stem.lower() in tbase.lower():
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="TDD disiplini sinyali.")
    ap.add_argument("--base", help="kıyas referansı (ör. main); yoksa HEAD")
    ap.add_argument("--allow", action="append", default=[],
                    help="test gerektirmeyen yol glob'u (tekrarlanabilir)")
    args = ap.parse_args()

    try:
        files = changed_files(args.base)
    except SystemExit:
        raise
    tests = sorted(f for f in files if is_test(f))
    sources = sorted(f for f in files if is_source(f, args.allow))

    if not sources:
        print("  temiz: test gerektiren kaynak değişikliği yok.")
        print("SONUÇ: PASS")
        return 0

    print(f"  değişen kaynak: {len(sources)}, değişen test: {len(tests)}")

    if not tests:
        print("  UYARI: kaynak değişmiş ama hiç test dosyası değişmemiş.")
        for s in sources:
            print(f"    · {s}")
        print("SONUÇ: FAIL — kriteri karşılayan test ekle "
              "ya da meşru istisnayı --allow ile kaydet.")
        return 1

    # Testler var; ad-eşleşmesi olmayan kaynakları bilgi olarak listele.
    unmatched = [s for s in sources if not has_matching_test(s, tests)]
    for s in sources:
        tag = "eşleşti" if s not in unmatched else "eşleşme yok"
        print(f"    · {s}  [{tag}]")
    if unmatched:
        print("  NOT: yukarıdaki 'eşleşme yok' kaynakları için ad-eşleşmeli test")
        print("       görülmedi — mevcut bir test bunları kapsıyorsa sorun yok,")
        print("       değilse kriter→test eşlemesini gözden geçir.")
    print("SONUÇ: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
