"""PI options must not replace another option's custom_action_param object."""
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def test_independent_option_nodes_and_complete_custom_parameters():
    interface=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    # These four options had no task since the native entries were consolidated and
    # were removed on 2026-11-23; pack preferences are set through the Mirror task.
    for option in ('team_slot','team_name','pack_name','pack_weight'):
        assert option not in interface['option']
    assert 'mirror_preferences' in next(t for t in interface['task'] if t['name']=='mirror_loop')['option']
    tasks={t['entry']:t for t in interface['task']}
    assert 'ThemePackStart' not in tasks  # preferences no longer appear as main tasks
    assert nodes['ThemePackDrag']['max_hit']==1
    assert nodes['ThemePackBoundary']['custom_action_param']['reason']=='theme_drag_recorded_map_verification_pending'


def test_deployment_requires_saved_order_or_explicit_preset_and_is_bounded():
    interface=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert 'deployment_preset' not in interface['option']
    assert all(t['entry']!='DeploymentStart' for t in interface['task'])
    assert nodes['DeploymentNext']['max_hit']==12
    assert nodes['DeploymentComplete']['custom_action']=='limbus_deployment_proof'
    assert nodes['DeploymentBoundary']['custom_action_param']['reason']=='deployment_order_observed_battle_not_started'
    assert 'DeploymentPreset' in nodes
