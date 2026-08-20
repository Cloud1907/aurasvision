#!/usr/bin/env python3
"""Kurulum manifesti ve PROVENANCE — "hangi sürüm, nereden, ne zaman".

Neden ayrı modül: `kernel_dosyalari.py` "motorun hangi dosyaları var ve
proje sürümü kanoniğe göre nerede" sorusunu cevaplar; burası kurulumun
KİMLİĞİNİ taşır. İkisi ayrı değişme sebebi taşır.

H. Demir denetimi (2026-08-15): manifest yalnız `rel → sha256` kayıtları
taşıyordu; bağlı bir repoya bakıp "hangi Auras sürümü kurulu?" sorusunu
cevaplamak mümkün değildi. Sürüm kimliği olmayan dağıtım devralınamaz.

ÖNEMLİ: buradaki kayıt ezme kararının OTORİTESİ DEĞİLDİR (ADR-0002) —
otorite kanonik git geçmişidir. Manifest teşhis içindir.
"""
import datetime as dt
import json
import os
import subprocess

MANIFEST_REL = os.path.join(".agents", ".kernel-manifest.json")
MANIFEST_SURUM = 2


def _kaynak_kimligi(kaynak):
    """(commit, repo) — kurulumun HANGİ kernel sürümünden yapıldığı."""
    def git(*args):
        try:
            p = subprocess.run(["git", *args], cwd=kaynak, capture_output=True,
                               text=True, timeout=10)
            return p.stdout.strip() if p.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return git("rev-parse", "HEAD"), git("remote", "get-url", "origin")


def manifest_govde(dosyalar, kaynak):
    """Manifest gövdesi: dosya özetleri + KURULUM PROVENANCE'I.

    H. Demir denetimi (2026-08-15): manifest yalnız `rel → sha256` taşıyordu.
    Bağlı bir repoya bakıp "hangi Auras sürümü kurulu, nereden, ne zaman?"
    sorusunu cevaplamak mümkün değildi; uyumluluk kaynak klonunun git
    geçmişine emanetti. Sürüm kimliği olmayan dağıtım, devralınamaz.

    Not: bu alan ezme kararının OTORİTESİ DEĞİLDİR (ADR-0002) — otorite
    kanonik git geçmişidir. Buradaki kayıt teşhis içindir.
    """
    commit, repo = _kaynak_kimligi(kaynak)
    return {
        "schema_version": MANIFEST_SURUM,
        "kernel": {
            "commit": commit,
            "repo": repo,
            "kurulum": dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="seconds"),
        },
        "dosyalar": dosyalar,
        "not": "Ezme kararının otoritesi kanonik git geçmişidir (ADR-0002); "
               "bu kayıt teşhis içindir.",
    }


def _manifest_oku(hedef):
    try:
        with open(os.path.join(hedef, MANIFEST_REL), encoding="utf-8") as fh:
            veri = json.load(fh)
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def manifest_dosyalari(hedef):
    """{yol: sha} — v1 (düz sözlük) ve v2 (kernel+dosyalar) biçimini de okur.

    v1'i okuyamamak, kurulu projeyi "hiç kurulmamış" saymak olurdu ve /auras
    her dosyayı yeniden yazardı.
    """
    veri = _manifest_oku(hedef)
    if "dosyalar" in veri:
        return veri.get("dosyalar") or {}
    return {k: v for k, v in veri.items() if isinstance(v, str)}


def kurulu_surum(hedef):
    """{commit, repo, kurulum} — v1 manifest'te boş döner (bilinmiyor)."""
    return _manifest_oku(hedef).get("kernel") or {}
