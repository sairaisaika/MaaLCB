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
