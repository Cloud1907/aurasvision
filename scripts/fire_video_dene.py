"""Bir video dosyasını yangın hattından geçirir; kutulu video + tespit zaman çizelgesi üretir.

Kullanım:
  python scripts/fire_video_dene.py --source <video.mp4> --cikti output/fire_dene

CLI `fire` komutundan farkı: (1) her işlenmiş kareyi kutulu olarak mp4'e yazar
(operatör "model ne gördü" diye bakabilsin), (2) kare başına ham tespitleri
JSON'a döker (eşik taraması sonradan yapılabilsin), (3) ilerleme basar.
Olay/alarm mantığı aynen src/fire.py (DumanTakip) — burada kopyalanmaz.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--cikti", default="output/fire_dene")
    ap.add_argument("--baslangic", type=float, default=0.0, help="sn — buradan başla")
    ap.add_argument("--sure", type=float, default=0.0, help="sn — 0 = sona kadar")
    ap.add_argument("--kirp", default="", help="x,y,w,h — kareyi kırp (ekran kaydında kamera alanı)")
    ap.add_argument("--karo", type=int, default=None, help="n×n karo (varsayılan: fire.tiles)")
    ap.add_argument("--video-yok", action="store_true", help="kutulu video yazma (hız)")
    a = ap.parse_args()

    import cv2

    from src import fire
    from src.config import load_config

    cfg = load_config()
    cikti = ROOT / a.cikti
    cikti.mkdir(parents=True, exist_ok=True)
    ded = fire._dedektor_kur(cfg)
    cap = cv2.VideoCapture(a.source)
    if not cap.isOpened():
        print(f"açılamadı: {a.source}")
        return 2
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    kirp = tuple(int(v) for v in a.kirp.split(",")) if a.kirp else None
    if kirp:
        w, h = kirp[2], kirp[3]
    karo = a.karo if a.karo is not None else int(cfg.get("fire.tiles", 1))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    toplam = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = max(1, int(cfg.get("fire.vid_stride", 3)))
    if a.baslangic > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, a.baslangic * 1000)
    takip = fire._takip_kur(cfg, w, h, None, None)
    yaz = None if a.video_yok else cv2.VideoWriter(
        str(cikti / "kutulu.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), max(1.0, fps / stride), (w, h))
    zaman: list[dict] = []
    olaylar: list[dict] = []
    idx = int(a.baslangic * fps)
    islenen = 0
    t0 = time.time()
    print(f"{w}x{h} @ {fps:.1f} fps · {toplam} kare · stride {stride} · "
          f"conf {cfg.get('fire.conf')} · karo {karo} · kırp {kirp} · pencere {cfg.get('fire.window_seconds')} sn / "
          f"{cfg.get('fire.confirm_frames')} kare", flush=True)
    while True:
        ok, kare = cap.read()
        if not ok:
            break
        idx += 1
        ts = idx / fps
        if a.sure and ts - a.baslangic > a.sure:
            break
        if idx % stride:
            continue
        islenen += 1
        if kirp:
            kare = kare[kirp[1]:kirp[1] + kirp[3], kirp[0]:kirp[0] + kirp[2]]
        tespitler = fire.tespit_karolu(ded, kare, karo)
        for d in tespitler:
            zaman.append({"ts": round(ts, 2), "sinif": str(d[0]), "conf": round(float(d[5]), 3),
                          "kutu": [round(float(v)) for v in d[1:5]]})
        for o in takip.guncelle(tespitler, ts):
            o = dict(o)
            o["ts"] = round(ts, 2)
            olaylar.append(o)
            print(f"  ! {o['durum']:9s} {o['sinif']:6s} {o.get('dogrulama', 0)} kare "
                  f"@ {ts:7.1f} sn  conf {o.get('conf', 0):.2f}", flush=True)
        if yaz is not None:
            cizili = fire._ciz(kare, tespitler)
            cv2.putText(cizili, f"{ts:7.1f}s", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (255, 255, 255), 2)
            yaz.write(cizili)
        if islenen % 500 == 0:
            hiz = islenen / max(time.time() - t0, 1e-6)
            print(f"  {ts:7.1f} sn · {islenen} kare · {hiz:.1f} kare/sn · "
                  f"tespit {len(zaman)} · olay {len(olaylar)}", flush=True)
    if yaz is not None:
        yaz.release()
    cap.release()
    (cikti / "tespitler.json").write_text(json.dumps(
        {"kaynak": a.source, "w": w, "h": h, "fps": fps, "stride": stride, "karo": karo, "kirp": kirp,
         "islenen_kare": islenen, "tespit": zaman, "olay": olaylar},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"bitti: {islenen} kare, {len(zaman)} tespit, {len(olaylar)} olay, "
          f"{time.time() - t0:.0f} sn → {cikti}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
