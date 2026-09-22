"""Yangın olayının yerel bus ve PostgreSQL migration sözleşmesi."""
import unittest

from src.bus import BusStore, YerelBus
from src.config import Config
from src.store import PgStore


def test_yangin_on_uyarisi_kaydedilir_alarm_bildirim_uretir(tmp_path, monkeypatch):
    """K12: Her kademe fire olayıdır; yalnız alarm bekleyen uyarı üretir."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    giden = []
    monkeypatch.setattr("src.olay._web", lambda _cfg, alarm: giden.append(alarm))
    bus = YerelBus(Config({"paths": {"db_path": str(tmp_path / "fire.db")}}))
    store = BusStore(bus)
    temel = {"sinif": "duman", "conf": 0.82, "dogrulama": 4,
             "sure": 0.0, "ts_seconds": 12.0, "frame_idx": 40}
    store.add_fire_event("depo", {**temel, "durum": "on_uyari"})
    assert len(bus.store.recent_events(tur="fire")) == 1
    assert bus.store.recent_alerts() == []
    store.add_fire_event("depo", {**temel, "durum": "alarm", "sure": 3.2,
                                   "ts_seconds": 15.2, "frame_idx": 51,
                                   "snapshot": "evidence/depo.jpg",
                                   "clip": "evidence/depo.mp4"})
    assert [o["state"] for o in bus.store.recent_events(tur="fire")] == [
        "alarm", "on_uyari"]
    assert bus.store.recent_alerts()[0]["snapshot"] == "evidence/depo.jpg"
    assert len(giden) == 1 and giden[0]["tur"] == "fire_warning"
    bus.close()


class TestPgYanginMigration(unittest.TestCase):
    class Conn:
        def __init__(self):
            self.sql = []

        def execute(self, sql, *_args):
            self.sql.append(" ".join(str(sql).split()))
            if "information_schema.tables" in sql:
                return self.Result((1,))
            if "pg_get_constraintdef" in sql:
                return self.Result(("CHECK (kind IN ('line','fire','firemask'))",))
            return self.Result(None)

        def commit(self):
            pass

        class Result:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

    def test_mevcut_pg_kurulumu_fire_timescale_politikalarini_alir(self):
        """K28: Eski DB fire tablosuyla birlikte hypertable ve retention almalı."""
        store = PgStore.__new__(PgStore)
        store.conn = self.Conn()
        store._ensure_schema()
        sql = "\n".join(store.conn.sql)
        assert "create_hypertable('fire_events','time'" in sql
        assert "add_compression_policy('fire_events'" in sql
        assert "add_retention_policy('fire_events', INTERVAL '90 days'" in sql

    def test_pg_yangin_migration_iki_kez_guvenle_kosar(self):
        """K28: Migration expand-only ve idempotent olmalı."""
        store = PgStore.__new__(PgStore)
        store.conn = self.Conn()
        store._ensure_schema()
        store._ensure_schema()
        assert sum("CREATE TABLE IF NOT EXISTS fire_events" in s
                   for s in store.conn.sql) == 2
