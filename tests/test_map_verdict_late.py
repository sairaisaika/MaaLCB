"""A map click is judged by the page the next read names, not by the one it aimed at.

`evidence/runtime/packaged-mirror-20261023-233928`: the marked node at (1028,480) was
clicked, the settle window still read MAP, the loop recorded
``the_page_stayed_on_the_map_after_the_click`` -- and the very next read named
NODE_PANEL.  The panel had opened one read late, and the verdict was already spent on
a refusal that fed ``map_refused_streak``; at a streak of one the window takes the
progress-panel escape hatch and leaves the exploration (the 90 s cycle of
`packaged-mirror-20261023-231231`).  These tests pin both directions: a click that
comes back lands as accepted-late, and a click that really did nothing is promoted to
a refusal one read later instead of being believed immediately.
"""
import json
import pathlib

import pytest

import maalimbus.runner as runner
from maalimbus.runner import MirrorRunner


class _Journal:
    def __init__(self, directory):
        self.path = directory / 'events.jsonl'

    def record(self, event, **fields):
        row = {'event': event}
        row.update(fields)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row) + '\n')


def _events(directory, name):
    rows = []
    for line in (directory / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get('event') == name:
                rows.append(row)
    return rows


def _loop(tmp_path):
    device = runner.FakeDevice()
    return MirrorRunner(device, settings={'rounds': 1, 'interval': 0}, directory=tmp_path,
                        journal=_Journal(tmp_path))


def test_a_click_settled_by_a_later_page_is_not_a_refusal(tmp_path):
    loop = _loop(tmp_path)
    loop.state['map_pending'] = [1002, 447, 40, 40]
    loop.state['map_candidate_kinds'] = {runner.box_key([1002, 447, 40, 40]): 'lit_icon'}
    loop.state['map_unjudged'] = {'target': [1002, 447, 40, 40], 'kind': 'lit_icon',
                                  'frame': 'frame-0006'}
    verdict = loop._resolve_map_click('NODE_PANEL')
    assert verdict == 'accepted'
    rows = _events(tmp_path, 'map_click_result')
    assert [row['outcome'] for row in rows] == ['accepted']
    assert rows[0]['reason'] == 'the_click_was_taken_after_the_verdict'
    assert rows[0]['page'] == 'NODE_PANEL'
    assert rows[0]['kind'] == 'lit_icon'
    assert loop.state['map_unjudged'] is None
    assert loop.state.get('map_refused_streak', 0) == 0
    assert not loop.state.get('map_refused_since_progress')


def test_a_click_that_really_did_nothing_is_promoted_one_read_later(tmp_path):
    loop = _loop(tmp_path)
    loop.state['map_unjudged'] = {'target': [545, 239, 190, 190], 'kind': 'gold_badge_node',
                                  'frame': 'frame-0006'}
    verdict = loop._resolve_map_click('MAP')
    assert verdict == 'rejected'
    rows = _events(tmp_path, 'map_click_result')
    assert rows[0]['outcome'] == 'rejected'
    assert rows[0]['reason'] == 'the_click_was_not_taken_and_the_page_stayed'
    assert loop.state['map_refused_streak'] == 1
    assert loop.state.get('map_refused_since_progress') is True
    # The un-resumed-exploration label is still only spent at the third refusal.
    assert _events(tmp_path, 'map_clicks_refused_while_the_exploration_may_be_unresumed') == []


def test_nothing_pending_means_nothing_is_written(tmp_path):
    loop = _loop(tmp_path)
    assert loop._resolve_map_click('MAP') is None
    assert not (tmp_path / 'events.jsonl').exists()


def test_an_unreadable_page_does_not_promote_the_click(tmp_path):
    """An allowed unknown wait is neither success nor evidence of failure."""
    loop = _loop(tmp_path)
    pending = {'target': [1002, 447, 40, 40], 'kind': 'lit_icon', 'frame': None}
    loop.state['map_unjudged'] = pending
    assert loop._resolve_map_click('UNKNOWN') == 'unjudged'
    assert loop.state['map_unjudged'] is pending
    assert _events(tmp_path, 'map_click_result') == []
    assert not loop.state.get('map_refused_streak')


def test_two_unknown_reads_then_real_panel_settle_one_original_click(tmp_path):
    loop = _loop(tmp_path)
    pending = {'target': [1002, 447, 40, 40], 'kind': 'lit_icon',
               'frame': 'original-input', 'expect': ['NODE_PANEL', 'UNKNOWN']}
    loop.state['map_unjudged'] = pending
    loop.state.update(map_pending=pending['target'],map_committed=pending['target'])
    for index in range(2):
        assert loop._resolve_map_click('UNKNOWN', observation={'frame':str(index)}) == 'unjudged'
        assert loop.state['map_unjudged'] is pending
    assert loop._resolve_map_click('NODE_PANEL', observation={
        'frame':'independent-panel', 'image_sha256':'native-pixels'}) == 'accepted'
    assert loop.state['map_unjudged'] is None
    assert not loop.state.get('map_pending') and not loop.state.get('map_committed')
    assert loop.device.clicks == []
    rows = _events(tmp_path, 'map_click_result')
    assert len(rows) == 1 and rows[0]['after_frame'] == 'independent-panel'
    assert rows[0]['frame'] == 'original-input'


def test_legacy_raw_pending_uses_the_same_verdict_owner(tmp_path):
    loop=_loop(tmp_path)
    target=[1002,447,40,40]
    loop.state.update(map_pending=target,map_committed=target,map_click_frame='old-input')
    assert loop._resolve_map_click('UNKNOWN')=='unjudged'
    assert loop.state['map_pending']==target and loop.state['map_committed']==target
    assert loop._resolve_map_click('NODE_PANEL')=='accepted'
    assert not loop.state.get('map_pending') and not loop.state.get('map_committed')
    assert len(_events(tmp_path,'map_click_result'))==1


def test_the_streak_is_not_spent_when_the_verdict_is_unjudged(tmp_path):
    loop = _loop(tmp_path)
    loop.state['map_pending'] = [545, 239, 190, 190]
    loop._map_verdict(target=[545, 239, 190, 190], page='MAP', outcome='unjudged',
                      kind='gold_badge_node',
                      reason='the_page_stayed_on_the_map_after_the_click')
    assert loop.state.get('map_refused_streak', 0) == 0
    assert not loop.state.get('map_refused_since_progress')


def test_the_click_table_counts_an_unjudged_verdict_apart():
    from maalimbus import run_metrics
    assert 'unjudged' in run_metrics.CLICK_VERDICTS
    assert run_metrics.CLICK_VERDICTS != ('accepted', 'rejected')


def test_the_party_in_place_verdict_is_provisional_too(tmp_path):
    """A panel opening does not move the party, so this verdict cannot be final either.

    `packaged-mirror-20261023-235553`: the marked node at (1036,457) was clicked, the
    party stayed put, the loop recorded `the_map_stayed_with_the_party_in_place` -- and
    the next read named NODE_PANEL.
    """
    loop = _loop(tmp_path)
    loop.state['map_pending'] = [1036, 457, 40, 40]
    loop.state['map_candidate_kinds'] = {runner.box_key([1036, 457, 40, 40]): 'lit_icon'}
    loop.state['map_unjudged'] = {'target': [1036, 457, 40, 40], 'kind': 'lit_icon', 'frame': None}
    assert loop._resolve_map_click('NODE_PANEL') == 'accepted'
    rows = _events(tmp_path, 'map_click_result')
    assert rows[0]['outcome'] == 'accepted' and rows[0]['page'] == 'NODE_PANEL'


def test_the_map_keeps_its_verdict_for_the_next_read(tmp_path):
    """D184: one settle read proves the map kept its name; the verdict waits for the
    next step's read (D76), so the in-step second read bought nothing."""
    source = (pathlib.Path(runner.__file__).read_text(encoding='utf-8'))
    assert 'if map_successor_reads>=1:break' in source
    assert 'if map_successor_reads>=2:break' not in source
