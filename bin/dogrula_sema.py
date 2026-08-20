#!/usr/bin/env python3
"""Görev sınıfı sözleşmesinin doğrulayıcıları — profil + issue form.

Neden ayrı modül (`dogrula_ci.py` emsali): `validate.py` KERNEL uygunluğunu
topluca koşar; burası tek bir soruyu cevaplar — "görev sınıfı sözleşmesi her
yerde AYNI mı?". Ayrım `validate.py`'yi kalite ratchet'inin altında tutar
(ADR-0004) ve bu doğrulamaların kendi değişme sebebini ayırır.

Ayrılma anı ölçülüdür: dördüncü sınıf (`design`) denenirken `validate.py`
922/922'deydi — ratchet tabanının tam üstünde, tek satır bile büyüyemiyordu.
Tabanı yükseltmek borcu meşrulaştırırdı; doğru karşılık zaten kurulmuş olan
ayırma desenini (`dogrula_ci.py`) uygulamaktı.

GOREV_SINIFLARI burada yaşar çünkü sınıf listesinin TEK tanımı olması gerekir:
ölçüm 2026-08-16'da liste dört ayrı yerde ELLE tekrarlanıyordu (`validate.py`
üç nokta + `tests/test_mcp_kaydi.py`) ve issue form ile profiller de aynı
kümeyi ayrıca beyan ediyordu. Dört kopya, dördüncü sınıf eklenirken dördünü de
elle bulmayı gerektirdi — sürüklenmenin tanımı budur.
"""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Görev sınıflarının TEK tanımı. Sınıf = capability profili seçicisi; konu
# değil YETENEK SINIRI adlandırır (bkz. ADR-0005).
GOREV_SINIFLARI = ("code-change", "research", "incident", "design")


def kur(check_fn):
    """validate.py'nin `check` fonksiyonunu enjekte eder (tek hata sayacı)."""
    global check
    check = check_fn


check = None


def test_profiles(skill_names):
    """Profilleri doğrular ve sınıf→izinli skill kümesini döndürür."""
    prof_dir = os.path.join(ROOT, ".agents", "capability-profiles")
    required_classes = set(GOREV_SINIFLARI)
    seen, izinli_kume = set(), {}
    for f in sorted(os.listdir(prof_dir)):
        if not f.endswith(".yml"):
            continue
        path = os.path.join(prof_dir, f)
        data = yaml.safe_load(open(path, encoding="utf-8"))
        tc = data.get("task_class")
        seen.add(tc)
        izinli_kume[tc] = set(data.get("skills") or [])
        check(f == f"{tc}.yml", f"profil {f}: dosya adı task_class ile uyuşmuyor")
        for key in ("schema_version", "skills", "tools", "network",
                    "mcp", "evidence_required", "risk"):
            check(key in data, f"profil {f}: '{key}' alanı eksik")
        for s in data.get("skills", []):
            check(s in skill_names,
                  f"profil {f}: tanımsız skill '{s}' (kayıtlı: {sorted(skill_names)})")
        risk = data.get("risk", {})
        check(risk.get("escalation") == "upward_only",
              f"profil {f}: risk.escalation 'upward_only' olmalı")
        net = data.get("network", {})
        check(net.get("mode") in ("allowlist", "open-web", "none"),
              f"profil {f}: geçersiz network.mode '{net.get('mode')}'")
    check(seen >= required_classes,
          f"eksik profil sınıfı: {required_classes - seen}")
    return izinli_kume


def test_issue_form():
    path = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "work-contract.yml")
    check(os.path.isfile(path), "work-contract.yml issue form yok")
    if not os.path.isfile(path):
        return
    data = yaml.safe_load(open(path, encoding="utf-8"))
    ids = {b.get("id") for b in data.get("body", []) if isinstance(b, dict)}
    for needed in ("hedef", "gorev-sinifi", "kriterler", "kapsam",
                   "on-risk", "kanit"):
        check(needed in ids, f"issue form: '{needed}' alanı eksik")
    dropdowns = {b.get("id"): b for b in data.get("body", [])
                 if isinstance(b, dict) and b.get("type") == "dropdown"}
    if "gorev-sinifi" in dropdowns:
        opts = set(dropdowns["gorev-sinifi"]["attributes"]["options"])
        check(opts == set(GOREV_SINIFLARI),
              f"issue form: görev sınıfı seçenekleri profillere uymuyor: {opts}")
    required_flags = [b.get("validations", {}).get("required")
                      for b in data.get("body", []) if isinstance(b, dict)]
    check(all(required_flags), "issue form: tüm alanlar zorunlu olmalı")
