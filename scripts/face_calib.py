"""Yüz sayım kalibrasyonu — TEŞHİS scripti (üretim dışı).

run_face'i koşar, finalize edilen NİHAİ kimlikleri alır ve:
  1. Her kimliğin en kaliteli karesinden yüz kırpıntısı kaydeder (görsel kontrol),
  2. Temsilci embedding'ler arası pairwise cosine matrisini basar,
  3. 0.30-0.40 bandındaki (muhtemel aynı kişi) ve <0.25 (net farklı) çiftleri listeler.

KVKK: output/calib* GEÇİCİ teşhis klasörüdür — iş bitince silinir, commit edilmez.

Kullanım:
  .venv/bin/python scripts/face_calib.py [video] [çıkış_klasörü]
  (varsayılan: data/videos/store-aisle-detection.mp4, output/calib)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config                                      # noqa: E402
from src.face import _calm_frac, _cosine, _wander_ratio, run_face       # noqa: E402


def _rep(t) -> tuple:
    """Track'in temsilci embedding'i + (kare, bbox): en yüksek det_score'lu giriş."""
    if not t.embs:
        return None, 0, None
    _, emb, frame_idx, bbox = t.embs[0]
    return emb, frame_idx, bbox


def _pair_sim(a, b) -> float:
    """İki nihai kimlik arası benzerlik: embedding kümeleri arası MAX cosine."""
    if not a.embs or not b.embs:
        return 0.0
    return max(_cosine(x[1], y[1]) for x in a.embs for y in b.embs)


def save_crops(video: str, finals: list, out_dir: Path) -> None:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video)
    for t in finals:
        emb, frame_idx, bbox = _rep(t)
        if bbox is None or not frame_idx:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx - 1)
        ok, frame = cap.read()
        if not ok:
            continue
        x1, y1, x2, y2 = bbox
        pw, ph = (x2 - x1) * 0.2, (y2 - y1) * 0.2   # %20 pay
        h, w = frame.shape[:2]
        X1, Y1 = max(0, int(x1 - pw)), max(0, int(y1 - ph))
        X2, Y2 = min(w, int(x2 + pw)), min(h, int(y2 + ph))
        crop = frame[Y1:Y2, X1:X2].copy()
        if crop.size == 0:
            continue
        # Küçük kırpıntıda yüz kapanmasın: 3x büyüt, tid'i alta bantla yaz
        crop = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3),
                          interpolation=cv2.INTER_CUBIC)
        band = 24
        out = cv2.copyMakeBorder(crop, 0, band, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        cv2.putText(out, f"#{t.tid} n={t.n_frames}", (2, out.shape[0] - 7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        cv2.imwrite(str(out_dir / f"id_{t.tid}_n{t.n_frames}.jpg"), out)
    cap.release()
    print(f"kırpıntılar: {out_dir}/ ({len(list(out_dir.glob('id_*.jpg')))} dosya)")


def print_matrix(finals: list, thr: float, co_overlap: int) -> None:
    from src.face import _seen_overlap

    # det_tepe: track'in gördüğü en yüksek det_score (face.det_min_score ayarı için);
    # gezinti/boyut: merkez gezintisinin yüz boyutuna oranı (face.min_track_move ayarı
    # için — donmuş doku ~0); sakin: sakin adım oranı (face.min_calm_frac ayarı için —
    # gerçek yüz 0.48-1.00 bandında, seken doku 0.00-0.15 bandında ölçüldü).
    print("\nKimlik aralıkları [first_frame, last_frame] + tespit sayısı + filtre metrikleri:")
    for t in finals:
        print(f"  #{t.tid}: [{t.first_frame}, {t.last_frame}] n={t.n_frames} |seen|={len(t.seen)} "
              f"det_tepe={t.conf:.2f} gezinti/boyut={_wander_ratio(t):.3f} "
              f"sakin={_calm_frac(t):.2f}")

    tids = [t.tid for t in finals]
    print("\nPairwise cosine matrisi (tid × tid):")
    print("      " + "".join(f"{tid:>6}" for tid in tids))
    for a in finals:
        row = [f"{_pair_sim(a, b):6.2f}" if b.tid != a.tid else "     -"
               for b in finals]
        print(f"{a.tid:>6}" + "".join(row))

    # Tüm çiftler: skor + tespit-seti kesişimi + birleşMEme nedeni (final kimlikler
    # zaten ayrık: neden = veto | skor-altı | greedy-sıra).
    print(f"\nÇift dökümü (skor azalan; eşik={thr}, veto: kesişim>{co_overlap}):")
    pairs = []
    for i, a in enumerate(finals):
        for b in finals[i + 1:]:
            pairs.append((a.tid, b.tid, _pair_sim(a, b), _seen_overlap(a, b)))
    for x, y, sc, ovl in sorted(pairs, key=lambda v: -v[2]):
        if ovl > co_overlap:
            neden = "VETO(es-zamanli)"
        elif sc < thr:
            neden = "skor-alti"
        else:
            neden = "greedy-sira"   # skor yeter + veto yok ama zincir başka kümeye gitti
        print(f"  {x} ~ {y}: {sc:.3f}  kesisim={ovl}  {neden}")


def main() -> None:
    video = sys.argv[1] if len(sys.argv) > 1 else "data/videos/store-aisle-detection.mp4"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "output/calib")
    cfg = load_config()
    finals: list = []
    res = run_face(str(ROOT / video) if not Path(video).is_absolute() else video,
                   cfg, save_video=False, _debug_tracks=finals)
    print(f"video={video}")
    print(f"detections={res.detections} raw={res.raw_detections} frames={res.frames} "
          f"male={res.male} female={res.female}")
    print("nihai kimlikler: " +
          ", ".join(f"#{t.tid}(n={t.n_frames})" for t in finals))
    save_crops(str(ROOT / video) if not Path(video).is_absolute() else video,
               finals, out_dir if out_dir.is_absolute() else ROOT / out_dir)
    print_matrix(finals, cfg.get("face.reid_threshold", 0.30),
                 cfg.get("face.cooccur_frames", 2))


if __name__ == "__main__":
    main()
