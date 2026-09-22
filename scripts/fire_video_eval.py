"""Tek saha videosunda yangın erken-uyarı kararlılık kabulü.

Bu araç yalnız gerçek model ağırlığıyla anlamlıdır. Model yoksa veya motor
paketi çalışmıyorsa sonuç uydurmaz; ``status=blocked`` raporu ve çıkış kodu 2
üretir. Kabul, sınıflandırma metriği değil operatör davranışıdır:

* görünür yangından sonra ilk alarm en geç belirlenen sürede gelmeli,
* görünür yangın boyunca ham tespitler arasındaki boşluk sınırı aşmamalı,
* elle işaretli negatif aralıklarda alarm oluşmamalı.

Örnek (müşteri videosunun elle doğrulanmış aralıkları):

  python scripts/fire_video_eval.py --video /path/video.mp4 \
    --positive-start 07:56 --positive-end 14:44 --negative 00:00-07:55
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.fire import model_yolu, run_fire  # noqa: E402


def zaman_coz(deger: str | float | int) -> float:
    """Saniye, MM:SS veya HH:MM:SS değerini saniyeye çevirir."""
    if isinstance(deger, (int, float)):
        return float(deger)
    parcalar = str(deger).strip().split(":")
    if not 1 <= len(parcalar) <= 3:
        raise ValueError(f"Geçersiz zaman: {deger}")
    try:
        sayilar = [float(x) for x in parcalar]
    except ValueError as e:
        raise ValueError(f"Geçersiz zaman: {deger}") from e
    if any(x < 0 for x in sayilar):
        raise ValueError(f"Zaman negatif olamaz: {deger}")
    toplam = 0.0
    for sayi in sayilar:
        toplam = toplam * 60.0 + sayi
    return toplam


def aralik_coz(deger: str) -> tuple[float, float]:
    """``başlangıç-bitiş`` zaman aralığını doğrular."""
    try:
        bas, bit = deger.split("-", 1)
    except ValueError as e:
        raise ValueError(f"Aralık başlangıç-bitiş biçiminde olmalı: {deger}") from e
    sonuc = (zaman_coz(bas), zaman_coz(bit))
    if sonuc[1] <= sonuc[0]:
        raise ValueError(f"Aralık bitişi başlangıçtan büyük olmalı: {deger}")
    return sonuc


def degerlendir(*, tespit_anlari: list[float], alarm_anlari: list[float],
                pozitif: tuple[float, float],
                negatifler: list[tuple[float, float]],
                azami_alarm_gecikmesi: float,
                azami_tespit_boslugu: float) -> dict:
    """Ham sürelerden makinece karar verilebilir kabul raporu üretir."""
    bas, bit = pozitif
    if bit <= bas:
        raise ValueError("Pozitif aralığın bitişi başlangıçtan büyük olmalı")
    if azami_alarm_gecikmesi < 0 or azami_tespit_boslugu < 0:
        raise ValueError("Kabul eşikleri negatif olamaz")

    tespitler = sorted(float(x) for x in tespit_anlari if bas <= float(x) <= bit)
    alarmlar = sorted(float(x) for x in alarm_anlari)
    pozitif_alarmlar = [x for x in alarmlar if bas <= x <= bit]
    negatif_alarmlar = [x for x in alarmlar
                        if any(nbas <= x <= nbit for nbas, nbit in negatifler)]

    azami_bosluk = _en_uzun_bosluk(tespitler, bas, bit)
    ilk_alarm = pozitif_alarmlar[0] if pozitif_alarmlar else None
    gecikme = ilk_alarm - bas if ilk_alarm is not None else None
    hatalar = _kabul_hatalari(gecikme, azami_bosluk, negatif_alarmlar,
                              azami_alarm_gecikmesi, azami_tespit_boslugu)
    return {
        "passed": not hatalar,
        "positive_interval_seconds": [bas, bit],
        "negative_intervals_seconds": [list(x) for x in negatifler],
        "detection_hits_in_positive": len(tespitler),
        "alarm_count": len(alarmlar),
        "first_alarm_seconds": ilk_alarm,
        "first_alarm_latency_seconds": None if gecikme is None else round(gecikme, 3),
        "max_detection_gap_seconds": round(azami_bosluk, 3),
        "negative_interval_alarms": negatif_alarmlar,
        "thresholds": {
            "max_alarm_latency_seconds": azami_alarm_gecikmesi,
            "max_detection_gap_seconds": azami_tespit_boslugu,
        },
        "failures": hatalar,
    }


def _en_uzun_bosluk(tespitler: list[float], bas: float, bit: float) -> float:
    if not tespitler:
        return bit - bas
    bosluklar = [tespitler[0] - bas, bit - tespitler[-1]]
    bosluklar.extend(b - a for a, b in zip(tespitler, tespitler[1:]))
    return max(bosluklar)


def _kabul_hatalari(gecikme, bosluk, negatif_alarmlar,
                    gecikme_esigi, bosluk_esigi) -> list[str]:
    hatalar = []
    if gecikme is None:
        hatalar.append("pozitif aralıkta alarm üretilmedi")
    elif gecikme > gecikme_esigi:
        hatalar.append(f"ilk alarm gecikmesi {gecikme:.2f} sn > {gecikme_esigi:.2f} sn")
    if bosluk > bosluk_esigi:
        hatalar.append(f"azami tespit boşluğu {bosluk:.2f} sn > {bosluk_esigi:.2f} sn")
    if negatif_alarmlar:
        hatalar.append(f"negatif aralıklarda {len(negatif_alarmlar)} alarm üretildi")
    return hatalar


def _sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _rapor_yaz(yol: Path, veri: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def _argumanlar(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", required=True)
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--positive-start", required=True)
    ap.add_argument("--positive-end", required=True)
    ap.add_argument("--negative", action="append", default=[],
                    help="Alarm çıkmaması gereken başlangıç-bitiş; tekrarlanabilir")
    ap.add_argument("--max-alarm-latency", type=float, default=10.0)
    ap.add_argument("--max-detection-gap", type=float, default=None)
    ap.add_argument("--out", default=str(ROOT / "output" / "fire_video_eval.json"))
    return ap.parse_args(argv)


def _onkosullar(a):
    out = Path(a.out)
    video = Path(a.video).expanduser().resolve()
    cfg = load_config(a.config)
    if not video.is_file():
        raise FileNotFoundError(f"Video bulunamadı: {video}")
    pozitif = (zaman_coz(a.positive_start), zaman_coz(a.positive_end))
    negatifler = [aralik_coz(x) for x in a.negative]
    model = model_yolu(str(cfg.get("fire.model", "models/fire.pt")))
    from src.dedektor import calisma_kapisi
    calisma_kapisi(str(cfg.get("fire.engine", "rfdetr")),
                   bool(cfg.get("fire.agpl_kabul", False)))
    return out, video, cfg, pozitif, negatifler, model


def _video_calistir(video, cfg):
    tespit_anlari: list[float] = []
    alarm_anlari: list[float] = []
    sonuc = run_fire(
        str(video), cfg, camera_id="saha-kabul",
        on_detection=lambda ts, _idx, ds: tespit_anlari.append(float(ts)) if ds else None,
        on_alert=lambda olay: alarm_anlari.append(float(olay["ts_seconds"])))
    return sonuc, tespit_anlari, alarm_anlari


def main(argv: list[str] | None = None) -> int:
    a = _argumanlar(argv)
    out, video = Path(a.out), Path(a.video).expanduser().resolve()
    try:
        out, video, cfg, pozitif, negatifler, model = _onkosullar(a)
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as e:
        rapor = {"status": "blocked", "passed": False, "video": str(video), "error": str(e)}
        _rapor_yaz(out, rapor)
        print(f"BLOKE: {e}", file=sys.stderr)
        return 2
    basladi = time.monotonic()
    try:
        sonuc, tespit_anlari, alarm_anlari = _video_calistir(video, cfg)
    except Exception as e:
        rapor = {"status": "error", "passed": False, "video": str(video),
                 "model": str(model), "model_sha256": _sha256(model),
                 "error": f"{e.__class__.__name__}: {e}"}
        _rapor_yaz(out, rapor)
        print(f"HATA: {rapor['error']}", file=sys.stderr)
        return 2
    azami_bosluk = (float(a.max_detection_gap) if a.max_detection_gap is not None
                    else float(cfg.get("fire.max_gap_seconds", 2.0)))
    rapor = degerlendir(
        tespit_anlari=tespit_anlari, alarm_anlari=alarm_anlari,
        pozitif=pozitif, negatifler=negatifler,
        azami_alarm_gecikmesi=float(a.max_alarm_latency),
        azami_tespit_boslugu=azami_bosluk)
    rapor.update({
        "status": "passed" if rapor["passed"] else "failed",
        "video": str(video),
        "model": str(model),
        "model_sha256": _sha256(model),
        "engine": str(cfg.get("fire.engine", "rfdetr")),
        "confidence": float(cfg.get("fire.conf", 0.35)),
        "analyzed_frames": sonuc.frames,
        "source_fps": sonuc.fps,
        "elapsed_seconds": round(time.monotonic() - basladi, 2),
    })
    _rapor_yaz(out, rapor)
    print(json.dumps(rapor, ensure_ascii=False, indent=2))
    return 0 if rapor["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
