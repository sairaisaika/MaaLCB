"""Options of removed standalone tasks stay out of the interface, and so do their nodes."""
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def test_pack_preferences_are_set_through_the_mirror_task():
    interface=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    # These four options had no task since the native entries were consolidated and
    # were removed on 2026-11-23; pack preferences are set through the Mirror task.
    for option in ('team_slot','team_name','pack_name','pack_weight'):
        assert option not in interface['option']
    assert 'mirror_preferences' in next(t for t in interface['task'] if t['name']=='mirror_loop')['option']
    # The ThemePack* and TeamLibrary* pipeline tasks those options configured were removed
    # on 2026-11-27 with the rest of the pipeline-only Mirror layer.
    assert not [name for name in nodes if name.startswith(('ThemePack','TeamLibrary'))]


def test_every_task_enters_one_custom_action_and_no_chain_of_clicks():
    interface=json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    nodes=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert 'deployment_preset' not in interface['option']
    for task in interface['task']:
        node=nodes[task['entry']]
        assert node['custom_action']=='limbus_main_task' and not node.get('next')
