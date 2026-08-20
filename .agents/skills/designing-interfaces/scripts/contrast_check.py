#!/usr/bin/env python3
"""WCAG 2.2 kontrast oranı denetleyici — tasarım kalitesini ölçülebilir yapar.

Kullanım:
  python3 contrast_check.py "#1a1a1a on #ffffff"
  python3 contrast_check.py "#777 on #fff" "#0c447c on #e6f1fb large"

Her çift için oran + PASS/FAIL. Herhangi biri FAIL ise exit 1.
'large' etiketi büyük metin eşiğini (3:1) kullanır; varsayılan normal (4.5:1).
"""
import re
import sys


def _hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        raise ValueError(f"geçersiz renk: #{c}")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lin(v):
    v /= 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    l1, l2 = _lum(_hex(fg)), _lum(_hex(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def main():
    if len(sys.argv) < 2:
        print("kullanım: contrast_check.py '#fg on #bg [large]' ...")
        return 2
    any_fail = False
    for spec in sys.argv[1:]:
        m = re.match(r"\s*(\S+)\s+on\s+(\S+)\s*(large)?\s*$", spec, re.I)
        if not m:
            print(f"  ? ayrıştırılamadı: {spec!r} (biçim: '#fg on #bg [large]')")
            any_fail = True
            continue
        fg, bg, large = m.group(1), m.group(2), bool(m.group(3))
        try:
            r = ratio(fg, bg)
        except ValueError as e:
            print(f"  ? {e}")
            any_fail = True
            continue
        threshold = 3.0 if large else 4.5
        ok = r >= threshold
        any_fail = any_fail or not ok
        tag = "PASS" if ok else "FAIL"
        kind = "büyük" if large else "normal"
        print(f"  {tag}  {fg} on {bg}  = {r:.2f}:1  (eşik {threshold} / {kind})")
    if any_fail:
        print("SONUÇ: FAIL — renk/rol düzelt ve tekrar çalıştır.")
        return 1
    print("SONUÇ: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
