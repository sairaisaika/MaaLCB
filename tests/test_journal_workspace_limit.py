"""Live and offline writers preserve complete capture pairs."""
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import recognition
from maalimbus import workspace
from maalimbus.evidence_capacity import EvidenceCapacityUnavailable


def test_compressed_capture_is_lossless_and_hashes_actual_bytes(tmp_path,monkeypatch):
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    pixels=np.random.default_rng(1).integers(0,256,(40,80,3),dtype=np.uint8)
    name=journal.frame(pixels,[],'UNKNOWN')
    png=journal.directory/(name+'.png')
    record=json.loads((journal.directory/(name+'.json')).read_text(encoding='utf-8'))
    assert record['image_sha256']==hashlib.sha256(png.read_bytes()).hexdigest()
    assert record['frame']==name
    assert np.array_equal(cv2.imread(str(png)),pixels)


def test_limit_preserves_previous_frames_and_writes_no_partial_pair(tmp_path,monkeypatch):
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current', history_maintenance=True)
    image=np.zeros((40,80,3),np.uint8)
    journal.frame(image,[],'UNKNOWN')
    before={p.name:p.read_bytes() for p in journal.directory.iterdir()}
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+1)
    with pytest.raises(EvidenceCapacityUnavailable,match='Workspace budget exceeded'):
        journal.frame(image,[],'UNKNOWN')
    assert journal.index==1
    assert {p.name:p.read_bytes() for p in journal.directory.iterdir()}==before


def test_installed_capture_counts_the_whole_project(tmp_path,monkeypatch):
    app=tmp_path/'dist/MaaLimbus';app.mkdir(parents=True)
    monkeypatch.setattr(recognition,'ROOT',app)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current', history_maintenance=True)
    (tmp_path/'other-output.bin').write_bytes(b'x'*100)
    monkeypatch.setattr(workspace,'BUDGET_BYTES',1)
    with pytest.raises(EvidenceCapacityUnavailable,match='Workspace budget exceeded'):
        journal.frame(np.zeros((1,1,3),np.uint8),[],'UNKNOWN')
    assert not list(journal.directory.glob('frame-*'))


def test_live_capture_uses_actual_disk_availability(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, 'ROOT', tmp_path)
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', 1)
    journal = recognition.Journal(tmp_path/'evidence/runtime/current')
    image = np.zeros((40, 80, 3), np.uint8)
    journal.frame(image, [], 'UNKNOWN')
    before = {path.name: path.read_bytes() for path in journal.directory.iterdir()}

    def no_space(*args):
        raise ValueError('Runtime evidence volume has no space')

    monkeypatch.setattr(workspace, 'require_disk_space', no_space)
    with pytest.raises(EvidenceCapacityUnavailable, match='Runtime evidence volume'):
        journal.frame(image, [], 'UNKNOWN')
    assert {path.name: path.read_bytes() for path in journal.directory.iterdir()} == before


def test_direct_input_requires_fresh_planning_after_storage_maintenance(tmp_path,monkeypatch):
    from maalimbus.evidence_capacity import EvidenceCapacity,EvidenceCapacityUnavailable
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    monkeypatch.setattr(EvidenceCapacity,'admit',lambda *a,**k:dict(storage_maintenance=True,input_sent=False))
    with pytest.raises(EvidenceCapacityUnavailable,match='Fresh planning required'):
        journal.before_input('click',(1,2))
    events=[json.loads(line) for line in (journal.directory/'events.jsonl').read_text().splitlines()]
    assert events[-1]['event']=='evidence_capacity_refresh_required'
    assert events[-1]['input_sent'] is False
