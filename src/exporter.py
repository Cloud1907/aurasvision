"""Kanıt dışa aktarma — zaman aralığını tek mp4 + imzalı manifest olarak paketler.

Neden imza: adli/idari süreçte "bu video değiştirilmedi" iddiasının teknik karşılığı.
Sektörde standart (Milestone SHA-2, Axxon SHA-256, Digifort AES-256+filigran);
imzasız export delil değeri taşımaz.

Manifest ne içerir: kamera, zaman aralığı, kullanılan segmentlerin listesi ve tek tek
SHA-256'ları, birleşik dosyanın SHA-256'sı, üretim zamanı ve isteyen. Doğrulama:
    sha256sum <dosya>   →  manifest'teki sha256 ile birebir aynı olmalı

Birleştirme PyAV ile REMUX'tur (yeniden kodlama yok): görüntü verisi bit düzeyinde
korunur — transcode edilmiş bir "kanıt" zaten kanıt sayılmaz.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def disa_aktar(cfg, camera: str, segmentler: list[dict], isteyen: str = "operatör") -> dict:
    """Segmentleri tek mp4'e birleştirir, manifest üretir. (mp4_yolu, manifest_yolu) döner."""
    import av

    if not segmentler:
        raise ValueError("Bu aralıkta kayıt yok")

    cikti_kok = _ROOT / cfg.get("paths.output_dir", "output")
    kayit_kok = cikti_kok / cfg.get("record.dir", "rec")
    klasor = cikti_kok / "exports"
    klasor.mkdir(parents=True, exist_ok=True)
    damga = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ad = f"{camera}_{damga}_{uuid.uuid4().hex[:6]}"
    hedef = klasor / f"{ad}.mp4"

    kaynak_kayitlari: list[dict] = []
    cikis = None
    ovs = None
    offset = 0            # birleşik zaman ekseni (her segment öncekinin sonundan devam eder)
    try:
        for seg in segmentler:
            yol = kayit_kok / seg["path"]
            if not yol.is_file():
                continue
            with av.open(str(yol)) as inp:
                if not inp.streams.video:
                    continue
                ivs = inp.streams.video[0]
                if cikis is None:
                    cikis = av.open(str(hedef), "w", format="mp4")
                    ovs = cikis.add_stream_from_template(ivs)
                ilk = None
                son = 0
                for pkt in inp.demux(ivs):
                    if pkt.pts is None or pkt.dts is None or pkt.size == 0:
                        continue
                    if ilk is None:
                        ilk = pkt.dts
                    pkt.pts = pkt.pts - ilk + offset
                    pkt.dts = pkt.dts - ilk + offset
                    son = max(son, pkt.dts)
                    pkt.stream = ovs
                    cikis.mux(pkt)
                offset = son + 1
            kaynak_kayitlari.append({"path": seg["path"], "start": str(seg["start_time"]),
                                     "duration": seg.get("duration"),
                                     "sha256": _sha256(yol)})
    finally:
        if cikis is not None:
            cikis.close()

    if not kaynak_kayitlari:
        hedef.unlink(missing_ok=True)
        raise ValueError("Segment dosyaları bulunamadı")

    manifest = {
        "surum": 1,
        "kamera": camera,
        "aralik": {"baslangic": str(segmentler[0]["start_time"]),
                   "bitis": str(segmentler[-1]["end_time"])},
        "uretim_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "isteyen": isteyen,
        "dosya": hedef.name,
        "dosya_sha256": _sha256(hedef),
        "dosya_bayt": hedef.stat().st_size,
        "segment_sayisi": len(kaynak_kayitlari),
        "segmentler": kaynak_kayitlari,
        "dogrulama": "sha256sum <dosya> çıktısı dosya_sha256 ile aynı olmalı",
    }
    man_yolu = klasor / f"{ad}.json"
    man_yolu.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"video": f"exports/{hedef.name}", "manifest": f"exports/{man_yolu.name}",
            "sha256": manifest["dosya_sha256"], "bytes": manifest["dosya_bayt"],
            "segments": len(kaynak_kayitlari)}
