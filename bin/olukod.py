#!/usr/bin/env python3
"""Ölü kod tespiti — kullanılmayan import'lar.

Neden ayrı modül: `kalite.py` BOYUT ve KARMAŞIKLIK sayar; burası ÖLÜ KOD
arar. Ayrı soru, ayrı değişme sebebi — ve ayrı tutulmazsa kalite.py 400
satır sınırını aşıyor (kendi kapısına takıldı, 2026-08-16).

Neden yeni bir ARAÇ değil: ölçüldü 2026-08-16 — ruff bu repoda 316 bulgu
üretiyor ve ilk dört kural (200 bulgu) ya kozmetik ya da mimariyle ÇATIŞIYOR
(`PLW1510 subprocess-without-check`: bu repo çıkış kodunu bilerek okur,
exception fırlatmaz). Gerçek olan kısım 12 satırlık ölü koddu ve ratchet onu
hiç görmüyordu. 300 gürültüyü yönetmek için yeni bir CI bağımlılığı eklemek
yerine evdeki alet kullanıldı: `ast`. `kapsam_bekcisi.py` aynı dersi zaten
öğrenmişti — metin deseni değil, dili kendi aracıyla oku.

Kapsam sınırı dürüstçe: yalnız Python, yalnız import. Kullanılmayan yerel
değişken ve ölü fonksiyon BU ARAÇTA YOK; onlar elle bulundu (2026-08-16) ve
tekrarı ölçülürse buraya eklenir.
"""
import ast

def olu_importlar(metin):
    """Python dosyasında kullanılmayan import adları (satır no listesi).

    Neden yeni bir araç DEĞİL: ölçüldü 2026-08-16 — ruff bu repoda 316 bulgu
    üretiyor ve ilk dört kural (200 bulgu) ya kozmetik ya da mimariyle
    ÇATIŞIYOR (`PLW1510 subprocess-without-check`: bu repo çıkış kodunu
    bilerek okur). Gerçek olan kısım 12 satırlık ölü koddu ve ratchet onu
    hiç görmüyordu. 300 gürültüyü yönetmek için yeni bir CI bağımlılığı
    eklemek yerine, evdeki alet (`ast`) kullanıldı — `kapsam_bekcisi.py`
    aynı dersi zaten öğrenmişti: metin deseni değil, dili kendi aracıyla oku.

    `# noqa` taşıyan satır ATLANIR: yeniden dışa verme (re-export) meşrudur
    ve `kernel_dosyalari.py` bunu bilinçle yapar.
    """
    try:
        agac = ast.parse(metin)
    except SyntaxError:
        return []
    satirlar = metin.splitlines()
    adaylar = _import_adlari(agac, satirlar)
    if not adaylar:
        return []
    kullanilan = _kullanilan_adlar(agac)
    # Dize içi atıf (tip yorumu, doctest) sessizce kaçmasın: import satırları
    # dışındaki gövdede `ad.` geçiyorsa kullanılmış say.
    govde = "\n".join(s for s in satirlar if not s.lstrip().startswith("import "))
    return sorted((satir, ad) for ad, satir in adaylar.items()
                  if ad not in kullanilan and f"{ad}." not in govde)


def _import_adlari(agac, satirlar):
    """{ad: satır} — `# noqa` taşıyan satır atlanır (meşru re-export)."""
    adaylar = {}
    for dugum in ast.walk(agac):
        if not isinstance(dugum, (ast.Import, ast.ImportFrom)):
            continue
        # `from __future__ import X`: derleyici direktifi, ad olarak asla
        # KULLANILMAZ — "ölü" saymak her modern dosyayı yanlış pozitif yapar
        # (AurasVision ölçümü: 32 dosya, hepsi `annotations`).
        if isinstance(dugum, ast.ImportFrom) and dugum.module == "__future__":
            continue
        ham = satirlar[dugum.lineno - 1] if dugum.lineno <= len(satirlar) else ""
        if "noqa" in ham:
            continue
        for takma in dugum.names:
            if takma.name != "*":
                adaylar[(takma.asname or takma.name).split(".")[0]] = dugum.lineno
    return adaylar


def _kullanilan_adlar(agac):
    """Gövdede adıyla ya da `ad.x` biçiminde geçen tüm isimler."""
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Name):
            adlar.add(d.id)
        elif isinstance(d, ast.Attribute) and isinstance(d.value, ast.Name):
            adlar.add(d.value.id)
    return adlar
