"""After a task ends the program makes room by itself, by moving frames to the archive.

A live task only checks free disk space and reclaims nothing, so an installation that
was left running grew past the folder's warning line task after task: 3.4 GB on
2026-11-23 after two days of runs, and a start had to be unblocked by hand the day before.
`settle` runs once per task, after the ending is written.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus import capture_retention as retention, workspace
from maalimbus.storage import write_json
from test_capture_retention import run


def project(tmp_path, monkeypatch, *, over=0):
    """One run of 14 frames; the warning line sits `over` bytes below the folder's size."""
    root = tmp_path / 'project'
    folder = run(root, closed=True)
    line = workspace.size(root) - over
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', line)
    return root, folder, line


def archived(root, folder, name):
    return root.parent / 'project-evidence-archive' / folder.relative_to(root) / name


def test_frames_the_rule_allows_leave_for_the_archive_until_the_target_is_met(tmp_path, monkeypatch):
    root, folder, line = project(tmp_path, monkeypatch)
    records = {p: p.read_bytes() for p in folder.glob('*.json')}
    journal = (folder / 'events.jsonl').read_bytes()
    summary = retention.settle(root, folder, headroom=3_000)
    # 1: first frame, 3/4: the input's before and after, 7..14: the recent eight. Of the
    # three frames left (2, 5, 6) two are enough to reach the target, so the third stays.
    assert summary['moved'] == 2 and summary['moved_bytes'] == 20_000
    assert summary['reached'] and not summary['over_line'] and not summary['archive_notice']
    assert summary['after_bytes'] == workspace.size(root) <= line - 3_000
    for name in ('frame-0002.png', 'frame-0005.png'):
        assert not (folder / name).exists()
        assert archived(root, folder, name).read_bytes() == bytes([int(name[6:10])]) * 10_000
    assert all((folder / f'frame-{n:04}.png').exists() for n in (1, 3, 4, 6, 7, 14))
    assert all(p.read_bytes() == body for p, body in records.items())
    assert (folder / 'events.jsonl').read_bytes() == journal
    trail = [json.loads(x) for x in (folder / 'capture-retention.jsonl').read_text().splitlines()]
    assert [x['archived'] for x in trail if x['event'] == 'capture_reclaimed'] == [
        'evidence/runtime/current/frame-0002.png', 'evidence/runtime/current/frame-0005.png']
    assert summary['archive_bytes'] == 20_000


def test_a_target_out_of_reach_still_moves_what_it_can_and_says_so(tmp_path, monkeypatch):
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    summary = retention.settle(root, folder, headroom=10_000)
    assert summary['moved'] == 3 and not summary['reached'] and summary['over_line']
    assert not any((folder / f'frame-{n:04}.png').exists() for n in (2, 5, 6))
    assert (folder / 'frame-0007.png').exists()
    # A second pass has nothing more it may move and changes nothing.
    again = retention.settle(root, folder, headroom=10_000)
    assert again['moved'] == 0 and again['after_bytes'] == summary['after_bytes']


def test_a_folder_under_its_target_is_left_alone(tmp_path, monkeypatch):
    root, folder, line = project(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in folder.iterdir()}
    summary = retention.settle(root, folder, headroom=0)
    assert summary['moved'] == 0 and summary['reached']
    assert {p: p.read_bytes() for p in folder.iterdir()} == before
    assert not (root.parent / 'project-evidence-archive').exists()


def test_a_frame_something_still_points_at_stays_in_the_project(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    folder = run(root, closed=True)
    write_json(root / 'config/pending.json', dict(pending=dict(before=str(folder / 'frame-0005.json'))))
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root))
    summary = retention.settle(root, folder, headroom=50_000)
    assert summary['moved'] == 2 and not summary['reached']
    assert (folder / 'frame-0005.png').exists()
    assert not (folder / 'frame-0002.png').exists() and not (folder / 'frame-0006.png').exists()


def test_a_run_folder_outside_the_installation_gives_no_authority(tmp_path, monkeypatch):
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    elsewhere = tmp_path / 'elsewhere/run'
    elsewhere.mkdir(parents=True)
    monkeypatch.setattr(workspace, 'size', lambda path: pytest.fail('the folder was measured'))
    summary = retention.settle(root, elsewhere, headroom=10_000)
    assert summary['skipped'] == 'run_folder_outside_this_installation' and summary['moved'] == 0
    assert (folder / 'frame-0005.png').exists()


