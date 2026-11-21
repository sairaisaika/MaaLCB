"""D149: a battle transition is counted by its own clock, not by the page wait budget.

Measured 2026-10-24 (`packaged-mirror-20261024-172437`): a healthy fight spent 41
transition waits, `WAIT_LIMIT = 40` ended the run at 85 s, and the battle had not finished.
"""
import inspect
from types import SimpleNamespace

import pytest
from maalimbus import runner


@pytest.mark.parametrize(('wait', 'expected'), [
    ({'page': 'BATTLE_HUD', 'battle': True}, 0),
    ({'page': 'LOADING'}, 0),
    ({'page': 'UNKNOWN', 'startup': True}, 0),
    ({'page': 'UNKNOWN'}, 1),
])
def test_only_an_ordinary_page_wait_counts_towards_the_page_budget(wait, expected):
    loop = SimpleNamespace(
        settings=runner.settings(), state={'step': 0}, deadline=None, journal=None,
        _retire_foreign_pending=lambda: None, _start_stall_watch=lambda: None,
        note=lambda *args, **kwargs: None, _pause_between_steps=lambda interval: 0,
        step=lambda: {'waiting': True, 'done': True, **wait},
    )
    loop.summary = lambda: loop._waited
    assert runner.MirrorRunner._walk(loop, steps=1) == expected


def test_the_transition_result_carries_whether_it_was_a_battle():
    source = inspect.getsource(runner.MirrorRunner.step)
    assert 'battle=in_battle' in source


SAMPLE = ('mirror_loader', 'LOADING', 'frame-0001', 'a' * 64)


@pytest.mark.parametrize(('updates', 'expected'), [
    # 66ceed4 moved the role to waits whose owner declares a sample; a wait that names
    # no owner no longer marks its capture as releasable.
    ({'diagnostic_sample': SAMPLE}, 'owner_diagnostic_poll'),
    ({}, None),
    ({'diagnostic_sample': SAMPLE, 'input_sent': True}, None),
    ({'input_sent': True}, None),
    ({'stopped': 'uncertain'}, None),
    ({'waiting': False}, None),
    ({'done': True}, None),
])
def test_runner_declares_only_nonterminal_input_free_waits(updates, expected):
    rows = []
    journal = SimpleNamespace(record=lambda event, **fields: rows.append((event, fields)))
    results = iter(({'page': 'SHOP', 'waiting': True, **updates}, {'done': True}))
    loop = SimpleNamespace(
        settings=runner.settings(), state={'step': 0}, deadline=None, journal=journal,
        _retire_foreign_pending=lambda: None, _start_stall_watch=lambda: None,
        note=lambda *args, **kwargs: None, _pause_between_steps=lambda interval: 0,
        step=lambda: next(results), summary=lambda: None,
    )
    runner.MirrorRunner._walk(loop, steps=1)
    assert rows[0][0] == 'step_finished'
    assert rows[0][1]['capture_role'] == expected


def test_a_page_wait_still_ends_after_the_limit():
    assert runner.wait_decision(runner.WAIT_LIMIT)['stop'] is False
    assert runner.wait_decision(runner.WAIT_LIMIT + 1) == {
        'note': True, 'stop': True, 'reason': 'the_loop_waited_without_a_new_page'}


def test_the_transition_clock_still_bounds_a_battle():
    assert 0 < runner.settings().transition_seconds <= 120
