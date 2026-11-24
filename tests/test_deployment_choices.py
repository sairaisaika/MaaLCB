import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'agent'))
from recognition import TeamAction, Journal
from maalimbus.deployment import DeploymentDraft
from maalimbus.policies import Team
from maalimbus.storage import ProfileStore, SINNERS


def test_draft_rejects_partial_duplicate_unknown_and_invalid_position():
    draft = DeploymentDraft()
    with pytest.raises(ValueError): draft.finish()
    for invalid in (True, 0, 13, '1'):
        with pytest.raises(ValueError): draft.choose(invalid, 'Faust')
    with pytest.raises(ValueError): draft.choose(1, 'Unknown')
    draft.choose(1, 'Faust')
    with pytest.raises(ValueError): draft.choose(1, 'Yi Sang')
    for position in range(2,13): draft.choose(position, 'Faust')
    with pytest.raises(ValueError): draft.finish()


@pytest.mark.parametrize('failure', ['partial','duplicate','disk_error',None])
def test_agent_commits_once_and_preserves_other_saved_team_preferences(tmp_path,monkeypatch,failure):
    monkeypatch.setenv('MAALIMBUS_DATA_PATH', str(tmp_path))
    original = Team(2, frozenset({'Burn'}), 'Renamed team', frozenset({'Gift'}),
                    frozenset({'Blocked'}), SINNERS, (('A Certain World', 20),))
    other = Team(7, frozenset({'Bleed'}), deployment=SINNERS)
    store = ProfileStore(tmp_path/'user-team-profiles.json');store.save([original, other])
    before = store.path.read_bytes()
    rec = SimpleNamespace(team=original,deployment_draft=None,journal=Journal(tmp_path/'journal'))
    action = TeamAction(rec)
    def run(params): return action.run(None,SimpleNamespace(custom_action_param=json.dumps(params)))
    assert run({'mode':'deployment','preset':'custom'})
    order = tuple(reversed(SINNERS))
    count = 11 if failure=='partial' else 12
    for position in range(1,count+1):
        assert run({'mode':'deployment_slot','position':position,
                    'sinner':order[0] if failure=='duplicate' else order[position-1]})
        assert store.path.read_bytes()==before
    if failure=='disk_error':
        def reject(*args): raise OSError('Cannot replace configuration')
        monkeypatch.setattr('maalimbus.storage.os.replace', reject)
    if failure:
        assert run({'mode':'deployment_commit'}) is False
        assert store.path.read_bytes()==before and rec.team==original
        events=[json.loads(line) for line in (tmp_path/'journal/events.jsonl').read_text().splitlines()]
        assert events[-1]['event']=='callback_failed' and not events[-1]['verified_clear']
        assert rec.callback_failure['error_type']==('OSError' if failure=='disk_error' else 'ValueError')
        assert run({'mode':'deployment','preset':'natural'}) is False
        assert store.path.read_bytes()==before
    else:
        assert run({'mode':'deployment_commit'})
        saved = ProfileStore(store.path).load()
        assert saved[0].deployment==order and saved[1]==other
        assert saved[0].pack_weights==original.pack_weights and saved[0].keywords==original.keywords
        assert saved[0].name==original.name and saved[0].allow==original.allow and saved[0].block==original.block
        assert rec.deployment_draft is None


def test_the_preset_options_are_gone_and_the_order_lives_with_each_team():
    # No task has offered deployment_preset and its twelve position options since the
    # native entries were consolidated; they were removed on 2026-11-23. A team's
    # order is one choice in the team's own settings (it was twelve dropdowns).
    pi=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert 'deployment_preset' not in pi['option']
    for i in range(1,13):
        assert f'deployment_position_{i}' not in pi['option']
        assert f'global_team_1_order_{i}' not in pi['option']
        assert nodes[f'DeploymentOrder{i}']['max_hit']==1
    assert [case['name'] for case in pi['option']['global_team_1_order']['cases']]==['keep','game','starters','custom']
    assert nodes['DeploymentPreset']['next']==['DeploymentOrder1']
    assert nodes['DeploymentOrderCommit']['next'][0]=='LimbusSafety'
