"""Older finished runs leave for the archive whole; the bound data folder still pins frames.

Live 2026-11-28: 7.1 GB of frames in 134 run folders, over a 3 GB warning line, and each
task's reclaim moved almost nothing ("still referenced, not moved"), because only a few
kinds of frame of a run that ended `passed` could move and nearly every task ends on a
stop. The data folder the install is bound to was never read for references either.
"""
import json
import os
import time

from maalimbus import capture_retention as retention, workspace
from maalimbus.storage import write_json
from test_capture_retention import run


def runs(root, count):
    folders = []
    for index in range(count):
        folder = run(root, 'pi-%02d' % index, closed=True)
        stamp = time.time() - 1000 + index
        os.utime(folder / 'events.jsonl', (stamp, stamp))
        folders.append(folder)
    return folders


def test_older_finished_runs_move_whole_and_the_newest_five_keep_their_structure(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    folders = runs(root, 7)
    current = run(root, 'pi-99')
    groups = retention.diagnostic_groups(root, current)
    moving = {png for members in groups for png, record, data in members}
    for folder in folders[:2]:
        assert {p for p in folder.glob('frame-*.png')} <= moving
    for folder in folders[2:]:
        # The five newest keep their first frame and their tail as before.
        assert folder / 'frame-0001.png' not in moving and folder / 'frame-0014.png' not in moving
    # The run in progress is never aged (its intermediate frames follow the old rules).
    assert not any(png.parent == current and data.get('_retention') for members in groups
                   for png, record, data in members)


def test_a_frame_the_bound_data_folder_names_stays(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    folders = runs(root, 7)
    data = tmp_path / 'private'
    data.mkdir()
    (root / 'config').mkdir()
    write_json(root / 'config/user-data-root.json', dict(version=1, directory=str(data)))
    pinned = folders[0] / 'frame-0005.json'
    write_json(data / 'user-shop-run.json', dict(proof=dict(path=str(pinned))))
    assert pinned in workspace.protected_evidence(root)
    groups = retention.diagnostic_groups(root, run(root, 'pi-99'))
    moving = {png for members in groups for png, record, data_ in members}
    assert folders[0] / 'frame-0004.png' in moving and folders[0] / 'frame-0005.png' not in moving
    # A binding that is not one is ignored, not trusted.
    write_json(root / 'config/user-data-root.json', dict(version=2, directory=str(data)))
    assert workspace.bound_data_directories(root) == []


def test_an_unfinished_old_run_is_not_aged(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    folders = runs(root, 6)
    open_run = run(root, 'pi-00-open')
    stamp = time.time() - 5000
    os.utime(open_run / 'events.jsonl', (stamp, stamp))
    groups = retention.diagnostic_groups(root, run(root, 'pi-99'))
    moving = {png for members in groups for png, record, data in members}
    assert not any(png.parent == open_run and data.get('_retention') for members in groups
                   for png, record, data in members)
    assert folders[0] / 'frame-0001.png' in moving


def test_a_run_killed_long_ago_ages_like_a_finished_one(tmp_path, monkeypatch):
    # 64 of 141 live folders had no closing event (the app quit, a Stop, a crash).
    root = tmp_path / 'project'
    folders = runs(root, 6)
    killed = run(root, 'pi-00-killed')
    stamp = time.time() - retention.STALE_RUN_SECONDS - 60
    os.utime(killed / 'events.jsonl', (stamp, stamp))
    groups = retention.diagnostic_groups(root, run(root, 'pi-99'))
    assert any(png.parent == killed and data.get('_retention') for members in groups
               for png, record, data in members)


def test_a_tidy_with_nothing_new_skips_the_full_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, '_SETTLE_STATE', {})
    root = tmp_path / 'project'
    folders = runs(root, 7)
    pinned = folders[0] / 'frame-0005.json'
    (root / 'config').mkdir()
    data = tmp_path / 'private'
    data.mkdir()
    write_json(root / 'config/user-data-root.json', dict(version=1, directory=str(data)))
    write_json(data / 'user-shop.json', dict(proof=str(pinned)))
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', 50_000)
    monkeypatch.setattr(retention, 'SETTLE_HEADROOM', 1_000)
    current = run(root, 'pi-90', closed=True)
    first = retention.settle(root, current)
    assert not first.get('skipped') and first['moved'] > 0
    assert retention._SETTLE_STATE[str(root.resolve())]['fruitless'] is False
    planned = []
    real = retention._plan
    monkeypatch.setattr(retention, '_plan', lambda *a, **k: planned.append(1) or real(*a, **k))
    # A plan that moved something runs again; this one finds only the pinned frame.
    second = retention.settle(root, current)
    assert not second.get('skipped') and second['moved'] == 0 and planned == [1]
    # Nothing aged since that fruitless plan: the next tidy answers without one.
    third = retention.settle(root, current)
    assert third['skipped'] == 'nothing_new_to_reclaim' and planned == [1]
    # A newer finished run ages one more folder: the plan runs again.
    fourth = retention.settle(root, run(root, 'pi-91', closed=True))
    assert not fourth.get('skipped') and planned == [1, 1]
