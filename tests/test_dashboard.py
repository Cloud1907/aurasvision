from datetime import datetime, timezone

import pytest

from src.store import SqliteStore


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(tmp_path / 'panel.db')
    s.conn.executemany('INSERT INTO alerts(time,camera_id,kind,ref,acked_at) VALUES(?,?,?,?,?)', [
        ('2026-09-21 20:59:59', 'cam', 'sigara', 'old', None),
        ('2026-09-21 21:00:00', 'cam', 'sigara', 'today', None),
        ('2026-09-22 08:00:00', 'cam', 'intrusion', 'today', '2026-09-22 09:00:00'),
        ('2026-09-22 09:00:00', 'test', 'fire_warning', 'test', None),
        ('2026-09-22 21:00:00', 'cam', 'sigara', 'tomorrow', None),
    ])
    s.commit()
    yield s
    s.close()


def test_alarm_period_is_half_open_and_backlog_is_separate(store):
    result = store.dashboard_alerts('2026-09-21 21:00:00', '2026-09-22 21:00:00', ['test'])
    assert result['total'] == 2
    assert result['pending'] == 1
    assert result['acknowledged'] == 1
    assert result['pending_all'] == 3
    assert sum(r['total'] for r in result['series']) == 2


def test_notification_feed_starts_at_latest_and_paginates_without_duplicates(store):
    initial = store.alert_feed(None, 2)
    assert initial['alerts'] == []
    assert initial['cursor'] == 5
    first = store.alert_feed(0, 2)
    second = store.alert_feed(first['cursor'], 2)
    assert [r['id'] for r in first['alerts'] + second['alerts']] == [1, 2, 3, 4]
    assert first['has_more']


def test_notification_feed_exposes_acknowledged_state(store):
    rows = store.alert_feed(2, 2)['alerts']
    assert rows[0]['acked_at'] is not None
