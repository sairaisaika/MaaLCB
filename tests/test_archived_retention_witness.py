"""Lossless storage cannot silently erase a diagnostic witness's availability."""
import json

import pytest

from maalimbus import capture_retention as retention,native_image_archive as archive
from maalimbus.native_evidence import frame_reference
from test_completed_battle_retention import finished_then_failed
from test_ordinary_battle_retention import fight
from test_observation_frame import capture


def original_pairs(folder):
    """Give these legacy protocol fixtures actual canonical PNG/JSON pairs."""
    records=list(folder.glob('frame-*.json'));hashes={}
    for path in records:
        scene=json.loads(path.read_bytes())['scene']
        _,raw=capture(folder,path.stem,scene=scene)
        pixels=path.with_suffix('.png').read_bytes()+path.stem.encode()*5000
        raw['image_sha256']=archive.sha(pixels)
        path.with_suffix('.png').write_bytes(pixels);path.write_text(json.dumps(raw))
        hashes[path.stem]=raw['image_sha256']
    log=folder/'events.jsonl';rows=[json.loads(line) for line in log.read_text().splitlines()]
    for row in rows:
        if row.get('image_sha256') and row.get('frame') in hashes:
            row['image_sha256']=hashes[row['frame']]
    log.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
    return rows


def archive_witness(root,path,monkeypatch):
    pixels=path.with_suffix('.png').read_bytes();expected=frame_reference(path)
    entry=dict(path=path.with_suffix('.png').relative_to(root).as_posix(),bytes=len(pixels),
               sha256=archive.sha(pixels),record_sha256=archive.sha(path.read_bytes()))
    # Candidate-policy boundaries are separately covered in test_archive_page_ownership.
    monkeypatch.setattr(archive,'candidates',lambda root:[entry])
    assert archive.compact(root)['files']==1
    assert not path.with_suffix('.png').exists() and frame_reference(path)==expected
    return archive.load_index(root)['members'][entry['path']]


def test_archived_battle_result_keeps_exact_same_diagnostic_eligibility(tmp_path,monkeypatch):
    folder=finished_then_failed(tmp_path);rows=original_pairs(folder)
    expected=retention._completed_battle_inputs(folder,rows)
    names={p.stem for p,_ in retention._run_rows(folder,False,2)}
    assert {'frame-0003','frame-0006'}<=expected
    archive_witness(tmp_path,folder/'frame-0012.json',monkeypatch)
    assert retention._completed_battle_inputs(folder,rows)==expected
    assert {p.stem for p,_ in retention._run_rows(folder,False,2)}==names


def test_archived_answered_hud_keeps_exact_same_diagnostic_eligibility(tmp_path,monkeypatch):
    folder,_=fight(tmp_path);rows=original_pairs(folder)
    expected=retention._older_hud_diagnostics(folder,rows)
    assert expected=={'frame-0003','frame-0006','frame-0009'}
    archive_witness(tmp_path,folder/'frame-0004.json',monkeypatch)
    assert retention._older_hud_diagnostics(folder,rows)==expected


@pytest.mark.parametrize('owner',['result','hud'])
@pytest.mark.parametrize('fault',['archive','event','record','raw'])
def test_archiving_never_hides_a_changed_or_unbound_witness(tmp_path,monkeypatch,owner,fault):
    folder=finished_then_failed(tmp_path) if owner=='result' else fight(tmp_path)[0]
    rows=original_pairs(folder);name='frame-0012' if owner=='result' else 'frame-0004'
    path=folder/(name+'.json');entry=archive_witness(tmp_path,path,monkeypatch)
    if owner=='hud':
        # A later independent HUD may legitimately answer the same read. Make
        # both alternatives unavailable, then prove the intact cold witness
        # still answers it before damaging that witness in this negative case.
        for n in (5,6):(folder/('frame-%04d.png'%n)).write_bytes(b'unavailable independent read')
        assert 'frame-0003' in retention._older_hud_diagnostics(folder,rows)
    if fault=='archive':(tmp_path/entry['archive']).write_bytes(b'changed')
    elif fault=='raw':path.with_suffix('.png').write_bytes(b'corrupt raw takes precedence')
    elif fault=='event':
        for row in rows:
            if row.get('frame')==name:row['image_sha256']='0'*64
    else:
        value=json.loads(path.read_bytes());value['image_sha256']='0'*64
        path.write_text(json.dumps(value))
    if owner=='result':assert retention._completed_battle_inputs(folder,rows) is None
    else:assert 'frame-0003' not in retention._older_hud_diagnostics(folder,rows)
