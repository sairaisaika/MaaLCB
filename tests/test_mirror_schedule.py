"""The Mirror task plays on the chosen days until the day's runs are booked, then ends.

This is what lets the app sit on a timer: "Start" can be pressed every hour and the
Mirror Dungeon is still played only when the day owes it. The schedule is the Mirror
task's own setting, so there is no second entry repeating the task's options.
"""
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus import mirror_schedule
from maalimbus.daily_ledger import DailyLedger

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def kst(day, hour):
    return datetime(2026, 11, day, hour, tzinfo=KST)   # 23 November 2026 is a Monday


def nodes(days='every_day', runs=2):
    data = {'MirrorSchedule': {'attach': {'days': days}}, 'MirrorRunsPerDay': {'attach': {'runs': runs}}}
    return data.__getitem__


def result(tmp_path, completed):
    run = tmp_path / 'pi-1'
    run.mkdir(exist_ok=True)
    (run / 'agent-result.json').write_text(json.dumps(dict(verified_runs=dict(completed=completed))), encoding='utf-8')
    return run


def test_without_a_schedule_the_task_is_not_gated(tmp_path):
    assert mirror_schedule.collect(nodes('off', 1)) == ('off', 1)
    assert mirror_schedule.gate(tmp_path, 'off', 1, kst(24, 12)) is None
    # A pipeline built before the option existed has no such node.
    assert mirror_schedule.collect({}.__getitem__) == ('off', 1) and mirror_schedule.collect(None) == ('off', 1)
    assert not list(tmp_path.iterdir())


def test_a_chosen_day_owes_its_runs_until_they_are_booked(tmp_path):
    days, runs = mirror_schedule.collect(nodes('mon_wed_fri', 2))
    monday = kst(23, 12)
    first = mirror_schedule.gate(tmp_path, days, runs, monday)
    assert first == dict(days='mon_wed_fri', runs_per_day=2, day='2026-11-23', wanted=2, done=0, left=2, reason=None)
    assert mirror_schedule.book_result(tmp_path, result(tmp_path, 1), monday) == 1
    assert mirror_schedule.gate(tmp_path, days, runs, monday)['left'] == 1
    mirror_schedule.book_result(tmp_path, result(tmp_path, 1), monday + timedelta(hours=2))
    done = mirror_schedule.gate(tmp_path, days, runs, monday + timedelta(hours=3))
    assert done['left'] == 0 and done['reason'] == 'mirror_schedule_done_today'
    assert DailyLedger(tmp_path / 'user-daily-ledger.json').data['proofs']['mirror'] == ['pi-1', 'pi-1']


def test_another_day_owes_nothing_and_the_server_day_turns_at_six(tmp_path):
    tuesday = mirror_schedule.gate(tmp_path, 'mon_wed_fri', 2, kst(24, 12))
    assert tuesday['left'] == 0 and tuesday['reason'] == 'mirror_not_scheduled_today'
    # 03:00 on Tuesday is still the server's Monday; 06:00 on Wednesday is a new chosen day.
    assert mirror_schedule.gate(tmp_path, 'mon_wed_fri', 2, kst(24, 3))['left'] == 2
    mirror_schedule.book_result(tmp_path, result(tmp_path, 2), kst(24, 3))
    assert mirror_schedule.gate(tmp_path, 'mon_wed_fri', 2, kst(24, 5))['left'] == 0
    assert mirror_schedule.gate(tmp_path, 'mon_wed_fri', 2, kst(25, 6))['left'] == 2


def test_a_stop_halfway_books_nothing(tmp_path):
    for completed in (0, None, '1'):
        assert mirror_schedule.book_result(tmp_path, result(tmp_path, completed), kst(23, 12)) == 0
    assert mirror_schedule.book_result(tmp_path, tmp_path / 'absent', kst(23, 12)) == 0
    assert mirror_schedule.gate(tmp_path, 'every_day', 1, kst(23, 12))['left'] == 1


def test_a_run_finished_by_the_rewards_task_is_a_run_of_today(tmp_path):
    run = tmp_path / 'pi-2'
    run.mkdir()
    (run / 'agent-result.json').write_text(json.dumps(dict(passed=True, reason=mirror_schedule.PAYOUT_REASON)),
                                           encoding='utf-8')
    assert mirror_schedule.book_result(tmp_path, run, kst(23, 12)) == 1
    assert mirror_schedule.gate(tmp_path, 'every_day', 1, kst(23, 12))['reason'] == 'mirror_schedule_done_today'
    # The same reason on a failed result, or another passed result, is not a run.
    for body in (dict(passed=False, reason=mirror_schedule.PAYOUT_REASON), dict(passed=True, reason='other')):
        (run / 'agent-result.json').write_text(json.dumps(body), encoding='utf-8')
        assert mirror_schedule.book_result(tmp_path, run, kst(23, 12)) == 0


