#!/usr/bin/env python3
"""CI ve kanıt sözleşmesinin doğrulayıcıları.

Neden ayrı modül: `validate.py` KERNEL uygunluğunu topluca koşar; burası tek
bir soruyu cevaplar — "kanıt üreten boru hattı gerçekten kanıt üretiyor mu?".
Ayrım `validate.py`'yi kalite ratchet'inin altında tutar (ADR-0004) ve bu
doğrulamaların kendi değişme sebebini ayırır.

Ölçü DİZGE DEĞİL YAPI: `"validate.py" in text` yorum satırındaki ya da ölü
daldaki bir metni de "koşuyor" sayıyordu (H. Demir denetimi, 2026-08-15).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kur(check_fn):
    """validate.py'nin `check` fonksiyonunu enjekte eder (tek hata sayacı)."""
    global check
    check = check_fn


check = None

def test_workflow():
    path = os.path.join(ROOT, ".github", "workflows", "evidence.yml")
    check(os.path.isfile(path), "evidence.yml workflow yok")
    if not os.path.isfile(path):
        return
    data = yaml.safe_load(open(path, encoding="utf-8"))
    tetikleyiciler = data.get(True, data.get("on", {}))
    check("pull_request" in tetikleyiciler,
          "workflow: pull_request tetikleyicisi yok")
    # Elle tetikleme dayanıklılık gereğidir: 2026-08-06'da GitHub Actions
    # kesintisinde (githubstatus "Incident with Actions", 15:22Z) webhook
    # teslimatı bozuldu; otomatik olaylar hiç run üretmedi ama
    # workflow_dispatch çalışmaya devam etti. Bu tetikleyici olmadan kesinti
    # boyunca hiçbir PR bağımsız makine kanıtı üretemez.
    check("workflow_dispatch" in tetikleyiciler,
          "workflow: workflow_dispatch yok — Actions olay teslimi bozulduğunda "
          "kanıt elle üretilemez. evidence.yml'de 'on:' altına "
          "'workflow_dispatch:' ekle")
    # Denetim öncesi bu üç kontrol DİZGE ARAMASIYDI: `"validate.py" in text`
    # yorum satırındaki ya da ölü daldaki bir metni de "koşuyor" sayıyordu
    # (H. Demir bulgusu, 2026-08-15). Ölçü artık YAPI: gerçekten çalışan
    # adımların `run`/`uses` alanlarına bakılır.
    adimlar = []
    for job in (data.get("jobs") or {}).values():
        adimlar.extend((job or {}).get("steps") or [])
    komutlar = " ".join(str((a or {}).get("run") or "") for a in adimlar)
    kullanilan = [str((a or {}).get("uses") or "") for a in adimlar]
    check("validate.py" in komutlar,
          "workflow: kernel doğrulaması bir adımın `run` komutunda değil "
          "(yorumda geçmesi koşuyor demek değildir)")
    check("make_evidence.py" in komutlar,
          "workflow: evidence üretimi bir adımın `run` komutunda değil")
    check(any("upload-artifact" in u for u in kullanilan),
          "workflow: evidence artifact yükleyen `uses` adımı yok")

    # Tedarik zinciri: hareketli etiket deterministik kanıtı bozar; upstream
    # ele geçirilirse `@v4` saldırganın commit'ini getirir.
    for u in kullanilan:
        if not u or "@" not in u:
            continue
        _ad, _sep, ref = u.partition("@")
        check(re.fullmatch(r"[0-9a-f]{40}", ref.split()[0] if ref else ""),
              f"workflow: '{u}' tam commit SHA'sına sabitlenmemiş — "
              "hareketli etiket her koşuda farklı kod getirebilir")
    check(re.search(r"pip install[^\n]*==", komutlar),
          "workflow: Python bağımlılığı sürüme sabitlenmemiş "
          "(`pip install pyyaml` → `pip install \"pyyaml==X.Y.Z\"`)")


def test_evidence_roundtrip():
    schema = json.load(open(os.path.join(ROOT, "schemas",
                                         "evidence.schema.json"),
                            encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "evidence.json")
        digest_src = os.path.join(td, "report.txt")
        open(digest_src, "w").write("ornek rapor")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "make_evidence.py"),
             "--out", out, "--contract", "#0", "--task-class", "code-change",
             "--skill", "implement-change",
             "--check", "tests=passed", "--check", "lint=passed",
             "--digest", f"report={digest_src}",
             "--risk-provisional", "auto", "--risk-final", "auto"],
            capture_output=True, text=True, cwd=ROOT)
        check(proc.returncode == 0,
              f"make_evidence başarısız: {proc.stderr or proc.stdout}")
        if proc.returncode != 0:
            return
        ev = json.load(open(out, encoding="utf-8"))
        for key in schema["required"]:
            check(key in ev, f"evidence: zorunlu alan eksik '{key}'")
        check(re.match(r"^[0-9a-f]{7,40}$", ev["commit_sha"]),
              "evidence: commit_sha biçimi geçersiz")
        for name, dig in ev.get("digests", {}).items():
            check(re.match(r"^sha256:[0-9a-f]{64}$", dig),
                  f"evidence: digest biçimi geçersiz ({name})")
        for c in ev["checks"]:
            check(c["status"] in ("passed", "failed", "skipped"),
                  f"evidence: geçersiz check durumu {c}")
        proc2 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "make_evidence.py"),
             "--out", out, "--check", "tests=failed"],
            capture_output=True, text=True, cwd=ROOT)
        check(proc2.returncode == 1,
              "make_evidence: failed check'te non-zero dönmeli")
