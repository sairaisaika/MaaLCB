"""Unjudged ordinary START keeps pending proof while bounding diagnostic reads."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import cv2,pytest
from maalimbus.hud_evidence import diagnostic_index
from maalimbus.battle_vision import start_button
from maalimbus.vision import Text
from maalimbus import capture_retention as retention,workspace

SOURCE=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-134824/frame-0066.json'
pytestmark=pytest.mark.skipif(not SOURCE.with_suffix('.png').is_file(),reason='Private native HUD fixture')


def sample(tmp_path):
    run=tmp_path/'evidence/runtime/animation';run.mkdir(parents=True)
    before=json.loads(SOURCE.read_text());image=cv2.resize(cv2.imread(str(SOURCE.with_suffix('.png'))),(1280,720),interpolation=cv2.INTER_AREA)
    for t in before['ocr']:t['box']=[round(v*2/3) for v in t['box']]
    before['size']=[1280,720]
    def frame(n,scene):
        data=deepcopy(before);pixels=image.copy();pixels[0,0]=(n,n,n)
        p=run/f'frame-{n:04}.png';cv2.imwrite(str(p),pixels)
        data.update(frame=p.stem,scene=scene,utc=f'2026-11-17T20:00:{n+1:02}+00:00',
                    image_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        if scene=='UNKNOWN':data['ocr']=[]
        p.with_suffix('.json').write_text(json.dumps(data))
        return data
    data=frame(1,'BATTLE_HUD');data['utc']='2026-11-17T20:00:01+00:00';(run/'frame-0001.json').write_text(json.dumps(data))
    box=start_button([Text(t['text'],t['box'],t['score']) for t in data['ocr']],data['size'],image);assert box
    x,y,w,h=box
    rows=[dict(event='mirror_loop_start',run_scope='scope',utc='2026-11-17T20:00:00+00:00'),
        dict(event='battle_observed',frame='frame-0001',scene='BATTLE_HUD',utc='2026-11-17T20:00:01.1+00:00'),
        dict(event='window_intent',page='BATTLE_HUD',reason='start_button_submits_the_assigned_turn',
            target=list(box),point=[x+w//2,y+h//2],delay_ms=500,utc='2026-11-17T20:00:02+00:00')]
    for n in range(2,8):
        frame(n,'UNKNOWN');rows.append(dict(event='battle_observed',frame=f'frame-{n:04}',scene='UNKNOWN',utc=f'2026-11-17T20:00:{n+1:02}.1+00:00'))
    return run,rows,frame


def project(run,rows):
    (run/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    return diagnostic_index((run.parent,)).get(run,{})


def test_pending_unknown_read_history_is_sampled_without_crediting_the_turn(tmp_path):
    run,rows,_=sample(tmp_path);original={p:p.read_bytes() for p in run.iterdir()};p=project(run,rows)
    assert p['inflight_reads']=={'frame-0003','frame-0004','frame-0005'}
    assert p['required']=={'frame-0001','frame-0002','frame-0006','frame-0007'}
    assert not p.get('turn_answers')
    eligible=retention._run_rows(run,True,2,hud_index={run:p})
    assert {f.stem for f,_ in eligible}==p['inflight_reads']
    assert all(f.read_bytes()==b for f,b in original.items())


@pytest.mark.parametrize('fault',['short_touch','wrong_control','new_input','named_page','corrupt_before','missing_first','old_capture','foreign'])
def test_unproven_animation_context_never_authorizes_sampling(tmp_path,fault):
    run,rows,_=sample(tmp_path)
    if fault=='short_touch':rows[2]['delay_ms']=20
    elif fault=='wrong_control':rows[2].update(target=[100,100,80,80],point=[140,140])
    elif fault=='new_input':rows.insert(-1,dict(event='flow_intent'))
    elif fault=='named_page':rows.insert(-1,dict(event='battle_observed',scene='SHOP',utc='2026-11-17T20:00:07.5+00:00'))
    elif fault=='corrupt_before':(run/'frame-0001.png').write_bytes(b'changed')
    elif fault=='missing_first':(run/'frame-0002.png').unlink()
    elif fault=='old_capture':
        p=run/'frame-0002.json';d=json.loads(p.read_text());d['utc']='2026-11-17T20:00:01+00:00';p.write_text(json.dumps(d))
    else:rows.insert(1,dict(event='semantic_frame_proposal',episode='other'))
    assert not project(run,rows).get('inflight_reads')


def test_human_review_pin_and_pending_bytes_survive_sampling(tmp_path,monkeypatch):
    run,rows,_=sample(tmp_path);project(run,rows)
    config=tmp_path/'config';config.mkdir();pending=config/'pending.json'
    pending.write_text(json.dumps(dict(pending='unknown',before=str(run/'frame-0001.json'),review=str(run/'frame-0003.json'))))
    original=pending.read_bytes();budget=workspace.size(tmp_path)+60000;monkeypatch.setattr(workspace,'BUDGET_BYTES',budget)
    plan=retention.plan(tmp_path,run,100000,recent=2,budget=budget);assert plan['sufficient']
    assert not {Path(r['path']).name for r in plan['files']}&{'frame-0001.png','frame-0002.png','frame-0003.png','frame-0006.png','frame-0007.png'}
    retention.apply(tmp_path,run,plan)
    assert pending.read_bytes()==original


def test_known_next_turn_uses_outcome_rules_instead_of_inflight_sampling(tmp_path):
    run,rows,frame=sample(tmp_path);data=frame(8,'BATTLE_HUD')
    for t in data['ocr']:
        if t['text'].strip().isdigit() and t['box'][0]<100 and 50<t['box'][1]<100:t['text']=str(int(t['text'])+1)
    (run/'frame-0008.json').write_text(json.dumps(data))
    rows.append(dict(event='battle_observed',frame='frame-0008',scene='BATTLE_HUD',utc='2026-11-17T20:00:09.1+00:00'))
    p=project(run,rows)
    assert not p.get('inflight_reads') and p.get('turn_answers')=={'frame-0001':'frame-0008'}
