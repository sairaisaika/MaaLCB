"""Native entry hands the picker back before Runner's durable entry intent.

These are graph/reader checks, not a Maa controller replay. The real November16
trace reached Team1 while the old ledger still named Team2: no test may relabel
that entry or credit its STAR_GRACES successor to the old scope.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from maalimbus.team_vision import selected_saved_team
from maalimbus.vision import Text


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'assets/resource/base/pipeline/mirror.json'
NODES = json.loads(PIPELINE.read_text(encoding='utf-8'))
TEAM_INPUT_NODES = {'DungeonTeamConfigure', 'DungeonTeamVerified', 'DungeonTeamRow',
                    'DungeonTeamConfirm', 'LevelWarningConfigure', 'LevelWarningProceed'}


def reachable(nodes, entry):
    seen, todo = set(), [entry]
    while todo:
        name = todo.pop()
        if name in seen or name not in nodes:
            continue
        seen.add(name)
        todo.extend(nodes[name].get('next') or [])
        todo.extend(nodes[name].get('on_error') or [])
    return seen


@pytest.mark.parametrize('name,scene', [('MirrorTeamReady', 'DUNGEON_TEAM'),
                                       ('MirrorLevelWarningReady', 'LEVEL_WARNING')])
def test_handoff_is_an_exact_scene_read_without_input_or_next(name, scene):
    node = NODES[name]
    assert node['recognition'] == 'Custom'
    assert node['custom_recognition'] == 'limbus_scene'
    assert node['custom_recognition_param'] == {'scene': scene}
    assert node['action'] == 'DoNothing'
    assert node['next'] == []
    assert not node.get('custom_action') and not node.get('target')


@pytest.mark.parametrize('entry', ['MirrorHome', 'MirrorDrive', 'MirrorEnter', 'MirrorEntryConfirm'])
def test_normal_entry_can_reach_picker_handoff_but_never_team_or_warning_inputs(entry):
    found = reachable(NODES, entry)
    assert 'MirrorTeamReady' in found
    assert not found & TEAM_INPUT_NODES


def test_picker_handoff_precedes_the_unexpected_team_library_terminal():
    next_nodes = NODES['MirrorEnter']['next']
    assert next_nodes.index('MirrorTeamReady') < next_nodes.index('MirrorTeamEvidence')
    assert 'MirrorTeamReady' in NODES['MirrorEntryConfirm']['next']
    assert 'DungeonTeamConfigure' not in NODES['MirrorEntryConfirm']['next']


def test_the_separately_reserved_team_confirmation_returns_at_level_warning():
    assert NODES['DungeonTeamConfirm']['next'] == [
        'LimbusSafety', 'LimbusExpired', 'LimbusDefeat', 'MirrorLevelWarningReady']
    assert not reachable(NODES, 'DungeonTeamConfirm') & {'LevelWarningConfigure', 'LevelWarningProceed'}


@pytest.mark.parametrize('entry', ['MirrorHome', 'MirrorDrive', 'MirrorEnter', 'MirrorEntryConfirm',
                                  'DungeonTeamConfirm'])
def test_handoff_keeps_existing_expiry_defeat_resource_and_unknown_doors(entry):
    node = NODES[entry]
    assert node['next'][:3] == ['LimbusSafety', 'LimbusExpired', 'LimbusDefeat']
    assert node['on_error'] == ['LimbusUnknown']
    assert NODES['LimbusSafety']['action'] == 'Custom'
    assert NODES['LimbusSafety']['custom_action'] == 'limbus_terminal'


def test_reintroducing_a_configure_node_is_detected_as_a_bad_native_chain():
    broken = copy.deepcopy(NODES)
    row = broken['MirrorEntryConfirm']['next']
    row[row.index('MirrorTeamReady')] = 'DungeonTeamConfigure'
    assert reachable(broken, 'MirrorDrive') & TEAM_INPUT_NODES


def test_retained_picker_names_team_one_and_never_team_two():
    # Retained integration preflight: all files and bytes must exist to use this
    # observation. This is reader evidence, not permission to re-send Confirm.
    # This retained integration check must not make the module's independent
    # graph tests disappear when an old local capture is unavailable.
    path = ROOT / 'evidence' / 'runtime' / ('packaged-mirror-'+'20261116-132550') / 'frame-0014.json'
    png = path.with_suffix('.png')
    if not (path.is_file() and png.is_file()):
        pytest.skip('Retained November16 Team1 picker JSON/PNG unavailable; reader integration unverified')
    record = json.loads(path.read_text(encoding='utf-8'))
    assert hashlib.sha256(png.read_bytes()).hexdigest() == record['image_sha256']
    assert record['scene'] == 'DUNGEON_TEAM'
    records = [Text(row['text'], tuple(row['box']), row['score']) for row in record['ocr']]
    selected = selected_saved_team(records, record['size'])
    assert selected == 1
    assert selected != 2