@pytest.mark.parametrize('headroom', [-1, 10**12, 1.5, '1'])
def test_a_headroom_that_is_not_a_size_below_the_line_is_refused(tmp_path, monkeypatch, headroom):
    root, folder, line = project(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='headroom'):
        retention.settle(root, folder, headroom=headroom)


def agent_module():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
    import recognition
    return recognition


def test_the_task_reports_what_was_moved_and_keeps_its_own_outcome(tmp_path, monkeypatch, capsys):
    recognition = agent_module()
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    monkeypatch.setattr(recognition, 'ROOT', root)
    monkeypatch.setattr(retention, 'SETTLE_HEADROOM', 10_000)
    summary = recognition.settle_evidence(folder)
    assert summary['moved'] == 3 and summary['seconds'] >= 0
    saved = json.loads((folder / 'storage-settle.json').read_text(encoding='utf-8'))
    assert saved['moved'] == 3 and saved['kind'] == 'capture_settle'
    said = capsys.readouterr().out
    assert '移出 3 张' in said and '提醒线' in said
    # A reclaim that fails is reported and returns nothing; it raises nothing.
    monkeypatch.setattr(retention, 'settle', lambda *a, **k: (_ for _ in ()).throw(ValueError('changed')))
    assert recognition.settle_evidence(folder) is None
    assert '任务结果不受影响' in capsys.readouterr().out


def test_a_task_run_outside_the_installation_writes_nothing_about_storage(tmp_path, monkeypatch, capsys):
    recognition = agent_module()
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    monkeypatch.setattr(recognition, 'ROOT', root)
    monkeypatch.setattr(retention, 'SETTLE_HEADROOM', 10_000)
    elsewhere = tmp_path / 'elsewhere/run'
    elsewhere.mkdir(parents=True)
    assert recognition.settle_evidence(elsewhere)['skipped']
    assert not list(elsewhere.iterdir()) and capsys.readouterr().out == ''


def test_every_main_task_settles_before_it_releases_the_controller():
    source = (Path(__file__).resolve().parents[1] / 'agent/recognition.py').read_text(encoding='utf-8')
    body = source[source.index('class MainTaskAction'):]
    following = body.find('\nclass ', 10)
    body = body if following < 0 else body[:following]
    # The action's own closing block: the last `finally` at method depth.
    closing = body[body.rindex('\n        finally:'):]
    assert closing.index('finish_task(directory,task)') < closing.index('lease.close()')
    finish = source[source.index('def finish_task('):source.index('def write_run_log(')]
    assert finish.index('settle_evidence(directory)') < finish.index('record_history(directory,task,storage)')


def test_the_moving_phase_is_bounded_and_the_next_task_finishes_what_was_left(tmp_path, monkeypatch):
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    stopped = retention.settle(root, folder, headroom=10_000, seconds=0)
    assert stopped['moved'] == 0 and stopped['left'] == 3 and stopped['moved_bytes'] == 0
    assert all((folder / f'frame-{n:04}.png').exists() for n in (2, 5, 6))
    trail = [json.loads(x) for x in (folder / 'capture-retention.jsonl').read_text().splitlines()]
    assert [x['event'] for x in trail] == ['capture_reclaim_intent'] * 3
    finished = retention.settle(root, folder, headroom=10_000)
    assert finished['moved'] == 3 and finished['left'] == 0
    assert not any((folder / f'frame-{n:04}.png').exists() for n in (2, 5, 6))
    with pytest.raises(ValueError, match='time bound'):
        retention.settle(root, folder, seconds=-1)


def test_references_are_read_once_per_interval_while_frames_move_not_once_per_frame(tmp_path, monkeypatch):
    # One full read rehashes every source, test, document and state file: about 0.4 s on a
    # real folder, so 545 frames took 217 s to move on 2026-11-23.
    root, folder, line = project(tmp_path, monkeypatch, over=50_000)
    reads = []
    real = retention._reference_keep
    monkeypatch.setattr(retention, '_reference_keep', lambda *a, **k: reads.append(1) or real(*a, **k))
    plan = retention.plan(root, folder, 0, budget=line - 10_000)
    planning = len(reads)
    assert len(plan['files']) == 3
    summary = retention.settle(root, folder, headroom=10_000)
    assert summary['moved'] == 3 and len(reads) - planning == planning + 1
    # The offline path keeps reading before every frame.
    other, other_folder, other_line = project(tmp_path / 'second', monkeypatch, over=50_000)
    del reads[:]
    retention._delete_rows(other, other_folder, retention.plan(other, other_folder, 0, budget=other_line - 10_000)['files'],
                           20_480, budget=workspace.size(other))
    assert len(reads) == planning + 3
