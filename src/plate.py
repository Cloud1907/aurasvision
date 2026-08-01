"""Plaka okuma — fast-alpr (tespit + OCR).

Plaka METİN olduğu için eşleştirme düz string'tir (yüz embedding'inden kolay).
Asıl zorluk OCR doğruluğu: aynı geçişte birden çok kare okunup en güveniliri tutulur.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import akis
from .config import Config
from .evidence import kaydet as kanit_kaydet


@dataclass
class PlateResult:
    plates: set[str] = field(default_factory=set)
    total_reads: int = 0
    frames: int = 0
    reads: list[dict[str, Any]] = field(default_factory=list)
    voted: list[dict[str, Any]] = field(default_factory=list)  # [{plate,count,conf}]


# — Türk plaka formatı: İL(01-81) + HARF(1-3) + RAKAM(2-4) —
# Plakalarda Q, W, X ve Türkçe karakter (Ç,Ğ,İ,Ö,Ş,Ü) kullanılmaz.
_TR_LETTERS = set("ABCDEFGHIJKLMNOPRSTUVYZ")
# OCR'ın sık karıştırdığı karakterler — yalnız beklenen sınıfa göre düzeltilir
# (rakam beklenen yerde O→0, harf beklenen yerde 0→O; iki yönlü serbest değişim YOK)
_TO_DIGIT = str.maketrans("OQIZSBG", "0012586")
_TO_LETTER = str.maketrans("012568", "OIZSGB")
# geçerli (harf, rakam) blok uzunlukları: 34A1234 · 34AB123(4) · 34ABC12(3)
_TR_SHAPES = ((1, 4), (2, 3), (2, 4), (3, 2), (3, 3))


def normalize_tr(text: str) -> str | None:
    """Okumayı Türk plaka formatına oturtmaya çalışır; oturmuyorsa None.

    Pozisyon-bilinçli düzeltme: ilk 2 karakter rakam sınıfına, orta blok harf
    sınıfına, son blok rakam sınıfına çevrilir. Birden çok şekil uyarsa en az
    düzeltme gerektiren seçilir; eşit düzeltmeyle FARKLI sonuçlar çıkarsa
    (belirsizlik) okuma reddedilir — kritik sahada tahmin yerine sessiz kalmak yeğ.
    """
    t = text.replace(" ", "").replace("-", "").upper()
    best: str | None = None
    best_fix = 10**9
    for nl, nd in _TR_SHAPES:
        if len(t) != 2 + nl + nd:
            continue
        il = t[:2].translate(_TO_DIGIT)
        mid = t[2:2 + nl].translate(_TO_LETTER)
        son = t[2 + nl:].translate(_TO_DIGIT)
        if not (il.isdigit() and 1 <= int(il) <= 81):
            continue
        if not all(c in _TR_LETTERS for c in mid):
            continue
        if not son.isdigit():
            continue
        cand = il + mid + son
        fix = sum(a != b for a, b in zip(cand, t))
        if fix < best_fix:
            best, best_fix = cand, fix
        elif fix == best_fix and cand != best:
            return None   # eşit maliyetli iki farklı okuma → belirsiz, reddet
    return best


# — Yabancı plakalar —
# Türkiye'de yabancı plakalı araç sıradan: turist, TIR, sınır trafiği. Bunları
# "TR formatına uymuyor" diye atmak, ihlal eden aracın hiç görünmemesi demek.
#
# Ama kapıyı öylece açamayız: TR doğrulaması OCR gürültüsünü eleyen ANA
# savunmamız. "IL1O0" gibi bir çöp okuma, geçerli bir TR plakası kuramadığı
# için reddediliyor. Yabancı plakada bu yapısal savunma yok — ülkelerin
# formatları birbirinden farklı ve hepsini bilmiyoruz.
#
# Yerine iki şey konuyor:
#   1) Daha yüksek güven eşiği (plate.foreign_min_conf) — yapı doğrulayamıyorsak
#      OCR'ın kendine güvenine daha çok yaslanmak zorundayız
#   2) Makullük kontrolü — uzunluk, karakter kümesi, en az bir harf VE bir rakam
# Kabul edilen yabancı plaka UI'da ayrı etiketlenir; "doğrulanmış" gibi
# görünmesi, olmadığı bir güvence verirdi.
# Alt sınır 6: yapısal doğrulama yapamadığımız için tek elemede uzunluk kaldı.
# Gerçek yabancı plakalar 6+ karakterdir (Bulgar CB1234AH=8, Alman BMW1234=7,
# Gürcü AA123BB=7); OCR kırıntıları ("34O5", "IL1O0") 4-5 karakterde çıkar ve
# harf/rakam karışımı oldukları için başka hiçbir kontrole takılmıyorlardı.
# 6'dan kısa gerçek bir plakayı kaçırma pahasına, çöp okumayı kabul etmiyoruz.
_YABANCI_MIN_UZUNLUK = 6
_YABANCI_MAX_UZUNLUK = 10


def normalize_yabanci(text: str) -> str | None:
    """TR dışı plaka için makullük kapısı. Oturmuyorsa None.

    Karakter DÜZELTMESİ yapmaz — hangi konumda harf, hangisinde rakam
    beklendiğini bilmiyoruz; tahmin yürütmek yanlış plaka üretirdi.
    """
    t = text.replace(" ", "").replace("-", "").replace(".", "").upper()
    if not (_YABANCI_MIN_UZUNLUK <= len(t) <= _YABANCI_MAX_UZUNLUK):
        return None
    if not t.isalnum() or not t.isascii():
        return None
    if not any(c.isdigit() for c in t):
        return None
    if not any(c.isalpha() for c in t):
        return None
    if len(set(t)) < 3:      # "AAAA111" tipi okumalar OCR takılmasıdır
        return None
    return t


def plaka_turu(plate: str) -> str:
    """Kabul edilmiş bir plakanın türü: 'tr' veya 'yabanci'."""
    return "tr" if normalize_tr(plate) == plate else "yabanci"


def accept_read(text: str | None, conf: float | None, min_conf: float,
                fmt: str = "tr", yabanci_min_conf: float | None = None) -> str | None:
    """Ham OCR okumasını kabul filtresi: normalize + güven eşiği + format.

    Kabul edilirse (düzeltilmiş) plaka metnini, edilmezse None döndürür.
    conf=None eşiği BYPASS ETMEZ — güvensiz okuma kritik sahada veri değildir.
    Tek doğruluk kapısı burasıdır; test ekranı da worker da bundan geçer.

    fmt:
      tr          — yalnız TR formatı (en sıkı; TR dışı araç GÖRÜNMEZ)
      tr+yabanci  — önce TR denenir, olmazsa yabancı kapısından geçirilir
      none        — ham metin (yalnız test/serbest saha)
    """
    if not text:
        return None
    c = conf or 0.0
    if c < min_conf:
        return None
    plate = text.replace(" ", "").upper()
    if fmt == "tr":
        return normalize_tr(plate)
    if fmt in ("tr+yabanci", "tr+foreign"):
        tr = normalize_tr(plate)
        if tr:
            return tr
        # Yapısal doğrulama yok → güven eşiği yükseliyor
        esik = min_conf if yabanci_min_conf is None else yabanci_min_conf
        if c < esik:
            return None
        return normalize_yabanci(plate)
    return plate


def _lev(a: str, b: str) -> int:
    """Levenshtein mesafesi (kısa stringler için yeterli)."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _vote(reads: list[dict[str, Any]], max_dist: int = 2) -> list[dict[str, Any]]:
    """Çok-kareli oylama: benzer okumaları kümeler, her küme için en güvenilir
    metni seçer. Aynı aracın kareler arası ufak OCR farkları tek plakaya iner.
    """
    clusters: list[dict[str, Any]] = []  # {rep, members:[(text,conf)]}
    for r in sorted(reads, key=lambda x: -(x.get("confidence") or 0)):
        t = r["plate"]
        c = r.get("confidence") or 0.0
        hit = None
        for cl in clusters:
            if abs(len(cl["rep"]) - len(t)) <= 1 and _lev(cl["rep"], t) <= max_dist:
                hit = cl
                break
        if hit:
            hit["members"].append((t, c))
        else:
            # temsilci okumadan kare/zaman/kanıt bilgisini de taşı (DB olayı için).
            # reads güven skoruna göre sıralı geldiği için ilk üye = en güvenilir okuma.
            clusters.append({"rep": t, "members": [(t, c)],
                             "frame_idx": r.get("frame_idx", 0),
                             "ts_seconds": r.get("ts_seconds", 0.0),
                             "snapshot": r.get("snapshot", "")})
    out = []
    for cl in clusters:
        # küme içinde en sık + en güvenilir metni temsilci seç
        score: dict[str, float] = {}
        cnt: dict[str, int] = {}
        for t, c in cl["members"]:
            score[t] = score.get(t, 0.0) + (c or 0.5)
            cnt[t] = cnt.get(t, 0) + 1
        best = max(score, key=lambda k: (cnt[k], score[k]))
        confs = [c for _, c in cl["members"] if c]
        out.append({"plate": best, "count": len(cl["members"]),
                    "conf": round(sum(confs) / len(confs), 3) if confs else None,
                    "frame_idx": cl["frame_idx"], "ts_seconds": cl["ts_seconds"],
                    # Kanıt: kümenin EN GÜVENİLİR okumasının karesi (temsilci metni veren kare)
                    "snapshot": cl.get("snapshot", "")})
    return sorted(out, key=lambda x: -x["count"])


