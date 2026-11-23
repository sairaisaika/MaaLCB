"""Each finished task leaves one row of numbers that outlives its frames.

The picture `run_report` draws only reaches back as far as the stored journals. The
history file is written once per task and is what a trend across days is read from; it
is also what can be shared when asking for help, so a row names no account, device or
local path.
"""
import json
import sys
from pathlib import Path

from maalimbus import run_history


def stamp(second):
    return '2026-11-23T10:%02d:%02d+00:00' % divmod(second, 60)


def journal(scope='a84a716214c04968', *, floor_seconds=700):
    """A task that enters floor 2 after 100 s, fights, and stops in the shop."""
    rows = [dict(event='mirror_loop_start', utc=stamp(0), run_scope=scope,
                 directory='Z:/someone/app/evidence/runtime/pi-1'),
            dict(event='page_checkpoint', utc=stamp(0), progress=dict(cleared_floors=[])),
            dict(event='step_finished', utc=stamp(10), page='MAP'),
            dict(event='window_intent', utc=stamp(20)),
            dict(event='loop_waited', utc=stamp(40)),
            dict(event='step_finished', utc=stamp(100), page='BATTLE_HUD'),
            dict(event='page_checkpoint', utc=stamp(100), progress=dict(cleared_floors=[1])),
            dict(event='battle_turn_advanced', utc=stamp(200)),
            dict(event='capture_profile_full_reread', utc=stamp(300)),
            dict(event='party_plan_refused', utc=stamp(400)),
            dict(event='step_finished', utc=stamp(100 + floor_seconds), page='SHOP'),
            dict(event='mirror_loop_stopped', utc=stamp(100 + floor_seconds), reason='shop_stopped', passed=False)]
    # A real journal has a row every few seconds; a silence of two minutes is a person.
    beats = [dict(event='loop_heartbeat', utc=stamp(second)) for second in range(150, 100 + floor_seconds, 50)
             if second not in (200, 300, 400)]
    return sorted(rows + beats, key=lambda row: row['utc'])


RESULT = dict(passed=False, reason='shop_stopped', clicks_sent=1)


def test_a_row_holds_times_counts_and_the_stop_and_nothing_that_names_the_machine():
    row = run_history.summary('pi-20261123-100000', journal(), task='mirror_loop', result=RESULT,
                              storage=dict(moved=3, moved_bytes=30_000, after_bytes=1, archive_bytes=2, reached=True,
                                           over_line=False, seconds=1.5, archive='Z:/someone/archive'))
    assert row['run'] == 'pi-20261123-100000' and row['task'] == 'mirror_loop' and row['scope'] == 'a84a7162'
    assert row['program_seconds'] == 800.0 and row['floors'] == {1: 100.0, 2: 700.0}
    assert row['battle'] == {2: 700.0} and row['pages'] == {'MAP': 90.0, 'BATTLE_HUD': 700.0, 'SHOP': 0.0}
    assert row['passed'] is False and row['reason'] == 'shop_stopped'
    assert row['checkpoints'] == dict(waits=1, rereads=1, refusals=1, inputs=1, observations=0, steps=3,
                                      battle_turns=1, purchases=0, floors_over_target=[2])
    assert row['events']['step_finished'] == 3
    assert row['storage'] == dict(moved=3, moved_bytes=30_000, after_bytes=1, archive_bytes=2, reached=True,
                                  over_line=False, seconds=1.5)
    text = json.dumps(row)
    assert 'someone' not in text and 'Z:' not in text and 'a84a716214' not in text


def test_a_wait_for_a_person_is_not_program_time():
    rows = journal()
    rows.append(dict(event='main_task_stopped', utc='2026-11-23T11:30:00+00:00'))
    assert run_history.summary('pi-1', rows)['program_seconds'] == 800.0


def test_rows_are_appended_and_a_damaged_line_does_not_cost_the_rest(tmp_path):
    first = run_history.summary('pi-1', journal(), task='mirror_loop', result=RESULT)
    path = run_history.append(tmp_path, first)
    with path.open('a', encoding='utf-8') as handle:
        handle.write('{"version": 1, "run": "cut off\n')
        handle.write('{"version": 2, "run": "from a later format"}\n')
    run_history.append(tmp_path, run_history.summary('pi-2', journal(), task='rewards', result=dict(passed=True)))
    assert path.name == 'user-run-history.jsonl'
    assert [row['run'] for row in run_history.load(tmp_path)] == ['pi-1', 'pi-2']
    assert run_history.load(tmp_path / 'absent') == []


