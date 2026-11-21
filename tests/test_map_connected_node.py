"""Actual post-shop node, independently measured parts and missing-part controls."""
from copy import deepcopy
import json
from pathlib import Path

import cv2
import pytest

from maalimbus import map_dispatch, map_node_geometry, runner

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / 'evidence/runtime/packaged-mirror-20261117-010749'
FLOOR4 = ROOT / 'evidence/runtime/packaged-mirror-20261120-001228/frame-0066.png'
# Per test: the tests further down build their own images and need no frame.
needs_captures = pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261117-010749')


def actual():
    image = cv2.imread(str(CAPTURES / 'frame-0092.png'))
    assert image is not None, 'actual failure frame must remain available'
    return image


def test_measured_cyan_shop_on_actual_narrow_map():
    if not FLOOR4.is_file():
        pytest.skip('local native Floor 4 capture not available')
    image=cv2.imread(str(FLOOR4))
    rows=map_node_geometry.connected_nodes(image,template=runner.node_badge_template())
    assert len(rows)==1
    assert rows[0]['party']==[709,298]
    assert 826<=rows[0]['point'][0]<=842 and 393<=rows[0]['point'][1]<=411
    assert rows[0]['saturated_share']>=.7


@needs_captures
@pytest.mark.parametrize('scale', [1, 2 / 3])
def test_actual_body_and_connected_node_measure_pitch_independently_of_click_box(scale):
    image = actual()
    if scale != 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    found = map_node_geometry.connected_red_node(image)
    assert found is not None
    assert abs(found['party'][0] - 687 * scale) < 5
    assert abs(found['party'][1] - 830 * scale) < 5
    assert abs(found['point'][0] - 1070 * scale) < 5
    assert abs(found['point'][1] - 830 * scale) < 5
    assert found['step'] > 1.9 * found['target'][2]
    assert found['warm_share'] >= .70


@needs_captures
@pytest.mark.parametrize('part,box', [
    ('left_lamp', (637, 788, 24, 24)),
    ('right_lamp', (707, 787, 27, 27)),
    ('clock', (658, 746, 50, 45)),
    ('flame', (666, 671, 38, 47)),
    ('path', (770, 820, 203, 23)),
    ('node', (972, 742, 200, 176)),
])
def test_missing_independent_part_does_not_authorize_the_connected_reader(part, box):
    image = actual()
    x, y, w, h = box
    # A bright grey replacement path is also insufficient; brightness alone
    # previously scored the cold backward edges as perfect connections.
    image[y:y+h, x:x+w] = 125 if part == 'path' else 0
    assert map_node_geometry.connected_red_node(image) is None


@needs_captures
def test_full_candidate_entry_uses_measured_pitch_and_preserves_actual_frame():
    path = CAPTURES / 'frame-0092.json'
    before = path.read_bytes()
    record = json.loads(before)
    _, boxes = runner.candidates_of(CAPTURES, record)
    assert len(boxes) == 1 and boxes[0][0] > 970
    assert record['map_step_reach']['source'] == 'measured_connected_segment'
    loop = runner.MirrorRunner(runner.FakeDevice(), directory=CAPTURES, settings={})
    loop.state.update(map_party=record['map_party'], map_step_reach=record['map_step_reach'])
    assert loop._map_click_allowed(record['map_connected_step']['point'])
    assert not loop._map_click_allowed([1500, 830])
    assert loop.device.clicks == [] and path.read_bytes() == before


@needs_captures
def test_absent_connected_red_node_keeps_general_reader_available():
    image = cv2.imread(str(CAPTURES / 'frame-0001.png'))
    found = map_node_geometry.train_body(image)
    assert found is not None and abs(found['party'][1] - 430) < 5
    assert map_node_geometry.connected_red_node(image) is None


@needs_captures
def test_runner_dispatch_keeps_the_measured_node_through_its_second_distance_filter(tmp_path, monkeypatch):
    import shutil
    for suffix in ('.json', '.png'):
        shutil.copyfile(CAPTURES / ('frame-0092' + suffix), tmp_path / ('frame-0092' + suffix))
    before = json.loads((tmp_path / 'frame-0092.json').read_text(encoding='utf8'))
    successor = json.loads((CAPTURES / 'frame-0006.json').read_text(encoding='utf8'))
    readings = iter([before, successor, successor])
    loop = runner.MirrorRunner(runner.FakeDevice(), directory=tmp_path,
                               settings=dict(interval=0, rounds=1))
    monkeypatch.setattr(loop, '_observe', lambda **kw: next(readings))
    monkeypatch.setattr(loop, '_normalise_view_once', lambda record: record)
    result = loop.step()
    assert len(loop.device.clicks) == 1
    x, y = loop.device.clicks[0]
    assert 1020 < x < 1120 and 780 < y < 870
    assert result['input_sent'] and result['stopped'] is None
    assert loop.artifacts['steps'][-1]['passed']
    assert loop.artifacts['steps'][-1]['page_after'] == 'NODE_PANEL'


