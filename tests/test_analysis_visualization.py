"""Analiz trendi ve video üstü çizgi görselleştirmesi regresyonları (#6)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from src import count
from src.store import SqliteStore


def test_sqlite_15_dakikalik_giris_cikis_trendi_doner(tmp_path):
    store = SqliteStore(tmp_path / "trend.db")
    trend = getattr(store, "count_trend", None)
    assert callable(trend), "Trend, store katmanında zaman aralığıyla toplanmalı"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    store.conn.executemany(
        "INSERT INTO count_events (time, camera_id, track_id, direction, zone) "
        "VALUES (?, ?, ?, ?, ?)",
        [(now, "giris", 1, "in", "Kapı"),
         (now, "giris", 2, "in", "Kapı"),
         (now, "giris", 3, "out", "Kapı")],
    )

    rows = trend("2000-01-01 00:00:00", 15)

    assert len(rows) == 1
    assert rows[0]["in_count"] == 2
    assert rows[0]["out_count"] == 1
    assert rows[0]["bucket"]
    store.close()


class _FakeCV2:
    FONT_HERSHEY_SIMPLEX = 0

    def __init__(self):
        self.arrows = []
        self.texts = []
        self.colors = []

    def arrowedLine(self, _img, start, end, color, _width, **_kwargs):
        self.arrows.append((start, end))
        self.colors.append(color)

    def line(self, _img, _start, _end, color, _width):
        self.colors.append(color)

    def circle(self, _img, _point, _radius, color, _width):
        self.colors.append(color)

    def putText(self, _img, text, origin, _font, _scale, color, _width):
        self.texts.append((text, origin))
        self.colors.append(color)

    def getTextSize(self, text, _font, _scale, _width):
        return (len(text) * 8, 12), 3


def test_sonuc_cizgisi_editor_rengi_yon_oku_ve_sinirlanmis_etiket_kullanir():
    cv2 = _FakeCV2()
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    state = {"name": "Çok uzun kapı çizgisi", "px": (1, 1, 118, 1),
             "flip": True, "in": 0, "out": 0}

    count._draw_line(cv2, image, state)

    assert cv2.arrows, "Sonuç çizgisi seçili giriş yönünü okla göstermeli"
    start, end = cv2.arrows[0]
    assert start[1] > end[1], "BtoA seçimi oku B tarafından A tarafına çevirmeli"
    assert count.LINE_COLOR_BGR in cv2.colors
    assert all(0 <= x < image.shape[1] and 0 <= y < image.shape[0]
               for _text, (x, y) in cv2.texts)
