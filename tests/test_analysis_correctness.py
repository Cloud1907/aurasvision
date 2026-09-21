"""Analiz doğruluğu regresyon testleri (#5).

Bu dosya model/GPU çalıştırmaz; olay toplama ve worker kararlarını saf girdilerle
doğrular. Özellikle yüksek trafikte sessiz eksik sayım üreten limitleri kapsar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src import count, server, worker
from src.config import Config
from src.store import SqliteStore


class _SummaryStore:
    def __init__(self) -> None:
        self.recent_calls: list[tuple[str, int]] = []

    def recent_events(self, limit: int):
        self.recent_calls.append(("events", limit))
        now = datetime.now(timezone.utc).isoformat()
        return [
            {"camera_id": "giris", "type": "count", "time": now},
            {"camera_id": "giris", "type": "plate", "time": now},
        ]

    def recent_alerts(self, limit: int, pending_only: bool = False):
        self.recent_calls.append(("alerts", limit))
        return []

    def event_summary(self, _since):
        return [{"camera_id": "giris", "count": 2, "count_events": 1,
                 "plate": 1, "face": 0, "last": "2026-09-21 10:00:00"}]

    def pending_alert_summary(self):
        return []

    def close(self):
        pass


def test_api_ozeti_olayi_bir_kez_sayar_ve_limitli_akisi_kullanmaz(monkeypatch):
    store = _SummaryStore()
    monkeypatch.setattr(server, "_store", lambda: store)

    sonuc = server.api_events_summary(hours=24)

    assert sonuc["cameras"] == [{
        "camera_id": "giris", "count": 2, "count_events": 1,
        "plate": 1, "face": 0, "alerts": 0,
        "last": "2026-09-21 10:00:00",
    }]
    assert store.recent_calls == []


def test_sqlite_ozeti_20000_olaydan_sonrasini_kesmez(tmp_path):
    store = SqliteStore(tmp_path / "summary.db")
    summary = getattr(store, "event_summary", None)
    assert callable(summary), "Özet doğrudan zaman aralığı üzerinden toplanmalı"

    rows = [("giris", i, "in", "Kapı", float(i), i) for i in range(20_001)]
    store.conn.executemany(
        "INSERT INTO count_events "
        "(camera_id, track_id, direction, zone, ts_seconds, frame_idx) "
        "VALUES (?, ?, ?, ?, ?, ?)", rows)

    sonuc = summary("2000-01-01 00:00:00")

    assert sonuc == [{
        "camera_id": "giris", "count": 20_001, "count_events": 20_001,
        "plate": 0, "face": 0, "last": sonuc[0]["last"],
    }]
    store.close()


class _ZoneStore:
    def list_zones(self, _camera_id: str):
        return [{
            "kind": "line", "name": "Araç kapısı",
            "points": [[0.1, 0.2], [0.9, 0.2]],
            "direction": "BtoA", "classes": ["car"],
        }]

    def close(self):
        pass


def test_kayitli_cizgi_siniflari_server_ve_worker_hattinda_korunur(monkeypatch):
    monkeypatch.setattr(server, "_store", _ZoneStore)

    assert server._saved_lines("cam") == [{
        "name": "Araç kapısı", "pts": [[0.1, 0.2], [0.9, 0.2]],
        "direction": "BtoA", "classes": ["car"],
    }]
    assert worker._saved_lines(_ZoneStore(), "cam")[0]["classes"] == ["car"]


def test_cizgi_siniflari_coco_kimliklerine_cevrilir_ve_eski_kayit_uyumludur():
    converter = getattr(count, "_line_class_ids", None)
    assert callable(converter), "Çizgi sınıfı için test edilebilir tek dönüşüm olmalı"

    assert converter({"classes": ["person"]}, {0}) == {0}
    vehicles = {1, 2, 3, 5, 7}
    assert converter({"classes": ["car"]}, {0}) == vehicles
    assert converter({"classes": ["person", "car"]}, {0}) == {0} | vehicles
    assert converter({"classes": []}, {0}) == {0}


def test_her_cizgi_yalniz_kendi_nesne_sinifini_sayar():
    lines = count._make_line_states([
        {"name": "İnsan", "pts": [[0.5, 0], [0.5, 1]], "classes": ["person"]},
        {"name": "Araç", "pts": [[0.5, 0], [0.5, 1]], "classes": ["car"]},
    ], 100, 100, {0})
    result = count.CountResult()
    hits, seen = {}, {}

    for tid, cid in ((10, 0), (20, 2)):
        for ts, box in ((1.0, [10, 10, 30, 40]), (2.0, [70, 10, 90, 40])):
            count._update_line_states(tid, box, cid, lines, hits, seen, "foot", 0,
                                      0.0, ts, int(ts), result, None, None, "cam")

    insan = next(line for line in lines if line["name"] == "İnsan")
    arac = next(line for line in lines if line["name"] == "Araç")
    assert insan["in"] + insan["out"] == 1
    assert arac["in"] + arac["out"] == 1
    assert len(result.events) == 2


def test_cizgi_ve_ihlal_yokken_worker_sayim_motorunu_baslatmaz(monkeypatch):
    class EmptyStore:
        def list_zones(self, _camera_id):
            return []

        def close(self):
            pass

    fresh = {"id": "cam", "source": "sample.mp4",
             "tasks": {"count": True, "plate": False, "face": False}}
    calls = []
    monkeypatch.setattr(worker, "open_store", lambda _cfg: EmptyStore())
    monkeypatch.setattr(worker, "merged_cameras", lambda _cfg, _store: [fresh])
    monkeypatch.setattr(count, "run_count", lambda *args, **kwargs: calls.append(kwargs))

    worker._run_camera(fresh, Config({"worker": {"loop_interval": 0}}), object())

    assert calls == []
    assert worker._STAGE["cam"] == "bitti"


def test_kaybolan_track_durumu_ttl_sonunda_tum_cizgilerden_silinir():
    prune = getattr(count, "_prune_track_state", None)
    assert callable(prune), "Track durumu için test edilebilir TTL temizliği olmalı"

    hits = {1: 4, 2: 8}
    seen = {1: 2.0, 2: 9.0}
    lines = [
        {"last": {1: -1.0, 2: 1.0}, "last_count": {1: 1.0, 2: 8.0}},
        {"last": {1: 2.0}, "last_count": {1: 1.5}},
    ]

    prune(hits, seen, lines, now=10.0, ttl=5.0)

    assert hits == {2: 8}
    assert seen == {2: 9.0}
    assert lines[0]["last"] == {2: 1.0}
    assert lines[0]["last_count"] == {2: 8.0}
    assert lines[1]["last"] == {}
    assert lines[1]["last_count"] == {}
