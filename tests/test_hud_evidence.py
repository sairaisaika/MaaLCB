"""One battle owns a diagnostic window across recorder restarts."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus.hud_evidence import diagnostic_index
from maalimbus import capture_retention as retention,workspace


def recorder(base,name,minute,scope='scope'):
    run=base/name;run.mkdir(parents=True);rows=[dict(event='mirror_loop_start',run_scope=scope)]
    def frame(n):
        image=np.full((1080,1920,3),n,np.uint8)
        image[:64,:64]=np.random.default_rng(n).integers(0,256,(64,64,3),dtype=np.uint8)
        p=run/f'frame-{n:04}.json';cv2.imwrite(str(p.with_suffix('.png')),image)
        data=dict(frame=p.stem,scene='BATTLE_HUD',size=[1920,1080],image_sha256=hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest(),
                  ocr=[dict(text='WAVE',box=[20,30,60,30],score=.99),dict(text='TURN',box=[20,90,60,30],score=.99)])
        p.write_text(json.dumps(data));rows.append(dict(event='battle_observed',frame=p.stem,scene='BATTLE_HUD',
            image_sha256=data['image_sha256'],utc=f'2026-11-17T10:{minute:02}:{n*2:02}+00:00'));return p
    frame(1)
    for n in (2,4):
        frame(n);rows.append(dict(event='window_intent',page='BATTLE_HUD',reason='win_rate_is_the_proven_auto_assign_control',
            target=[100,100,80,40],point=[140,120],delay_ms=500,utc=f'2026-11-17T10:{minute:02}:{n*2+1:02}+00:00'))
        frame(n+1)
    rows.append(dict(event='mirror_loop_stopped',passed=False,reason='evidence_capacity_unavailable_before_input'))
    save(run,rows);return run,rows


def save(run,rows):(run/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')


@pytest.mark.parametrize('fault',[None,'foreign','page_boundary','changed_after','short_touch','unknown_role',
                                  'malformed_scope','invalid_event','invalid_scene'])
def test_only_answered_nonfinancial_pairs_share_a_scope_owned_window(tmp_path,fault):
    base=tmp_path/'evidence/runtime';old,rows=recorder(base,'old',0)
    new,_=recorder(base,'new',2,scope='other' if fault=='foreign' else 'scope')
    if fault=='page_boundary':
        other=base/'map';other.mkdir();save(other,[dict(event='map_observed',scene='MAP',frame='frame-0001',utc='2026-11-17T10:01:00+00:00')])
    elif fault=='changed_after':(old/'frame-0003.png').write_bytes(b'changed')
    elif fault=='short_touch':next(r for r in rows if r['event']=='window_intent')['delay_ms']=20;save(old,rows)
    elif fault=='unknown_role':next(r for r in rows if r['event']=='window_intent')['reason']='unknown_control';save(old,rows)
    elif fault=='malformed_scope':rows[0]['run_scope']={'invalid':True};save(old,rows)
    elif fault=='invalid_event':rows.append(dict(event=[]));save(old,rows)
    elif fault=='invalid_scene':rows[1]['scene']={};save(old,rows)
    index=diagnostic_index((base,));first=index.get(old,{}).get('superseded',set())
    assert ('frame-0002' in first)==(fault is None)
    if fault is None:
        assert first=={'frame-0002','frame-0003','frame-0004','frame-0005'}
        assert index[old]['bootstrap']=={'frame-0001'}
        assert not index[new]['superseded']
        eligible={p.stem for p,_ in retention._run_rows(old,False,2,hud_index=index)}
        assert eligible=={'frame-0001','frame-0002','frame-0003','frame-0004','frame-0005'}


def test_external_pair_roots_and_all_native_metadata_survive_pressure_apply(tmp_path):
    base=tmp_path/'evidence/runtime';old,_=recorder(base,'old',0);new,_=recorder(base,'new',2)
    config=tmp_path/'config';config.mkdir();(config/'pending.json').write_text(json.dumps(dict(before=str(old/'frame-0002.json'))))
    original={p:p.read_bytes() for p in base.glob('*/*.json')}
    plan=retention.plan(tmp_path,new,70000,recent=2,budget=workspace.size(tmp_path)+40000)
    assert plan['sufficient']
    assert not {str(old/'frame-0002.png'),str(old/'frame-0003.png')}.intersection(str(tmp_path/r['path']) for r in plan['files'])
    assert {str(old/'frame-0001.png'),str(old/'frame-0004.png'),str(old/'frame-0005.png')}.intersection(str(tmp_path/r['path']) for r in plan['files'])
    retention.apply(tmp_path,new,plan)
    assert all(p.read_bytes()==body for p,body in original.items())


@pytest.mark.parametrize('fault',[None,'unknown_first_input','no_later_pixels'])
def test_redundant_preflight_read_does_not_require_resurrecting_retired_input_pixels(tmp_path,fault):
    base=tmp_path/'evidence/runtime';old,rows=recorder(base,'old',0)
    for n in (2,3): (old/f'frame-{n:04}.png').unlink()
    if fault=='unknown_first_input':next(r for r in rows if r['event']=='window_intent')['reason']='unjudged_control';save(old,rows)
    if fault=='no_later_pixels':
        for n in (4,5):(old/f'frame-{n:04}.png').unlink()
    index=diagnostic_index((base,));row=index.get(old,{})
    assert ('frame-0001' in row.get('bootstrap',set()))==(fault is None)
    assert ('frame-0002','frame-0003') not in row.get('causal_pairs',set())
    assert not {'frame-0002','frame-0003'}.intersection(row.get('superseded',set()))


@pytest.mark.parametrize('fault',[None,'same_turn','different_wave','changed_after','unknown_input','backward_time'])
def test_native_turn_progress_closes_diagnostics_without_closing_game_business(tmp_path,fault):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'battle',0);rows.pop()
    start=next(r for r in reversed(rows) if r['event']=='window_intent')
    start['reason']='start_button_submits_the_assigned_turn'
    for n in range(1,9):
        p=run/f'frame-{n:04}.json'
        if n>5:
            image=np.full((1080,1920,3),n,np.uint8);cv2.imwrite(str(p.with_suffix('.png')),image)
        unknown=n in (5,6,7)
        data=dict(frame=p.stem,scene='UNKNOWN' if unknown else 'BATTLE_HUD',size=[1920,1080],
            image_sha256=hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest(),
            ocr=[] if unknown else [dict(text=t,box=b,score=.99) for t,b in (
                ('WAVE',[20,30,60,30]),('2/2' if n==8 and fault=='different_wave' else '1/1',[80,30,40,30]),
                ('TURN',[20,90,60,30]),('4' if n==8 and fault!='same_turn' else '3',[80,90,35,30]))])
        p.write_text(json.dumps(data))
        if n>5:rows.append(dict(event='battle_observed',frame=p.stem,utc=f'2026-11-17T10:00:{n*2:02}+00:00'))
        event=next(r for r in rows if r.get('frame')==p.stem)
        event.update(scene=data['scene'],image_sha256=data['image_sha256'])
    if fault=='changed_after':(run/'frame-0008.png').write_bytes(b'changed')
    if fault=='backward_time':rows[-1]['utc']='2026-11-17T10:00:08+00:00'
    if fault=='unknown_input':rows.insert(-1,dict(event='flow_intent'))
    rows.append(dict(event='mirror_loop_stopped',passed=False));save(run,rows)
    original={p:p.read_bytes() for p in run.glob('*.json')}
    index=diagnostic_index((base,));projection=index.get(run,{})
    assert projection.get('turn_answers',{})==({'frame-0004':'frame-0008'} if fault is None else {})
    if fault is None:
        eligible={p.stem for p,_ in retention._run_rows(run,False,2,hud_index=index)}
        assert {'frame-0002','frame-0003','frame-0006','frame-0007'}<=eligible
        assert not {'frame-0004','frame-0005','frame-0008'}.intersection(eligible)
        # The latest raw tail remains protected until a newer read replaces it.
        active={p.stem for p,_ in retention._run_rows(run,True,2,hud_index=index)}
        assert 'frame-0007' not in active
    assert all(p.read_bytes()==body for p,body in original.items())


@pytest.mark.parametrize('mode',['same_visit','foreign_scope','different_page'])
def test_turn_checkpoint_is_not_a_per_recorder_permanent_pin(tmp_path,mode):
    base=tmp_path/'evidence/runtime';old,rows=recorder(base,'old',0)
    next(r for r in reversed(rows) if r['event']=='window_intent')['reason']='start_button_submits_the_assigned_turn'
    for n in range(1,6):
        p=old/f'frame-{n:04}.json';d=json.loads(p.read_text())
        d['ocr'].append(dict(text='4' if n==5 else '3',box=[80,90,35,30],score=.99));p.write_text(json.dumps(d))
    save(old,rows)
    recorder(base,'new',2,scope='other' if mode=='foreign_scope' else 'scope')
    if mode=='different_page':
        other=base/'map';other.mkdir();save(other,[dict(event='map_observed',scene='MAP',utc='2026-11-17T10:01:00+00:00')])
    index=diagnostic_index((base,));projection=index[old]
    assert projection['turn_answers']=={'frame-0004':'frame-0005'}
    assert {'frame-0002','frame-0003'}<=projection['superseded']
    assert {'frame-0004','frame-0005'}.issubset(projection['superseded'])==(mode=='same_visit')
