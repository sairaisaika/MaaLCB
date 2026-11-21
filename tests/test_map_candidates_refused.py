"""A refusal names the reading that failed, and a known party is not a missing one.

The D260 guard used a retained frame as its negative sample; once the party reader was
fixed (D261/D262) that sample started reading a party, which made the guard unreachable.
These cases build the record instead, so the contract is pinned without depending on a
frame that keeps improving.
"""
import numpy as np
import pytest

from maalimbus import runner


BOXES = [{'box': (400, 300, 190, 190), 'kind': 'gold_badge_node'},
         {'box': (700, 300, 190, 190), 'kind': 'path_node'}]


def _record():
    return {'scene': 'MAP', 'frame': 'test', 'ocr': []}


def _stub(monkeypatch, party, *, boxes=BOXES):
    monkeypatch.setattr(runner, 'latest_frame', lambda directory: (np.zeros((1080, 1920, 3), np.uint8), 'test'))
    monkeypatch.setattr(runner, 'map_clicks', lambda image, *, template=None, player=None:
                        [dict(item) for item in boxes])
    monkeypatch.setattr(runner.map_vision, 'party_tracked',
                        lambda image, previous=None: (party, 'primary'))
    monkeypatch.setattr(runner, 'party_point', lambda image: party)
    monkeypatch.setattr(runner, 'node_badge_template', lambda: None)
    monkeypatch.setattr(runner, 'header_chrome', lambda record: None)


def test_an_unread_party_refuses_and_says_which_reading_failed(monkeypatch):
    # An ordinary path with no independently marked destination cannot supply a
    # guessed anchor. Gold badges have a separate explicit fallback below.
    unmarked = [dict(item, kind='path_node') for item in BOXES]
    _stub(monkeypatch, None, boxes=unmarked)
    record = _record()
    name, boxes = runner.candidates_of('/', record)
    assert boxes == []
    assert record['map_candidates_refused'] == {'party': None, 'read': 2, 'guessed': 0}


def test_a_gold_badge_is_an_explicit_guess_without_claiming_a_party(monkeypatch):
    _stub(monkeypatch, None)
    record = _record()
    _name, boxes = runner.candidates_of('/', record)
    assert boxes == [[400, 300, 190, 190]]
    assert record['map_party'] is None
    assert record['map_party_source'] == 'none'
    assert record['map_candidates_refused'] == {'party': None, 'read': 2, 'guessed': 1}
    assert record['map_candidate_kinds'] == {runner.box_key(boxes[0]): 'guessed_badge'}
    # This pure reader offers one explicitly marked candidate. It has no input
    # loop or retry authority; the runner must still judge each attempted click.
    progress = runner.MapProgress()
    progress.note_floor(1)
    progress.note_click(boxes[0])
    for _ in range(3):
        same_page = _record()
        _name, offered = runner.candidates_of('/', same_page)
        assert progress.remaining(offered) == []
        progress.note_floor(None)  # A dropped header cannot make the guess new.


def test_a_known_party_is_used_instead_of_refusing(monkeypatch):
    _stub(monkeypatch, None)
    record = _record()
    name, boxes = runner.candidates_of('/', record, fallback_party=(420, 380))
    assert record['map_party_from_cache'] is True
    assert record['map_party'] == [420, 380]
    assert 'map_candidates_refused' not in record
    assert boxes and all(len(box) == 4 for box in boxes)


def test_a_readable_party_is_not_marked_as_cached(monkeypatch):
    _stub(monkeypatch, (420, 380))
    record = _record()
    name, boxes = runner.candidates_of('/', record)
    assert 'map_party_from_cache' not in record
    assert 'map_candidates_refused' not in record


@pytest.mark.parametrize('bound', [False, True])
def test_box_mode_only_removes_neighbors_when_the_arrow_names_one(monkeypatch, bound):
    left, right = (665, 405, 190, 190), (1045, 405, 190, 190)
    _stub(monkeypatch, (950, 500), boxes=[dict(box=box,kind='gold_badge_node') for box in (left,right)])
    monkeypatch.setattr(runner.map_vision, 'party_tracked',
                        lambda image, previous=None: ((950, 500), 'locomotive'))
    direction = dict(direction=(-1.0, 0.0))
    monkeypatch.setattr(runner.map_vision, 'direction_arrow', lambda *a, **kw: direction)
    monkeypatch.setattr(runner.map_vision, 'arrow_target', lambda *a, **kw:
                        dict(guess=(760,500), gap=0 if bound else 129,
                             arrow=direction, target=list(left) if bound else None))
    record = _record()
    _, boxes = runner.candidates_of('/', record, mode='box')
    assert list(left) in boxes
    assert (list(right) in boxes) is not bound


def test_the_floor_cache_is_bounded_and_cleared_by_a_new_floor(monkeypatch):
    """The step hands the reader the last point of THIS floor, never one from another."""
    from maalimbus import runner as r
    import inspect
    body = inspect.getsource(r.MirrorRunner.step)
    assert 'MAP_PARTY_CACHE_SECONDS' in body
    assert "self.state.get('map_party_floor') == floor" in body
    assert 0 < r.MAP_PARTY_CACHE_SECONDS <= 120