def test_one_start_never_plays_more_than_the_day_still_owes():
    assert mirror_schedule.run_count(None, 2) == 2 and mirror_schedule.run_count(0, 2) == 2
    assert mirror_schedule.run_count(5, 2) == 2 and mirror_schedule.run_count(1, 3) == 1


@pytest.mark.parametrize('days, runs', [('someday', 1), ('every_day', 4), ('every_day', '2'), ('every_day', True)])
def test_an_unknown_choice_is_refused(days, runs):
    with pytest.raises(ValueError):
        mirror_schedule.collect(nodes(days, runs))


def test_the_interface_offers_exactly_the_choices_the_module_knows():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    option = pi['option']['mirror_schedule']
    offered = [case['pipeline_override']['MirrorSchedule']['attach']['days'] for case in option['cases']]
    assert offered == list(mirror_schedule.DAYS) and option['default_case'] == 'off'
    assert all(case.get('option') == ['mirror_runs_per_day'] for case in option['cases'] if case['name'] != 'off')
    runs = [case['pipeline_override']['MirrorRunsPerDay']['attach']['runs']
            for case in pi['option']['mirror_runs_per_day']['cases']]
    assert tuple(runs) == mirror_schedule.RUNS
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert mirror_schedule.collect(pipeline.__getitem__) == ('off', 1)


@pytest.fixture
def agent(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'agent'))
    import recognition
    import maalimbus.controller_lease as leases
    monkeypatch.setattr(leases, 'lease_path', lambda path: tmp_path / 'unit.lock')
    monkeypatch.setattr(recognition, 'data_directory', lambda *a: tmp_path / 'config')
    monkeypatch.setattr(recognition.InputPreflight, 'run', lambda *a: True)
    return recognition


def start(recognition, tmp_path, days):
    context = SimpleNamespace(tasker=SimpleNamespace(controller=SimpleNamespace(info={'type': 'win32'})),
                              get_node_data=nodes(days, 1))
    args = SimpleNamespace(custom_action_param=json.dumps(dict(task='mirror', directory=str(tmp_path / 'run'))),
                           node_name='MirrorTask')
    return recognition.MainTaskAction(SimpleNamespace(callback_failure=None, journal=None)).run(context, args)


def test_a_start_the_day_does_not_owe_ends_before_anything_looks_at_the_game(agent, tmp_path, monkeypatch):
    monkeypatch.setattr(agent.runner, 'observe', lambda *a, **k: pytest.fail('the game was observed'))
    monkeypatch.setattr(agent.MirrorLoopAction, 'run', lambda *a: pytest.fail('the loop was started'))
    now = datetime.now(timezone.utc)
    DailyLedger(tmp_path / 'config/user-daily-ledger.json').book('mirror', now, count=1)
    assert start(agent, tmp_path, 'every_day') is True
    saved = json.loads((tmp_path / 'run/agent-result.json').read_text(encoding='utf-8'))
    assert saved['reason'] == 'mirror_schedule_done_today' and saved['passed'] and not saved['input_sent']
    assert '今天的局数已经打完' in saved['user_message'] and saved['schedule']['left'] == 0
    events = [json.loads(line)['event'] for line in (tmp_path / 'run/events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events[-2:] == ['mirror_schedule', 'main_task_stopped']


def test_the_wiring_bounds_the_loop_and_books_what_it_delivered():
    source = (ROOT / 'agent/recognition.py').read_text(encoding='utf-8')
    body = source[source.index('class MainTaskAction'):]
    gate = body.index('mirror_schedule.gate(')
    assert gate < body.index("config/'user-run-ledger.json'") < body.index('mirror_schedule.run_count(')
    assert body.index('mirror_schedule.run_count(') < body.index('passed=MirrorLoopAction(') < body.index(
        'mirror_schedule.book_result(')
    # The rewards task books the run it finishes, after its own result is written.
    rewards = body[body.index("if task=='rewards':"):]
    assert rewards.index('write_loop_result(directory,result)') < rewards.index('mirror_schedule.book_result(')
