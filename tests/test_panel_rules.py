import pytest
from src.panel_rules import RuleRepository, RuleSet


def test_rules_survive_reload_and_reject_stale_writes(tmp_path):
    path=tmp_path/'rules.json'
    repo=RuleRepository(path)
    payload=RuleSet(revision=0, rules=[dict(id='smoke',camera_id='cam',kind='sigara',popup=True,sound=True,cooldown=60)])
    result=repo.save(payload)
    assert result['revision']==1
    assert RuleRepository(path).load()['rules'][0]['kind']=='sigara'
    with pytest.raises(ValueError,match='changed'): repo.save(payload)


def test_invalid_rule_is_rejected():
    with pytest.raises(ValueError): RuleSet(rules=[dict(id='x',camera_id='cam',kind='made-up')])
    with pytest.raises(ValueError): RuleSet(rules=[dict(id='x',camera_id='cam',kind='sigara',cooldown=-1)])


def test_broken_saved_rules_are_not_silently_overwritten(tmp_path):
    path=tmp_path/'rules.json';path.write_text('{bad')
    with pytest.raises(ValueError): RuleRepository(path).load()
