"""Plaka okuma doğruluk ölçümü / model A-B kıyası.

"Hata yapmıyoruz" iddiası ancak ölçümle kurulur: bu araç bir saha videosunu
seçilen detektör+OCR ile işler, HAM ve KABUL EDİLEN okumaları ayrı raporlar,
her tespitin kırpılmış görüntüsünü diske yazar (insan gözüyle hızlı etiketleme)
ve varsa ground-truth listesiyle isabet/kaçırma döker.

Kullanım:
  # Okumaları + plaka kırpımlarını çıkar (etiketleme turu)
  .venv/bin/python scripts/plate_eval.py --source data/videos/otopark.mp4

  # Farklı OCR modeliyle aynı videoda A/B (çıktılar ayrı klasöre)
  .venv/bin/python scripts/plate_eval.py --source video.mp4 --ocr cct-s-v2-global-model

  # Ground truth ile skorla (dosya: her satırda videoda GERÇEKTEN görünen bir plaka)
  .venv/bin/python scripts/plate_eval.py --source video.mp4 --gt dogru_plakalar.txt

Çıktı klasörü: output/plate_eval/<video>_<ocr>/ — reads.csv + crops/ + özet.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config
from src.plate import _as_float_conf, _load_alpr, _vote, accept_read


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="video dosyası")
    ap.add_argument("--detector", default=None, help="fast-alpr detektör (vars: config)")
    ap.add_argument("--ocr", default=None, help="fast-plate-ocr modeli (vars: config)")
    ap.add_argument("--stride", type=int, default=None, help="her N karede bir (vars: config)")
    ap.add_argument("--gt", default=None, help="ground-truth: satır başına bir plaka")
    ap.add_argument("--out", default=None, help="çıktı klasörü (vars: output/plate_eval/...)")
    args = ap.parse_args()

    import cv2

    cfg = load_config()
    detector = args.detector or cfg.get("plate.detector", "yolo-v9-t-384-license-plate-end2end")
    ocr = args.ocr or cfg.get("plate.ocr", "global-plates-mobile-vit-v2-model")
    stride = args.stride or cfg.get("detect.vid_stride", 1)
    min_conf = cfg.get("plate.min_conf", 0.4)
    fmt = cfg.get("plate.format", "tr")

    out_dir = Path(args.out or f"output/plate_eval/{Path(args.source).stem}_{ocr}")
    crops = out_dir / "crops"
    crops.mkdir(parents=True, exist_ok=True)

    alpr = _load_alpr(detector, ocr, cfg.get("device", "auto"))
    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        raise SystemExit(f"Video açılamadı: {args.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    raw: list[dict] = []       # eşik/format öncesi her okuma
    accepted: list[dict] = []  # kabul kapısından geçenler (üretimdeki davranış)
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if stride > 1 and frame_idx % stride != 0:
            continue
        for i, pred in enumerate(alpr.predict(frame)):
            o = getattr(pred, "ocr", None)
            text = getattr(o, "text", None) if o else None
            conf = _as_float_conf(getattr(o, "confidence", None) if o else None)
            if not text:
                continue
            ham = text.replace(" ", "").upper()
            kabul = accept_read(text, conf, min_conf, fmt)
            raw.append({"frame": frame_idx, "ham": ham, "kabul": kabul or "",
                        "conf": round(conf, 3) if conf is not None else ""})
            # kırpım: insan doğrulaması için (dosya adında okunan metin)
            det = getattr(pred, "detection", None)
            bb = getattr(det, "bounding_box", None)
            if bb is not None:
                x1, y1, x2, y2 = (int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2))
                crop = frame[max(0, y1):y2, max(0, x1):x2]
                if crop.size:
                    tag = "ok" if kabul else "red"
                    cv2.imwrite(str(crops / f"f{frame_idx:06d}_{i}_{tag}_{ham}.jpg"), crop)
            if kabul:
                accepted.append({"plate": kabul, "confidence": conf,
                                 "frame_idx": frame_idx,
                                 "ts_seconds": round(frame_idx / fps, 2)})
    cap.release()

    voted = _vote(accepted)
    with open(out_dir / "reads.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["frame", "ham", "kabul", "conf"])
        w.writeheader()
        w.writerows(raw)

    print(f"\n— {Path(args.source).name} · detektör={detector} · ocr={ocr} · stride={stride}")
    print(f"ham okuma: {len(raw)} · kabul edilen: {len(accepted)} "
          f"(format/eşik reddi: {len(raw) - len(accepted)})")
    print(f"oylama sonrası araç: {len(voted)}")
    for v in voted:
        print(f"  {v['plate']:<10} okuma={v['count']:<3} conf={v['conf']}")

    if args.gt:
        gt = {line.strip().replace(" ", "").upper()
              for line in Path(args.gt).read_text().splitlines() if line.strip()}
        got = {v["plate"] for v in voted}
        tp, fp, fn = got & gt, got - gt, gt - got
        prec = len(tp) / len(got) if got else 0.0
        rec = len(tp) / len(gt) if gt else 0.0
        print(f"\nground truth: {len(gt)} plaka")
        print(f"  isabet (TP): {len(tp)} → {sorted(tp)}")
        print(f"  yanlış okuma (FP): {len(fp)} → {sorted(fp)}")
        print(f"  kaçırılan (FN): {len(fn)} → {sorted(fn)}")
        print(f"  precision={prec:.2%}  recall={rec:.2%}")
    print(f"\nçıktılar: {out_dir}/ (reads.csv + crops/)")


if __name__ == "__main__":
    main()
