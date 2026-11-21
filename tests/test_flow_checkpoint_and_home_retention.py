"""Observed navigation checkpoints are not replayed inputs or business receipts."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from maalimbus import capture_retention as retention, runner, session_flow as flows, workspace
from maalimbus.learning_dataset import digest
from maalimbus.storage import write_json


def home():
    return dict(scene='HOME',frame='frame-0001',image_sha256='1'*64,size=[1920,1080],
                ocr=[dict(text='LUNACY',score=.99,box=[806,952,56,26])])


def test_fresh_home_checkpoint_finishes_title_navigation_with_one_read_and_zero_inputs(tmp_path):
    calls=[];events=[]
    def observe(**kw):calls.append('read');return home()
    controller=SimpleNamespace(post_click=lambda *p:pytest.fail('replayed title input'),
                               post_start_app=lambda *p:pytest.fail('replayed start_app'))
    rows=runner.run_flow(None,controller,SimpleNamespace(record=lambda n,**f:events.append((n,f))),
        tmp_path,None,flows.flow('finish_launch'),observer=SimpleNamespace(observe=observe,directory=tmp_path))
    assert calls==['read'] and len(rows)==3
    assert all(row['passed'] and row['clicks']==0 for row in rows)
    assert all(row.get('skipped') and row['page']=='HOME' for row in rows[:2])
    assert rows[2]['reason']=='flow_token_seen'
    assert events[0][0]=='flow_checkpoint_observed' and events[0][1]['input_sent'] is False


@pytest.mark.parametrize('fault',['unknown','overlay','missing_hash','missing_frame','low_score','wrong_band'])
def test_unverified_or_covered_home_text_cannot_skip_the_title(fault):
    record=home()
    if fault=='unknown':record['scene']='UNKNOWN'
    elif fault=='overlay':record['scene']='UNKNOWN_DIALOG'
    elif fault=='missing_hash':record.pop('image_sha256')
    elif fault=='missing_frame':record.pop('frame')
    elif fault=='low_score':record['ocr'][0]['score']=.1
    elif fault=='wrong_band':record['ocr'][0]['box']=[100,100,56,26]
    assert flows.checkpoint_index(record,flows.flow('finish_launch'))==0


def recorded_home(root, *, sealed=True):
    run=root/'evidence/runtime/window-only-home';run.mkdir(parents=True)
    rows=[]
    for n in range(1,15):
        p=run/f'frame-{n:04}.png';p.write_bytes(bytes([n])*10000)
        write_json(p.with_suffix('.json'),dict(scene='HOME',image_sha256=digest(p)))
        rows.append(dict(event='map_observed',scene='HOME',frame=p.stem,input_sent=False,image_sha256=digest(p)))
    if sealed:rows.append(dict(event='window_capture_session_closed',input_sealed=True,input_free_home=True))
    (run/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n',encoding='utf-8')
    return run,rows


def test_only_sealed_input_free_home_diagnostics_can_compact_and_private_proof_stays(tmp_path):
    run,_=recorded_home(tmp_path)
    assert [p.stem for p,_ in retention._run_rows(run,False,8)] == [f'frame-{n:04}' for n in range(2,13)]
    write_json(tmp_path/'config/receipt.json',dict(home=str(run/'frame-0003.json')))
    metadata={p:p.read_bytes() for p in run.glob('*.json')}
    new=tmp_path/'evidence/runtime/new';new.mkdir()
    plan=retention.plan(tmp_path,new,26000,budget=workspace.size(tmp_path)+25000)
    assert plan['sufficient'] and plan['files']
    assert 'frame-0003.png' not in [p['path'].split('/')[-1] for p in plan['files']]
    retention.apply(tmp_path,new,plan)
    assert (run/'frame-0001.png').exists() and (run/'frame-0003.png').exists()
    assert all((run/f'frame-{n:04}.png').exists() for n in (13,14))
    assert all(p.read_bytes()==body for p,body in metadata.items())


@pytest.mark.parametrize('fault',['unsealed','action','unknown_event','different_page','explicit_sent'])
def test_home_readiness_is_not_permission_to_compact_active_or_action_evidence(tmp_path,fault):
    run,rows=recorded_home(tmp_path,sealed=fault!='unsealed')
    if fault=='action':rows.insert(2,dict(event='flow_intent',step='home_confirm'))
    elif fault=='unknown_event':rows.insert(2,dict(event='unrecognized_native_operation'))
    elif fault=='different_page':rows[2]['scene']='RUN_REWARD_DIALOG'
    elif fault=='explicit_sent':rows[2]['input_sent']=True
    (run/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n',encoding='utf-8')
    new=tmp_path/'evidence/runtime/new';new.mkdir()
    plan=retention.plan(tmp_path,new,26000,budget=workspace.size(tmp_path)+25000)
    assert not plan['sufficient'] and plan['files']==[]
