"""VideoAI CLI — tek giriş noktası.

Alt komutlar:
  count    kişi sayma + çizgi geçişi (YOLO + ByteTrack)
  plate    plaka okuma (fast-alpr)
  face     yüz tespit + anonim demografi (InsightFace)
  analyze  üçü birden tek videoda

Örnek:
  python -m src.cli count   --source data/videos/people.mp4 --save
  python -m src.cli plate   --source data/videos/traffic.mp4
  python -m src.cli face    --source data/videos/people.mp4
  python -m src.cli analyze --source data/videos/scene.mp4 --save
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .device import select_device
from .store import open_store


def _cam_id(source: str) -> str:
    return Path(source).stem or source


def cmd_count(args, cfg) -> int:
    from .count import run_count

    store = open_store(cfg)
    store.start_run("count", args.source, {"model": cfg.get("detect.model")})
    res = run_count(args.source, cfg, save_video=args.save, store=store,
                    camera_id=_cam_id(args.source))
    store.close()
    print(f"✓ Sayım bitti — IN: {res.in_count}  OUT: {res.out_count}  "
          f"(kare: {res.frames}, fps: {res.fps:.1f})")
    if args.save:
        print(f"  Çıktı videosu: output/ (annotated)")
    return 0


def cmd_plate(args, cfg) -> int:
    from .plate import run_plate

    store = open_store(cfg)
    store.start_run("plate", args.source)
    res = run_plate(args.source, cfg, save_video=args.save, store=store,
                    camera_id=_cam_id(args.source))
    store.close()
    print(f"✓ Plaka bitti — araç (oylama sonrası): {len(res.voted)}  "
          f"(ham okuma: {res.total_reads}, kare: {res.frames})")
    for v in res.voted:
        print(f"   • {v['plate']}  ×{v['count']}")
    return 0


def cmd_face(args, cfg) -> int:
    from .face import run_face

    store = open_store(cfg)
    store.start_run("face", args.source)
    res = run_face(args.source, cfg, save_video=args.save, store=store,
                   camera_id=_cam_id(args.source))
    store.close()
    print(f"✓ Yüz bitti — kişi (track): {res.detections}  "
          f"(ham tespit: {res.raw_detections}, kare: {res.frames})")
    print(f"   Anonim demografi → erkek: {res.male}  kadın: {res.female}  "
          f"ort. yaş: {res.avg_age:.0f}")
    return 0


def cmd_analyze(args, cfg) -> int:
    rc = 0
    print("── Sayım ──")
    rc |= cmd_count(args, cfg)
    print("── Plaka ──")
    try:
        rc |= cmd_plate(args, cfg)
    except Exception as e:  # plaka modülü/modeli yoksa pipeline'ı durdurma
        print(f"  (plaka atlandı: {e})")
    print("── Yüz ──")
    try:
        rc |= cmd_face(args, cfg)
    except Exception as e:
        print(f"  (yüz atlandı: {e})")
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="videoai", description="VideoAI — görüntü analitiği POC")
    p.add_argument("--config", default=None, help="config.yaml yolu")
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_ in [("count", "kişi sayma"), ("plate", "plaka okuma"),
                        ("face", "yüz + anonim demografi"), ("analyze", "üçü birden")]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--source", required=True, help="video dosyası / kamera id (0)")
        sp.add_argument("--save", action="store_true", help="annotated video kaydet")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    print(f"[device: {select_device(cfg.get('device', 'auto'))}]")

    dispatch = {"count": cmd_count, "plate": cmd_plate,
                "face": cmd_face, "analyze": cmd_analyze}
    return dispatch[args.command](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
