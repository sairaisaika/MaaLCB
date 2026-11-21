"""Guided bracket metadata and default box selection have separate contracts."""
import sys
import pathlib
import json

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src')]

import maalimbus.runner as runner  # noqa: E402

ORIGIN = (525, 425, 190, 190)  # party at (620, 520)
RIGHT = (715, 425, 190, 190)   # one real node pitch to the right
DOWN = (525, 615, 190, 190)    # one real node pitch below


def _record(scene='MAP'):
    return {'scene': scene}


def _wire(monkeypatch, boxes, bracket):
    monkeypatch.setattr(runner, 'latest_frame', lambda directory: (np.zeros((1080, 1920, 3), np.uint8), 'frame-0001.png'))
    monkeypatch.setattr(runner, 'map_clicks', lambda image, *, template=None, player=None:
                        [{'box': list(b), 'kind': 'lit_icon'} for b in boxes])
    monkeypatch.setattr(runner, 'header_chrome', lambda record: None)
    # Stub the image readers, retaining real lock/size/adjacency/box geometry.
    # The party stands at ORIGIN's exact centre; RIGHT and DOWN are one pitch away.
    monkeypatch.setattr(runner, 'party_point', lambda image: (620, 520))
    monkeypatch.setattr(runner.map_vision, 'party_tracked',
                        lambda image, previous=None: ((620, 520), 'primary'))
    monkeypatch.setattr(runner, 'order_candidates', lambda boxes, kinds: [list(b) for b in boxes])
    monkeypatch.setattr(runner.map_vision, 'selection_bracket', lambda image: bracket)


def test_a_bracketed_box_is_recorded_as_a_hard_node(monkeypatch):
    boxes = [ORIGIN, RIGHT, DOWN]
    _wire(monkeypatch, boxes, (735, 445, 140, 140))
    record = _record()
    _name, ordered = runner.candidates_of('/tmp/x', record, mode='guided')
    assert ordered == [list(RIGHT), list(DOWN)]
    assert record['map_hard_node'] == list(RIGHT)


def test_a_bracket_on_no_adjacent_box_is_ignored(monkeypatch):
    boxes = [ORIGIN, RIGHT]
    _wire(monkeypatch, boxes, (1400, 200, 60, 50))
    record = _record()
    _name, ordered = runner.candidates_of('/tmp/x', record, mode='guided')
    assert ordered == [list(RIGHT)]
    assert record['map_hard_node'] is None


def test_no_bracket_leaves_the_order_alone(monkeypatch):
    boxes = [ORIGIN, RIGHT, DOWN]
    _wire(monkeypatch, boxes, None)
    record = _record()
    _name, ordered = runner.candidates_of('/tmp/x', record, mode='guided')
    assert ordered == [list(RIGHT), list(DOWN)]
    assert record['map_hard_node'] is None


def test_the_record_stays_json_serialisable(monkeypatch):
    boxes = [ORIGIN, RIGHT]
    _wire(monkeypatch, boxes, (735, 445, 140, 140))
    record = _record()
    runner.candidates_of('/tmp/x', record, mode='guided')
    json.dumps(record['map_hard_node'])


def test_a_non_map_page_offers_nothing(monkeypatch):
    _wire(monkeypatch, [ORIGIN, RIGHT], (735, 445, 140, 140))
    assert runner.candidates_of('/tmp/x', _record('SHOP')) == (None, None)


def test_small_icons_expand_to_exact_node_geometry_in_guided_mode(monkeypatch):
    _wire(monkeypatch, [(600, 500, 40, 40), (790, 500, 40, 40)], (790, 495, 60, 50))
    record = _record()
    _name, ordered = runner.candidates_of('/tmp/x', record, mode='guided')
    assert ordered == [[714, 424, 192, 192]]
    assert record['map_hard_node'] == [714, 424, 192, 192]
    assert record['map_click_size']['expanded'] == 2


def test_default_box_mode_keeps_one_step_nodes_and_drops_own_and_far_tiles(monkeypatch):
    far = (1095, 425, 190, 190)
    _wire(monkeypatch, [ORIGIN, RIGHT, DOWN, far], None)
    record = _record()
    _name, ordered = runner.candidates_of('/tmp/x', record)
    assert record['map_box_path'] == {'party': True, 'side': 190, 'boxes': 4}
    assert ordered == [list(RIGHT), list(DOWN)]
    assert list(ORIGIN) not in ordered and list(far) not in ordered