def test_a_floor_played_across_several_tasks_is_one_floor_of_one_game_run():
    rows = [run_history.summary('pi-1', journal(floor_seconds=500), task='mirror_loop', result=RESULT),
            run_history.summary('pi-2', journal(floor_seconds=400), task='mirror_loop', result=RESULT),
            run_history.summary('pi-3', journal('ffff0000', floor_seconds=400), task='mirror_loop',
                                result=dict(passed=True)),
            run_history.summary('pi-4', [dict(event='main_task_stopped', utc=stamp(0))], task='rewards',
                                result=dict(passed=True))]
    report = run_history.trend(rows)
    assert report['tasks'] == 4
    assert report['by_task'] == [dict(task='mirror_loop', count=3, passed=1), dict(task='rewards', count=1, passed=1)]
    slow, quick = report['game_runs']
    # 100 + 100 s on floor 1 and 500 + 400 s on floor 2: neither task alone was over the target.
    assert slow == dict(scope='a84a7162', floors={1: 3.3, 2: 15.0}, slowest_floor=2, slowest_minutes=15.0,
                        within_target=False)
    assert quick['within_target'] and report['slowest_floor_minutes'] == 15.0
    assert report['stops'] == [dict(reason='shop_stopped', count=2)]
    assert report['checkpoints']['waits'] == 3 and report['checkpoints']['steps'] == 9
    assert report['pages'][0]['page'] == 'BATTLE_HUD'
    assert any('game run a84a7162' in line for line in run_history.lines(report))
    assert run_history.trend([])['tasks'] == 0 and run_history.lines(run_history.trend([]))


def test_a_task_says_when_a_floor_ran_past_the_target():
    slow = run_history.summary('pi-1', journal(), task='mirror_loop', result=RESULT)
    assert '第 2 层' in run_history.notice(slow) and '12 分钟' in run_history.notice(slow)
    assert run_history.notice(run_history.summary('pi-1', journal(floor_seconds=300))) is None


def agent(monkeypatch, root):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
    import recognition
    monkeypatch.setattr(recognition, 'ROOT', root)
    monkeypatch.setattr(recognition, 'data_directory', lambda *a: root / 'config')
    return recognition


def test_a_finished_task_inside_the_installation_adds_its_row(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'app'
    recognition = agent(monkeypatch, root)
    run = root / 'evidence/runtime/pi-20261123-100000'
    run.mkdir(parents=True)
    (run / 'events.jsonl').write_text('\n'.join(json.dumps(row) for row in journal()) + '\nnot json\n', encoding='utf-8')
    (run / 'agent-result.json').write_text(json.dumps(RESULT), encoding='utf-8')
    monkeypatch.setattr(recognition, 'settle_evidence', lambda directory: dict(moved=1, moved_bytes=10, seconds=0.1))
    row = recognition.finish_task(run, 'mirror_loop')
    assert row['run'] == 'pi-20261123-100000' and row['storage']['moved'] == 1
    assert run_history.load(root / 'config') == [json.loads(json.dumps(row))]
    assert '第 2 层' in capsys.readouterr().out


def test_a_task_pointed_elsewhere_leaves_no_row_and_a_failure_costs_nothing(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'app'
    recognition = agent(monkeypatch, root)
    monkeypatch.setattr(recognition, 'settle_evidence', lambda directory: None)
    elsewhere = tmp_path / 'elsewhere/run'
    elsewhere.mkdir(parents=True)
    assert recognition.finish_task(elsewhere, 'stamina') is None
    assert not (root / 'config').exists() and capsys.readouterr().out == ''
    # No journal at all: reported, nothing raised, nothing written.
    run = root / 'evidence/runtime/pi-1'
    run.mkdir(parents=True)
    assert recognition.finish_task(run, 'stamina') is None
    assert '任务结果不受影响' in capsys.readouterr().out and not (root / 'config').exists()
