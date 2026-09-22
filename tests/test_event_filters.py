from datetime import datetime

import pytest
from fastapi import HTTPException

from src import server
from src.store import SqliteStore


@pytest.fixture
def event_store(tmp_path):
    store = SqliteStore(tmp_path / 'events.db')
    store.conn.executemany(
        'INSERT INTO plate_events (time,camera_id,plate) VALUES (?,?,?)',
        [('2026-09-20 10:00:00', 'entrance', '34 OLD 123'),
         ('2026-09-22 10:00:00', 'entrance', '34 ABC 123'),
         ('2026-09-22 11:00:00', 'parking', '34 ABC 456'),
         ('2026-09-22 12:00:00', 'entrance', '34 XYZ 789')])
    store.conn.execute("INSERT INTO alerts (time,camera_id,kind,ref,label) VALUES "
                       "('2026-09-22 10:30:00','entrance','fire_warning','zone','Duman')")
    store.commit()
    yield store
    store.close()


def test_combined_filters_run_before_limit(event_store):
    rows = event_store.recent_events(1, 'plate', 'entrance',
                                    start='2026-09-22T09:00:00Z',
                                    end='2026-09-22T11:00:00Z', q='ABC')
    assert [r['detail'] for r in rows] == ['34 ABC 123']


def test_pagination_and_literal_search(event_store):
    first = event_store.recent_events(2, 'plate')
    second = event_store.recent_events(2, 'plate', offset=2)
    assert len({r['detail'] for r in first + second}) == 4
    assert event_store.recent_events(q="%' OR 1=1 --") == []
    assert event_store.recent_events(q='%') == []


def test_fire_alerts_are_in_event_stream(event_store):
    rows = event_store.recent_events(tur='fire')
    assert len(rows) == 1
    assert rows[0]['detail'] == 'zone Duman'


def test_api_accepts_fire_and_passes_filters(monkeypatch):
    calls = []
    class Store:
        def recent_events(self, *args, **kwargs):
            calls.append((args, kwargs))
            return []
        def close(self): pass
    monkeypatch.setattr(server, '_store', Store)
    server.api_events(limit=50, tur='fire', kamera='entrance',
                      start='2026-09-22T12:00:00+03:00', end='', q='Duman', offset=50)
    assert calls[0][1]['start'] == '2026-09-22T09:00:00+00:00'
    assert calls[0][1]['offset'] == 50


@pytest.mark.parametrize('start,end', [('bad', ''), ('2026-09-23T00:00:00Z', '2026-09-22T00:00:00Z')])
def test_invalid_dates_are_rejected(start, end):
    with pytest.raises(HTTPException) as exc:
        server.api_events(limit=50, start=start, end=end, q='', offset=0)
    assert exc.value.status_code == 422
