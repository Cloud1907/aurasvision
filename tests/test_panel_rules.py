import pytest

from src.panel_rules import RuleRepository, RuleSet
from src.store import SqliteStore


def test_rules_survive_reload_and_reject_stale_writes(tmp_path):
    path = tmp_path / "rules.json"
    repo = RuleRepository(path)
    payload = RuleSet(revision=0, rules=[dict(
        id="smoke", camera_id="cam", kind="sigara",
        popup=True, sound=True, cooldown=60,
    )])
    result = repo.save(payload)
    assert result["revision"] == 1
    assert RuleRepository(path).load()["rules"][0]["kind"] == "sigara"
    with pytest.raises(ValueError, match="changed"):
        repo.save(payload)


def test_invalid_rule_is_rejected():
    with pytest.raises(ValueError):
        RuleSet(rules=[dict(id="x", camera_id="cam", kind="made-up")])
    with pytest.raises(ValueError):
        RuleSet(rules=[dict(id="x", camera_id="cam", kind="sigara", cooldown=-1)])


def test_broken_saved_rules_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text("{bad")
    with pytest.raises(ValueError):
        RuleRepository(path).load()


def test_alert_feed_starts_at_current_cursor_and_pages_only_new_alerts(tmp_path):
    store = SqliteStore(tmp_path / "events.db")
    try:
        store.add_alert("intrusion", "Bölge 1", "intrusion", "Alan ihlali", "cam-1")
        first = store.alert_feed(None)
        assert first == {"cursor": 1, "alerts": [], "has_more": False}

        store.add_alert("fire_warning", "Duman", "fire", "Yangın şüphesi", "cam-1")
        store.add_alert("plate", "34 ABC 34", "blacklist", "Plaka eşleşmesi", "cam-2")
        page = store.alert_feed(first["cursor"], limit=1)
        assert [row["id"] for row in page["alerts"]] == [2]
        assert page["cursor"] == 2
        assert page["has_more"] is True
        assert store.alert_feed(page["cursor"], limit=1)["alerts"][0]["id"] == 3
    finally:
        store.close()