def test_actual_internal_camera_half_zoom_uses_sprite_units_not_screen_units():
    path = ROOT / 'evidence/runtime/packaged-mirror-20261117-013306/frame-0004.png'
    image = cv2.imread(str(path))
    assert image is not None, 'actual normalization successor must be retained'
    found = map_node_geometry.connected_red_node(image)
    assert found is not None
    assert abs(found['party'][0] - 1055) < 5 and abs(found['party'][1] - 394) < 5
    assert abs(found['point'][0] - 1247) < 5 and abs(found['point'][1] - 395) < 5
    assert 185 <= found['step'] <= 195


def test_actual_camera_pan_does_not_turn_a_visible_body_into_header_furniture():
    path = ROOT / 'evidence/runtime/packaged-mirror-20261117-013306/frame-0024.png'
    image = cv2.imread(str(path))
    assert image is not None
    found = map_node_geometry.connected_red_node(image)
    assert found is not None
    assert abs(found['party'][1] - 254) < 6
    assert abs(found['point'][0] - 1247) < 5 and abs(found['point'][1] - 255) < 6


@pytest.mark.parametrize('unjudged,foreign', [(True, False), (False, True)])
def test_unjudged_or_foreign_map_intent_cannot_be_retired(unjudged, foreign):
    target = [100, 200, 190, 190]
    state = dict(map_pending=target, map_committed=target, unknown='preserve')
    if unjudged:
        state['map_unjudged'] = dict(target=target)
    before = deepcopy(state)
    assert not map_dispatch.retire_rejected_target(state, [2, 3, 4, 5] if foreign else target)
    assert state == before


def test_fresh_rejection_releases_only_its_outstanding_outcome_for_view_recovery():
    target = [100, 200, 190, 190]
    state = dict(map_pending=target, map_committed=target, map_pending_kind='lit_ring',
                 refused_targets={'retained-verdict'}, scope='same')
    assert map_dispatch.retire_rejected_target(state, target)
    assert state['refused_targets'] == {'retained-verdict'} and state['scope'] == 'same'
    assert map_dispatch.prepare_view_change(state) is not None


def test_bounded_gold_path_requires_a_line_clear_of_its_flanks():
    import numpy as np

    image = np.full((480, 640, 3), 35, dtype=np.uint8)
    party = [320, 220]
    gold = [510, 210, 20, 20]
    gray = [110, 210, 20, 20]
    cv2.line(image, party, (520, 220), (0, 55, 100), 4)
    cv2.line(image, party, (120, 220), (130, 130, 130), 4)
    assert map_node_geometry.gold_path_support(image, party, [gold, gray]) == {tuple(gold): 1.0}
    image[:] = (0, 55, 100)
    assert map_node_geometry.gold_path_support(image, party, [gold, gray]) == {}


def test_relative_refusal_survives_pan_but_not_a_different_floor_or_scale(tmp_path):
    record = dict(map_board=(3, 'Dizzying Waves'), map_party=[1056, 486],
                  map_lattice={'pitch': [174, 152]}, map_party_source='locomotive', map_seen_node=True)
    loop = runner.MirrorRunner(runner.FakeDevice(), directory=tmp_path, settings={})
    target = [787, 239, 190, 190]
    relative = map_dispatch.relative_destination(record, target)
    loop.state.update(map_pending=target, map_pending_relative=relative, map_party=record['map_party'])
    assert loop._resolve_map_click('MAP') == 'rejected'
    assert map_dispatch.prepare_view_change(loop.state) is not None
    assert loop.state['map_refused_relative'] == [relative]
    moved = dict(record, map_party=[1049, 607])
    same = map_dispatch.relative_destination(moved, [780, 360, 190, 190])
    other = map_dispatch.relative_destination(moved, [1145, 521, 190, 190])
    assert map_dispatch.same_relative_destination(relative, same)
    assert not map_dispatch.same_relative_destination(relative, other)
    for changed in (dict(moved, map_board=(4, 'Other Floor')),
                    dict(moved, map_lattice={'pitch': [76, 65]}),
                    dict(moved, map_party_from_cache=True)):
        assert not map_dispatch.same_relative_destination(relative, map_dispatch.relative_destination(
            changed, [780, 360, 190, 190]))
    loop.state['map_unjudged'] = dict(target=target, expect=['NODE_PANEL'])
    assert loop._resolve_map_click('NODE_PANEL') == 'accepted'
    assert 'map_refused_relative' not in loop.state