@functools.lru_cache(maxsize=1)
def _load_alpr(detector: str, ocr: str, device: str = "auto"):
    """fast-alpr ALPR örneğini bir kez yükler (model reuse).

    CUDA'da GPU provider (onnxruntime-gpu varsa); MPS/CPU'da CPU provider
    (Apple Silicon'da CoreML EP, yolo-v9 detektörünün dinamik şekliyle uyuşmuyor).
    """
    from fast_alpr import ALPR

    from .device import ort_providers

    providers = ort_providers(device)
    return ALPR(detector_model=detector, ocr_model=ocr,
                detector_providers=providers, ocr_providers=providers)


def _as_float_conf(conf) -> float | None:
    """OCR confidence float veya (karakter bazlı) liste olabilir → tek skora indir."""
    if conf is None:
        return None
    if isinstance(conf, (list, tuple)):
        vals = [float(x) for x in conf if x is not None]
        return sum(vals) / len(vals) if vals else None
    return float(conf)


def run_plate(source: str, cfg: Config, save_video: bool = False,
              store=None, camera_id: str = "", on_read=None,
              on_frame=None,
              should_stop: Callable[[], bool] | None = None) -> PlateResult:
    import cv2

    detector = cfg.get("plate.detector", "yolo-v9-t-384-license-plate-end2end")
    ocr = cfg.get("plate.ocr", "global-plates-mobile-vit-v2-model")
    min_conf = cfg.get("plate.min_conf", 0.4)
    fmt = cfg.get("plate.format", "tr")
    yabanci_conf = cfg.get("plate.foreign_min_conf", 0.75)
    vid_stride = cfg.get("detect.vid_stride", 1)
    camera_id = camera_id or Path(source).stem

    alpr = _load_alpr(detector, ocr, cfg.get("device", "auto"))

    cap = akis.ac(source, cfg)
    if not cap.isOpened():
        raise FileNotFoundError(f"Video açılamadı: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    writer = None
    if save_video:
        out_dir = Path(cfg.get("paths.output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        # Yalnız işlenen kareler yazılır (vid_stride) → gerçek süre için efektif fps
        writer = cv2.VideoWriter(str(out_dir / (Path(source).stem + "_plate.mp4")),
                                 fourcc, fps / max(vid_stride, 1), (w, h))

    res = PlateResult()
    frame_idx = 0
    while True:
        # İptal istendi → temiz çık (writer.release/oylama döngü sonrasında koşar)
        if should_stop is not None and should_stop():
            break
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if vid_stride > 1 and frame_idx % vid_stride != 0:
            continue
        res.frames += 1
        ts = frame_idx / fps

        for pred in alpr.predict(frame):
            ocr_res = getattr(pred, "ocr", None)
            text = getattr(ocr_res, "text", None) if ocr_res else None
            conf = _as_float_conf(getattr(ocr_res, "confidence", None) if ocr_res else None)
            plate = accept_read(text, conf, min_conf, fmt, yabanci_conf)
            if plate is None:
                continue
            res.plates.add(plate)
            res.total_reads += 1
            # Kanıt karesi: okunan plakanın kırpması + bağlam. Olmadan "doğru okudu mu"
            # sorusu denetlenemez (bkz. evidence.py — KVKK ve saklama süresi orada).
            det = getattr(pred, "detection", None)
            bb = getattr(det, "bounding_box", None)
            snap = kanit_kaydet(cfg, frame, camera_id, "plate",
                                box=(bb.x1, bb.y1, bb.x2, bb.y2) if bb is not None else None,
                                etiket=f"{plate}  ({conf:.2f})  kare {frame_idx}"
                                       if conf is not None else f"{plate}  kare {frame_idx}")
            res.reads.append({"plate": plate, "confidence": conf,
                              "frame_idx": frame_idx, "ts_seconds": round(ts, 2),
                              "snapshot": snap})
            if on_read:
                on_read(plate, conf, frame_idx, round(ts, 2))

        if writer is not None or on_frame is not None:
            drawn = alpr.draw_predictions(frame)
            # fast-alpr sürümüne göre ndarray veya .image taşıyan nesne dönebilir
            img = getattr(drawn, "image", drawn)
            if writer is not None:
                writer.write(img)
            if on_frame is not None:
                on_frame(img)

    cap.release()
    if writer is not None:
        writer.release()
    # Çok-kareli oylama: gürültülü okumaları konsolide et.
    # DB'ye kare başına değil ARAÇ başına tek satır yazılır (track bazlı olay).
    res.voted = _vote(res.reads)
    if store is not None:
        for v in res.voted:
            store.add_plate_event(camera_id, v["plate"], v["conf"], v["count"],
                                  v["ts_seconds"], v["frame_idx"],
                                  snapshot=v.get("snapshot", ""))
        store.commit()
    return res
