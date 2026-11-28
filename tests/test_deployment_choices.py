import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
from maalimbus.deployment import DeploymentDraft


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


def test_the_preset_options_are_gone_and_the_order_lives_with_each_team():
    # No task has offered deployment_preset and its twelve position options since the
    # native entries were consolidated; they were removed on 2026-11-23. A team's
    # order is one choice in the team's own settings (it was twelve dropdowns). The
    # pipeline nodes those options wrote into (DeploymentPreset, DeploymentOrder1..12,
    # DeploymentOrderCommit) followed on 2026-11-27.
    pi=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert 'deployment_preset' not in pi['option']
    for i in range(1,13):
        assert f'deployment_position_{i}' not in pi['option']
        assert f'global_team_1_order_{i}' not in pi['option']
    assert [case['name'] for case in pi['option']['global_team_1_order']['cases']]==['keep','game','custom']
    assert not [name for name in nodes if name.startswith('Deployment')]
