"""A storage interruption must never erase the only readable report bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

from maalimbus import capture_retention, evidence_reports, workspace

spec = importlib.util.spec_from_file_location(
    'rollover', Path(__file__).resolve().parents[1] / 'tools/rollover_report_archive.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

ARCHIVE = 'build/reports-generation2.zip'
RECIPE = 'build/reports-generation1-recipe.json'
OPERATION = 'build/report-rollover-generation2.json'


def setup(root):
    build = root / 'build'
    build.mkdir()
    originals = {
        'build/old.json': b'{"frame":"evidence/runtime/old/frame-0001.json","paid":false}',
        'build/one.json': b'{"frame":"evidence/runtime/a/frame-0002.json","passed":true}',
        'build/two.json': b'{"frame":"evidence/runtime/b/frame-0003.json","passed":false}',
    }
    old = build / 'reports-generation1.zip'
    with zipfile.ZipFile(old, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.comment = b'original metadata survives'
        archive.writestr('build/old.json', originals['build/old.json'])
    body = old.read_bytes()
    index = dict(version=1, kind='evidence_report_archive',
                 archive='build/reports-generation1.zip', sha256=tool.digest(body),
                 members=[dict(path='build/old.json', bytes=len(originals['build/old.json']),
                               sha256=tool.digest(originals['build/old.json']))])
    (root / evidence_reports.INDEX).write_bytes(tool.encoded(index))
    for name, data in list(originals.items())[1:]:
        (root / name).write_bytes(data)
    selection = dict(version=1, kind='closed_report_selection', sealed=True, reports=[
        dict(path=name, bytes=len(data), sha256=tool.digest(data))
        for name, data in list(originals.items())[1:]])
    return selection, originals, body


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def run(root, selection, **kwargs):
    return tool.rollover(root, selection, ARCHIVE, RECIPE, OPERATION, **kwargs)


def test_complete_rollover_preserves_references_bytes_and_old_container(tmp_path):
    selection, originals, old = setup(tmp_path)
    pins = capture_retention._reference_keep(tmp_path)
    result = run(tmp_path, selection)
    assert result['passed'] and result['archived_reports'] == 3
    assert result['raw_reports_removed_now'] == 2
    assert capture_retention._reference_keep(tmp_path) == pins
    for path, body in originals.items():
        assert evidence_reports.read_report_bytes(path, root=tmp_path) == body
    active = evidence_reports.load_index(tmp_path)
    members = dict(evidence_reports._verified_members(active['archive'].read_bytes(), active['value']))
    recipe = json.loads((tmp_path / RECIPE).read_bytes())
    assert tool.reconstruct(recipe, members) == old
    assert not (tmp_path / 'build/reports-generation1.zip').exists()
    assert json.loads((tmp_path / OPERATION).read_bytes())['record']['phase'] == 'completed'
    after = snapshot(tmp_path)
    assert run(tmp_path, selection)['raw_reports_removed_now'] == 0
    assert snapshot(tmp_path) == after


@pytest.mark.parametrize('point', ['before_index', 'after_index', 'after_report', 'after_old_archive'])
def test_every_interruption_leaves_all_reports_readable_and_resumes_without_replay(tmp_path, point):
    selection, originals, old = setup(tmp_path)
    pins = capture_retention._reference_keep(tmp_path)
    def interrupt(phase):
        if phase == point:
            raise RuntimeError('injected storage interruption')
    with pytest.raises(RuntimeError, match='injected'):
        run(tmp_path, selection, fault=interrupt)
    for path, body in originals.items():
        assert evidence_reports.read_report_bytes(path, root=tmp_path) == body
    assert capture_retention._reference_keep(tmp_path) == pins
    assert run(tmp_path, selection)['passed']
    assert capture_retention._reference_keep(tmp_path) == pins


def test_planning_and_insufficient_capacity_are_read_only(tmp_path, monkeypatch):
    selection, _, _ = setup(tmp_path)
    original = snapshot(tmp_path)
    operation, body = tool.prepare(tmp_path, selection, ARCHIVE, RECIPE)
    assert operation['phase'] == 'prepared' and body
    assert snapshot(tmp_path) == original
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(tmp_path) + 100)
    with pytest.raises(ValueError, match='budget'):
        run(tmp_path, selection)
    assert snapshot(tmp_path) == original


@pytest.mark.parametrize('fault', ['raw', 'old_zip', 'duplicate', 'unsealed', 'control', 'escape'])
def test_invalid_selection_or_changed_inputs_do_not_publish_or_retire(tmp_path, fault):
    selection, _, _ = setup(tmp_path)
    if fault == 'raw':
        (tmp_path / 'build/one.json').write_bytes(b'{"changed":true}')
    elif fault == 'old_zip':
        old = tmp_path / 'build/reports-generation1.zip'
        old.write_bytes(old.read_bytes() + b'changed')
    elif fault == 'duplicate':
        selection['reports'].append(selection['reports'][0].copy())
    elif fault == 'unsealed':
        selection['sealed'] = False
    elif fault == 'control':
        selection['reports'][0]['path'] = evidence_reports.INDEX
    else:
        selection['reports'][0]['path'] = 'build/../config/user.json'
    original = snapshot(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        run(tmp_path, selection)
    assert snapshot(tmp_path) == original


def test_changed_raw_after_index_publish_is_preserved_and_old_archive_not_retired(tmp_path):
    selection, originals, _ = setup(tmp_path)
    def change(phase):
        if phase == 'after_index':
            (tmp_path / 'build/two.json').write_bytes(b'{"new revision":true}')
    with pytest.raises(ValueError, match='Raw report changed'):
        run(tmp_path, selection, fault=change)
    assert (tmp_path / 'build/two.json').read_bytes() == b'{"new revision":true}'
    assert (tmp_path / 'build/reports-generation1.zip').exists()
    # The original version remains in the verified archive, independently of the new raw revision.
    active = evidence_reports.load_index(tmp_path)
    archived = dict(evidence_reports._verified_members(active['archive'].read_bytes(), active['value']))
    assert archived['build/two.json'] == originals['build/two.json']


def test_operation_tamper_is_not_treated_as_resume_authority(tmp_path):
    selection, _, _ = setup(tmp_path)
    def interrupt(phase):
        if phase == 'before_index':
            raise RuntimeError('interrupt')
    with pytest.raises(RuntimeError):
        run(tmp_path, selection, fault=interrupt)
    path = tmp_path / OPERATION
    value = json.loads(path.read_bytes())
    value['record']['phase'] = 'completed'
    path.write_bytes(tool.encoded(value))
    original = snapshot(tmp_path)
    with pytest.raises(ValueError, match='checksum'):
        run(tmp_path, selection)
    assert snapshot(tmp_path) == original
