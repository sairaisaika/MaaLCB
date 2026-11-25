"""A wiped stage with its retries used up: accept the result and confirm it, by choice.

The third run of 2026-11-24 was wiped three times by the floor-5 boss; the program
retried twice and stopped on the defeat page. The user chose that it should end the
run and go on to the rewards. The accept row was already planned for a window started
with `--defeat-accept`, but nothing followed it: the row was pressed again on every
step and its Confirm never was. The boxes are the ones the page anchors read on
`window-20261007-044408/frame-0001`.
"""
import json
from pathlib import Path

import pytest

from maalimbus import runner
from maalimbus.mirror_task_options import collect
from maalimbus.window import ANY, CLICK, plan_step

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = {'defeat.retry_button': [946, 480, 144, 34], 'defeat.accept_button': [952, 625, 362, 20],
            'defeat.confirm_button': [930, 770, 126, 36]}


def plan(**defeat):
    return plan_step('BATTLE_DEFEAT', controls=CONTROLS, defeat=dict(dict(row_sent=False), **defeat))


def test_the_accept_row_is_followed_by_its_own_confirm():
    row = plan(spent=True, accept=True)
    assert row['action'] == CLICK and row['target'] == CONTROLS['defeat.accept_button']
    assert row['defeat_accept'] == 'row'
    confirm = plan(spent=True, accept=True, accept_sent=True)
    assert confirm['target'] == CONTROLS['defeat.confirm_button'] and confirm['expect'] == [ANY]
    # The same word as the row: accepting is one decision in two presses, told apart by a flag.
    assert confirm['reason'] == row['reason'] and confirm['defeat_accept'] == 'confirm'
    # Without the Confirm on the page it is refused by name, not guessed.
    blind = plan_step('BATTLE_DEFEAT', controls={'defeat.accept_button': CONTROLS['defeat.accept_button']},
                      defeat=dict(row_sent=False, spent=True, accept=True, accept_sent=True))
    assert blind['action'] != CLICK and blind['reason'] == 'defeat_confirm_not_anchored'


def test_nothing_is_accepted_while_retries_remain_or_when_the_user_chose_to_wait():
    assert plan()['target'] == CONTROLS['defeat.retry_button']
    assert plan(spent=False, accept=True)['target'] == CONTROLS['defeat.retry_button']
    waiting = plan(spent=True, accept=False)
    assert waiting['action'] != CLICK and waiting['reason'] == 'defeat_retries_exhausted'
    # A retry row already highlighted is still confirmed as a retry.
    retry = plan(row_sent=True, spent=True, accept=True)
    assert retry['target'] == CONTROLS['defeat.confirm_button']
    assert retry['reason'] == 'the_retry_is_confirmed_and_the_stage_starts_over'


def test_the_choice_reaches_the_runner_from_the_interface():
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_bytes())
    assert pipeline['MirrorDefeatAccept']['attach'] == dict(mode='accept')
    assert collect(pipeline.__getitem__)['defeat_accept'] is True
    waiting = dict(pipeline, MirrorDefeatAccept=dict(attach=dict(mode='wait')))
    assert collect(waiting.__getitem__)['defeat_accept'] is False
    older = {name: node for name, node in pipeline.items() if name != 'MirrorDefeatAccept'}
    assert 'defeat_accept' not in collect(older.__getitem__)
    with pytest.raises(ValueError):
        collect(dict(pipeline, MirrorDefeatAccept=dict(attach=dict(mode='never'))).__getitem__)
    assert runner.settings().defeat_accept is False            # a bare runner still waits
    assert runner.settings(dict(defeat_accept=True)).defeat_accept is True
    interface = json.loads((ROOT / 'assets/interface.json').read_bytes())
    option = interface['option']['mirror_defeat_accept']
    assert option['default_case'] == 'accept' and [case['name'] for case in option['cases']] == ['accept', 'wait']
    for case in option['cases']:
        assert case['pipeline_override'] == {'MirrorDefeatAccept': {'attach': {'mode': case['name']}}}
    mirror = next(task for task in interface['task'] if task['name'] == 'mirror_loop')
    assert mirror['option'].index('mirror_defeat_accept') + 1 == mirror['option'].index('mirror_reward_claim')
