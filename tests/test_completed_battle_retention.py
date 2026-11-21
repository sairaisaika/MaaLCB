"""Closed failure can compact an earlier finished battle, never its final cause."""
import json
from pathlib import Path

import pytest

from maalimbus import capture_retention as retention, workspace
from maalimbus.storage import write_json


def finished_then_failed(root):
    folder=root/'evidence/runtime/closed-failed';folder.mkdir(parents=True)
    rows=[]
    for number in range(1,21):
        name=f'frame-{number:04}'
        png=folder/(name+'.png');png.write_bytes(bytes([number])*10000)
        scene='BATTLE_HUD' if number<12 else 'BATTLE_RESULT' if number==12 else 'MAP'
        sha=retention.digest(png)
        write_json(png.with_suffix('.json'),dict(scene=scene,image_sha256=sha))
        rows.append(dict(event='map_observed',frame=name,scene=scene,image_sha256=sha))
        if number in (3,6,9,16):
            rows.append(dict(event='window_intent',page='BATTLE_HUD' if number<12 else 'MAP'))
    rows.append(dict(event='mirror_loop_stopped',passed=False,reason='unexpected_successor'))
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    return folder


@pytest.mark.parametrize('fault',[None,'missing','changed_pixels','changed_record','changed_event','current'])
def test_only_verified_finished_old_battle_can_release_earlier_input_boundaries(tmp_path,fault):
    folder=finished_then_failed(tmp_path)
    if fault=='missing':(folder/'frame-0012.png').unlink()
    if fault=='changed_pixels':(folder/'frame-0012.png').write_bytes(b'changed')
    if fault=='changed_record':write_json(folder/'frame-0012.json',dict(scene='UNKNOWN'))
    if fault=='changed_event':
        path=folder/'events.jsonl';path.write_text(path.read_text().replace('BATTLE_RESULT','UNKNOWN'))
    eligible={p.stem for p,r in retention._run_rows(folder,fault=='current',2)}
    for n in (3,4,6,7):
        assert (f'frame-{n:04}' in eligible)==(fault in (None,'current'))
    # Last battle input pair, result page and the later failed MAP causal pair.
    assert all(f'frame-{n:04}' not in eligible for n in (1,9,10,11,12,13,16,17,19,20))


def test_recent_closed_session_is_eligible_but_business_reference_still_wins(tmp_path):
    folder=finished_then_failed(tmp_path)
    current=tmp_path/'evidence/runtime/current';current.mkdir()
    config=tmp_path/'config';config.mkdir()
    write_json(config/'pending.json',dict(proof=str(folder/'frame-0006.json')))
    result=retention.plan(tmp_path,current,20000,recent=2,
                          budget=workspace.size(tmp_path)+19000)
    names={Path(row['path']).stem for row in result['files']}
    assert 'frame-0003' in names and 'frame-0006' not in names
    assert result['sufficient']


def test_native_battle_event_can_omit_digest_while_its_original_record_binds_pixels(tmp_path):
    folder=finished_then_failed(tmp_path);path=folder/'events.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row.get('scene')=='BATTLE_RESULT':row.pop('image_sha256')
    path.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
    eligible={p.stem for p,r in retention._run_rows(folder,False,2)}
    assert 'frame-0003' in eligible and 'frame-0006' in eligible
    assert 'frame-0012' not in eligible
