"""Yangın video döngüsünün gözlemlenebilirlik ve kaynak kapatma sözleşmesi."""
import unittest
from unittest.mock import patch

import numpy as np

from src.config import Config
from src.fire import run_fire
from src.fire_runtime import analyze_includes_fire


class Cap:
    def __init__(self, kare_sayisi=1):
        self.i = 0
        self.kare_sayisi = kare_sayisi
        self.released = False

    def read(self):
        self.i += 1
        if self.i <= self.kare_sayisi:
            return True, np.zeros((20, 20, 3), dtype="uint8")
        return False, None

    def release(self):
        self.released = True


def test_tumunu_analiz_et_yangin_yetenegi_yokken_fire_calistirmaz():
    """K35: Varsayılan kapalı pilot, eski 'analyze' akışını bozmamalı."""
    assert analyze_includes_fire("analyze", {"available": False}) is False
    assert analyze_includes_fire("analyze", {"available": True}) is True
    assert analyze_includes_fire("fire", {"available": False}) is True


def test_tespit_callbacki_video_zamanini_tasir():
    """K34: Saha kabul aracı ham tespit zamanlarını kopya döngü kurmadan almalı."""
    class Ded:
        def tespit(self, _kare):
            return [("alev", 1, 1, 10, 10, 0.8)]

    gorulen = []
    with patch("src.fire._dedektor_kur", return_value=Ded()), \
         patch("src.fire._kaynak_ac", return_value=(Cap(2), 20, 20, 10.0)):
        run_fire("video.mp4", Config({"fire": {"vid_stride": 1}}),
                 on_detection=lambda ts, idx, ds: gorulen.append((ts, idx, ds)))
    assert [round(x[0], 1) for x in gorulen] == [0.1, 0.2]
    assert [x[1] for x in gorulen] == [1, 2]
    assert gorulen[0][2][0][0] == "alev"


def test_model_hatasinda_video_kaynagi_serbest_birakilir():
    """K33: Dedektör çökerse RTSP/video handle ve bekleyen DB yazısı kapanmalı."""
    class Ded:
        def tespit(self, _kare):
            raise RuntimeError("model çalışma anında çöktü")

    class Store:
        committed = False

        def commit(self):
            self.committed = True

    cap, store = Cap(), Store()
    with patch("src.fire._dedektor_kur", return_value=Ded()), \
         patch("src.fire._kaynak_ac", return_value=(cap, 20, 20, 25.0)):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "model çalışma"):
            run_fire("video.mp4", Config({"fire": {"vid_stride": 1}}),
                     store=store, camera_id="depo")
    assert cap.released
    assert store.committed
