"""Only a complete, input-free preflight duplicate may lose its older PNG."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from maalimbus.deployment_evidence import startup_order_preview,diagnostic_index

SOURCE=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-124654/frame-0004.json'
pytestmark=pytest.mark.skipif(not SOURCE.with_suffix('.png').is_file(),reason='Private native deployment fixture')


def sample(tmp_path):
    run=tmp_path/'evidence/runtime/read';run.mkdir(parents=True)
    value=json.loads(SOURCE.read_text(encoding='utf8'))
    for n in (1,2):
        data=deepcopy(value);data.update(frame=f'frame-{n:04}',utc=f'2026-11-17T20:00:0{n}+00:00')
        (run/(data['frame']+'.json')).write_text(json.dumps(data),encoding='utf8')
        (run/(data['frame']+'.png')).write_bytes(SOURCE.with_suffix('.png').read_bytes())
    rows=[dict(event='map_observed',scene='PRE_BATTLE_TEAM',frame='frame-0001',utc='2026-11-17T20:00:01+00:00',input_sent=False),
        dict(event='mirror_loop_start',run_scope='scope',utc='2026-11-17T20:00:01.5+00:00'),
        dict(event='map_observed',scene='PRE_BATTLE_TEAM',frame='frame-0002',utc='2026-11-17T20:00:02+00:00',input_sent=False),
        dict(event='mirror_loop_stopped',reason='evidence_capacity_unavailable_before_input',clicks_sent=0,utc='2026-11-17T20:00:03+00:00')]
    (run/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf8')
    return run,rows


def test_only_the_older_preflight_is_a_diagnostic_not_the_actor_before_image(tmp_path):
    run,rows=sample(tmp_path)
    prior={p:p.read_bytes() for p in run.iterdir()}
    assert startup_order_preview(run,rows)==dict(preflight='frame-0001',actor='frame-0002')
    index=diagnostic_index((run.parent,))
    assert index[run]['bootstrap']=={'frame-0001'}
    assert index[run]['required']=={'frame-0002'}
    assert all(p.read_bytes()==b for p,b in prior.items())


def test_current_structural_tail_cannot_pin_only_the_old_preflight_replica(tmp_path):
    from maalimbus import capture_retention as retention
    run,rows=sample(tmp_path)
    projection=diagnostic_index((run.parent,))
    eligible=retention._run_rows(run,True,2,projection,{}, {})
    assert [p.stem for p,_ in eligible]==['frame-0001']
    assert (run/'frame-0002.png').is_file()


@pytest.mark.parametrize('fault',['input','unknown','different_order','low_score','missing_control','stale','changed_png','ambiguous_scope','team_change','foreign_episode'])
def test_uncertain_startup_keeps_both_captures(tmp_path,fault):
    run,rows=sample(tmp_path);p=run/'frame-0002.json';data=json.loads(p.read_text())
    if fault=='input':rows.insert(2,dict(event='window_intent',input_sent=False))
    elif fault=='unknown':rows[0]['scene']='UNKNOWN'
    elif fault=='different_order':
        for t in data['ocr']:
            if t['text'] in ('1','2'):t['text']={'1':'2','2':'1'}[t['text']]
    elif fault=='low_score':
        for t in data['ocr']:
            if t['text']=='1':t['score']=.89
    elif fault=='missing_control':data['ocr']=[t for t in data['ocr'] if 'Clear Selection' not in t['text']]
    elif fault=='stale':data['utc']='2026-11-17T20:01:02+00:00'
    elif fault=='changed_png':p.with_suffix('.png').write_bytes(b'corrupt')
    elif fault=='ambiguous_scope':rows.insert(2,dict(event='mirror_loop_start',run_scope='foreign'))
    elif fault=='team_change':data['ocr'].append(dict(text='TEAMS #3',box=[150,254,150,25],score=.99))
    else:rows.insert(2,dict(event='semantic_frame_proposal',episode='foreign'))
    p.write_text(json.dumps(data),encoding='utf8')
    before={f:f.read_bytes() for f in run.iterdir()}
    assert startup_order_preview(run,rows) is None
    assert all(f.read_bytes()==b for f,b in before.items())
