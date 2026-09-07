"""Taşınabilir analiz motoru (src/akis_motoru.py) — model/GPU/kamera GEREKMEZ.

Motor iki noktadan sahte beslenir: `_Decoder` sentetik kareler üretir (bir
kişi çizgiyi soldan sağa geçer), `detector` YOLO yerine bilinen kutuları döner.
Böylece ölçülen şey decode/model değil, HATTIN KENDİSİ: kaynak seçimi
(substream/ana akış), hareket filtresi, takip → çizgi geçişi → olay yayını,
heartbeat sayaçları ve önizleme/tespit kancaları.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _numpy_var() -> bool:
    try:
        import numpy  # noqa: F401
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        return True
    except Exception:
        return False


class _Cfg:
    def __init__(self, d: dict) -> None:
        self.d = d

    def get(self, k, default=None):
        node = self.d
        for part in k.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


class KaynakSecimiTest(unittest.TestCase):
    """Substream/ana akış kararı — plaka açıksa ana akış, değilse substream."""

    def setUp(self):
        from src import akis_motoru
        self.m = akis_motoru
        self.cam = {"id": "k1", "source": "rtsp://cam/main", "url_sub": "rtsp://cam/sub"}

    def test_go2rtc_varsa_substream(self):
        cfg = _Cfg({"go2rtc": {"url": "http://localhost:1984"}})
        url, tip = self.m.kaynak_url(self.cam, cfg, {"count": True})
        self.assertEqual((url, tip), ("rtsp://localhost:8554/k1-sub", "substream"))

    def test_plaka_ana_akis(self):
        cfg = _Cfg({"go2rtc": {"url": "http://localhost:1984"}})
        url, tip = self.m.kaynak_url(self.cam, cfg, {"count": True, "plate": True})
        self.assertEqual((url, tip), ("rtsp://localhost:8554/k1", "ana akış"))

    def test_go2rtc_yoksa_dogrudan(self):
        cfg = _Cfg({})
        url, tip = self.m.kaynak_url(self.cam, cfg, {"count": True})
        self.assertEqual((url, tip), ("rtsp://cam/sub", "substream"))

    def test_substream_kapali(self):
        cfg = _Cfg({"detect": {"use_substream": False}})
        url, tip = self.m.kaynak_url(self.cam, cfg, {"count": True})
        self.assertEqual(url, "rtsp://cam/main")


@unittest.skipUnless(_numpy_var(), "numpy/torch/ultralytics gerekir (takipçi)")
class HatUctanUcaTest(unittest.TestCase):
    """Sentetik kare + sahte dedektör: çizgiyi geçen kişi TEK geçiş olayı üretir."""

    def test_cizgi_gecisi_olay_uretir(self):
        import numpy as np
        from src import akis_motoru

        W, H = 320, 180
        kareler = []
        # kişi x=40'tan x=280'e yürür (çizgi x=0.5 → 160 px), 40 karede
        for i in range(40):
            x = 40 + i * 6
            kareler.append((x, 60, x + 30, 150))

        class SahteDecoder(threading.Thread):
            """Gerçek _Decoder ile aynı arayüz: grab()/durum()/stop_flag."""
            olusan = []

            def __init__(self, cam_id, url, hw, extra=None):
                super().__init__(daemon=True)
                self.cam_id, self.url = cam_id, url
                self.lock = threading.Lock()
                self.i = 0
                self.stop_flag = False
                self.status, self.fps, self.hwaccel = "ok", 20.0, "sahte"
                self.dropped = self.decode_err = self.reconnects = 0
                SahteDecoder.olusan.append(self)

            def run(self):
                pass

            def grab(self):
                # her çağrıda bir sonraki kare (son kare kalır)
                idx = min(self.i, len(kareler) - 1)
                x1, y1, x2, y2 = kareler[idx]
                img = np.zeros((H, W, 3), dtype=np.uint8)
                img[y1:y2, x1:x2] = 200 + (idx % 3) * 10   # hareket filtresi geçsin
                self.i += 1
                return img, idx / 20.0, (W, H), self.i

            def durum(self):
                return {"status": "ok", "fps": 20.0, "dropped": 0, "decode_err": 0,
                        "reconnects": 0, "hwaccel": "sahte"}

        def detector(imgs):
            out = []
            for im in imgs:
                ys, xs = np.where(im[:, :, 0] > 0)
                if len(xs) == 0:
                    out.append((np.zeros((0, 4)), np.zeros(0), np.zeros(0, dtype=int)))
                else:
                    out.append((np.array([[xs.min(), ys.min(), xs.max(), ys.max()]], dtype=float),
                                np.array([0.9]), np.array([0], dtype=int)))
            return out

        class Bus:
            def __init__(self):
                self.olaylar = []

            def xadd(self, _s, fields, **kw):
                import json
                self.olaylar.append((fields["type"], fields["camera_id"],
                                     json.loads(fields["payload"])))

        class Store:
            def list_zones(self, cid):
                return []

            def faces_with_embedding(self):
                return []

            def close(self):
                pass

        cam = {"id": "k1", "source": "rtsp://x/main", "url_sub": "rtsp://x/sub",
               "tasks": {"count": True}, "enabled": True}
        cfg = _Cfg({"detect": {"fps": 1000, "model": "sahte"}, "worker": {"batch_max": 8},
                    "motion": {"enabled": True, "min_frac": 0.001},
                    "count": {"classes": [0], "cooldown_seconds": 0.5, "min_track_frames": 2},
                    "arama": {"enabled": False}, "paths": {"output_dir": tempfile.mkdtemp()}})
        bus = Bus()
        dets_alinan, kareler_alinan = [], []
        sayac = {"n": 0}

        def stop():
            sayac["n"] += 1
            return sayac["n"] > 60 or SahteDecoder.olusan[0].i >= len(kareler) + 3

        orig_dec = akis_motoru._Decoder
        akis_motoru._Decoder = SahteDecoder
        import src.store as store_mod
        orig_open = store_mod.open_store
        orig_merged = store_mod.merged_cameras
        store_mod.open_store = lambda cfg: Store()
        store_mod.merged_cameras = lambda cfg, s: [cam]
        try:
            akis_motoru.run_akis_worker(
                [cam], cfg, bus, detector=detector, stop=stop,
                on_frame=lambda cid: (lambda img: kareler_alinan.append(img.shape)),
                on_detections=lambda cid: (lambda d, fi: dets_alinan.append(d)))
        finally:
            akis_motoru._Decoder = orig_dec
            store_mod.open_store = orig_open
            store_mod.merged_cameras = orig_merged

        sayim = [o for o in bus.olaylar if o[0] == "count"]
        self.assertEqual(len(sayim), 1, bus.olaylar)
        # Varsayılan çizgi (0.5,0)→(0.5,1): A yanı sol, B yanı sağ değil — count._side
        # işaretine göre soldan sağa geçiş "out"tur (count.py ile aynı semantik;
        # yön UI'da 'BtoA' seçilerek çevrilir). Önemli olan TEK olay ve doğru kamera.
        self.assertEqual(sayim[0][2]["direction"], "out")
        self.assertEqual(sayim[0][1], "k1")
        # kancalar çalıştı: tespit listesi ve kutu çizili kare üretildi
        self.assertTrue(any(d for d in dets_alinan), "tespit kancası boş")
        self.assertTrue(kareler_alinan and kareler_alinan[0] == (H, W, 3))
        # substream seçildi (go2rtc yok → doğrudan url_sub)
        self.assertEqual(SahteDecoder.olusan[0].url, "rtsp://x/sub")


class DonanimTest(unittest.TestCase):
    def test_profil_alanlari(self):
        from src import donanim
        p = donanim.profil()
        for k in ("os", "cekirdek", "hwaccel", "oneri", "nvdec_motoru"):
            self.assertIn(k, p)
        self.assertIn(p["oneri"]["engine"], ("nvdec", "akis"))
        self.assertIsInstance(donanim.ozet_satiri(), str)

    def test_kullanim_bloklamaz(self):
        from src import donanim
        t = time.time()
        donanim.kullanim()
        self.assertLess(time.time() - t, 2.0)


if __name__ == "__main__":
    unittest.main()
