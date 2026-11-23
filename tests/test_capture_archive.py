"""A reclaimed capture is moved to the archive beside the project, never destroyed.

The project folder's size limit is a warning line (the user's rule of 2026-11-22):
when the program makes room it moves old diagnostic frames out, keeping their path and
recording where each went. Until 2026-11-23 the same step unlinked them.
"""
import hashlib

import pytest

from maalimbus import capture_retention as retention


def project(tmp_path):
    root = tmp_path / 'project'
    frame = root / 'evidence/runtime/run-1/frame-0001.png'
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b'frame bytes')
    return root, frame, hashlib.sha256(b'frame bytes').hexdigest()


def test_the_frame_leaves_the_project_for_the_same_path_in_the_archive(tmp_path):
    root, frame, sha = project(tmp_path)
    assert retention.retire_capture(frame, root, sha) == 'evidence/runtime/run-1/frame-0001.png'
    archived = tmp_path / 'project-evidence-archive/evidence/runtime/run-1/frame-0001.png'
    assert not frame.exists() and archived.read_bytes() == b'frame bytes'


def test_a_frame_already_archived_with_the_same_bytes_is_simply_released(tmp_path):
    root, frame, sha = project(tmp_path)
    archived = tmp_path / 'project-evidence-archive/evidence/runtime/run-1/frame-0001.png'
    archived.parent.mkdir(parents=True)
    archived.write_bytes(b'frame bytes')
    retention.retire_capture(frame, root, sha)
    assert not frame.exists() and archived.read_bytes() == b'frame bytes'


def test_a_different_file_in_the_archive_stops_the_reclaim_and_keeps_both(tmp_path):
    root, frame, sha = project(tmp_path)
    archived = tmp_path / 'project-evidence-archive/evidence/runtime/run-1/frame-0001.png'
    archived.parent.mkdir(parents=True)
    archived.write_bytes(b'something else')
    with pytest.raises(ValueError, match='different capture'):
        retention.retire_capture(frame, root, sha)
    assert frame.read_bytes() == b'frame bytes' and archived.read_bytes() == b'something else'


def test_across_volumes_the_copy_is_checked_before_the_frame_is_removed(tmp_path, monkeypatch):
    import os
    root, frame, sha = project(tmp_path)

    def cannot_rename(*a, **k):
        raise OSError('different volume')
    monkeypatch.setattr(os, 'replace', cannot_rename)
    retention.retire_capture(frame, root, sha)
    archived = tmp_path / 'project-evidence-archive/evidence/runtime/run-1/frame-0001.png'
    assert not frame.exists() and archived.read_bytes() == b'frame bytes'
    # A copy that does not match the planned digest is discarded and the frame stays.
    root, frame, sha = project(tmp_path / 'second')
    with pytest.raises(ValueError, match='differs from the planned bytes'):
        retention.retire_capture(frame, root, 'not-the-digest')
    assert frame.read_bytes() == b'frame bytes'
    assert not (tmp_path / 'second/project-evidence-archive/evidence/runtime/run-1/frame-0001.png').exists()
