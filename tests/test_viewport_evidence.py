"""Native view diagnostics retire only after same-container fresh reads."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus.viewport_evidence import diagnostic_index
from maalimbus import capture_retention as retention,workspace


def recorder(base,name,*,scope='scope',start=0,views=4):
    run=base/name;run.mkdir(parents=True)
    rows=[dict(event='mirror_loop_start',run_scope=scope)]
    for i in range(views):
        stem=f'frame-{i+1:04d}';at=f'2026-11-17T10:{start:02d}:{i*2:02d}+00:00'
        image=np.random.default_rng(i).integers(0,256,(1080,1920,3),dtype=np.uint8)
        png=run/(stem+'.png');cv2.imwrite(str(png),image)
        data=dict(frame=stem,scene='MAP',size=[1920,1080],utc=at,
            image_sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
            ocr=[dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
                 dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)])
        (run/(stem+'.json')).write_text(json.dumps(data))
        rows.append(dict(event='map_observed',scene='MAP',frame=stem,utc=at))
        if i<views-1:
            rows.append(dict(event='map_view_intent',kind='drag',frame=stem,image_sha256=data['image_sha256'],
                utc=f'2026-11-17T10:{start:02d}:{i*2+1:02d}+00:00',input_sent=False))
    rows.append(dict(event='mirror_loop_stopped',passed=False))
    save(run,rows);return run,rows


def save(run,rows):
    (run/'events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))


def test_old_view_read_retires_but_two_latest_pairs_remain(tmp_path):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'views')
    rows.insert(2,dict(event='map_view_probe',input_sent=False));save(run,rows)
    index=diagnostic_index((base,));p=index[run]
    assert p['superseded']=={'frame-0001'}
    assert p['required']=={'frame-0002','frame-0003','frame-0004'}
    eligible={p.stem for p,_ in retention._run_rows(run,True,2,viewport_index=index)}
    assert 'frame-0001' in eligible and not p['required']&eligible


@pytest.mark.parametrize('start',['absent',None,'foreign'])
def test_scope_producer_absence_differs_from_null_or_conflict(tmp_path,start):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'legacy')
    if start=='absent':rows[0].pop('run_scope')
    else:rows[0]['run_scope']=start
    rows.insert(1,dict(event='semantic_frame_proposal',episode='scope'));save(run,rows)
    retired=diagnostic_index((base,)).get(run,{}).get('superseded',set())
    assert retired==({'frame-0001'} if start=='absent' else set())


@pytest.mark.parametrize('fault',['missing_header','missing_png','changed_png','wrong_hash',
    'stale_after','unknown_after','foreign_header','unknown_input','invalid_scope','unanswered'])
def test_unproven_view_read_preserves_original_diagnostic(tmp_path,fault):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'views')
    p=run/'frame-0002.json';data=json.loads(p.read_text())
    if fault=='missing_header':data['ocr'].pop()
    elif fault=='missing_png':p.with_suffix('.png').unlink()
    elif fault=='changed_png':p.with_suffix('.png').write_bytes(b'changed')
    elif fault=='wrong_hash':rows[2]['image_sha256']='different'
    elif fault=='stale_after':data['utc']='2026-11-17T09:59:00+00:00'
    elif fault=='unknown_after':rows[3]['scene']='UNKNOWN'
    elif fault=='foreign_header':data['ocr'][0]['text']='Exploring Floor 4'
    elif fault=='unknown_input':rows.insert(3,dict(event='unknown_exploration_intent'))
    elif fault=='invalid_scope':rows[0]['run_scope']=[]
    elif fault=='unanswered':rows[3:]=[dict(event='mirror_loop_stopped',passed=False)]
    p.write_text(json.dumps(data));save(run,rows)
    index=diagnostic_index((base,))
    assert 'frame-0001' not in index.get(run,{}).get('superseded',set())


@pytest.mark.parametrize('scope',['scope','foreign'])
def test_scope_continues_across_recorders_without_creating_a_permanent_tail(tmp_path,scope):
    base=tmp_path/'evidence/runtime';old,_=recorder(base,'old',views=2)
    recorder(base,'new',scope=scope,start=1,views=3)
    index=diagnostic_index((base,))
    assert index.get(old,{}).get('superseded',set())==({'frame-0001','frame-0002'} if scope=='scope' else set())


def test_business_or_review_reference_keeps_its_original_even_under_pressure(tmp_path,monkeypatch):
    base=tmp_path/'evidence/runtime';run,_=recorder(base,'views')
    monkeypatch.setattr(retention,'_reference_keep',lambda root:{run/'frame-0001.png'})
    plan=retention.plan(tmp_path,run,20_001,budget=workspace.size(tmp_path)+20_000,recent=2)
    assert not plan['files'] and not plan['sufficient']


def test_another_domain_required_checkpoint_overrides_view_supersession(tmp_path):
    base=tmp_path/'evidence/runtime';run,_=recorder(base,'views')
    view=diagnostic_index((base,))
    hud={run:dict(required={'frame-0001'},superseded=set(),bootstrap=set())}
    eligible={p.stem for p,_ in retention._run_rows(run,True,2,hud_index=hud,viewport_index=view)}
    assert 'frame-0001' not in eligible


@pytest.mark.parametrize('scope',['next-logical-run',[]])
def test_changed_or_malformed_episode_never_inherits_launch_scope(tmp_path,scope):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'views')
    rows.insert(2,dict(event='semantic_frame_proposal',episode=scope));save(run,rows)
    assert run not in diagnostic_index((base,))


def test_a_later_recorder_does_not_retire_an_unanswered_old_view_intent(tmp_path):
    base=tmp_path/'evidence/runtime';old,rows=recorder(base,'old')
    last=rows[-2];rows.insert(-1,dict(event='map_view_intent',kind='drag',frame=last['frame'],
        utc='2026-11-17T10:00:07+00:00'));save(old,rows)
    recorder(base,'new',start=1,views=3)
    index=diagnostic_index((base,))
    assert 'frame-0004' in index[old]['required']
    assert 'frame-0004' not in index[old]['superseded']
    eligible={p.stem for p,_ in retention._run_rows(old,False,2,viewport_index=index)}
    assert 'frame-0004' not in eligible


def test_two_newer_native_map_reads_replace_answered_gesture_diagnostics(tmp_path):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'views',views=6)
    rows=[row for row in rows if not (row.get('event')=='map_view_intent' and row['frame'] in ('frame-0004','frame-0005'))]
    save(run,rows);index=diagnostic_index((base,))
    assert index[run]['required']=={'frame-0005','frame-0006'}
    assert {'frame-0001','frame-0002','frame-0003','frame-0004'}<=index[run]['superseded']
