"""Production verdict.frame is the original input; later observation is separate."""
import hashlib,json
import cv2,numpy as np,pytest
from maalimbus import capture_retention as r


def chain(tmp_path):
    run=tmp_path/'evidence/runtime/map';run.mkdir(parents=True)
    rows=[dict(event='mirror_loop_start',run_scope='scope')]
    for i in range(1,6):
        stem=f'frame-{i:04d}';utc=f'2026-11-17T10:00:{2*i:02d}+00:00'
        png=run/(stem+'.png');cv2.imwrite(str(png),np.full((1080,1920,3),i,np.uint8))
        record=dict(frame=stem,scene='MAP',size=[1920,1080],utc=utc,
            image_sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
            ocr=[dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
                 dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)])
        (run/(stem+'.json')).write_text(json.dumps(record))
        rows.append(dict(event='map_observed',scene='MAP',frame=stem,utc=utc))
        if i>1:rows.append(dict(event='map_click_result',frame=f'frame-{i-1:04d}',
            after_frame=stem,target=[1000,400,50,50],outcome='rejected',page='MAP',
            utc=f'2026-11-17T10:00:{2*i:02d}.5+00:00'))
        if i<5:rows.append(dict(event='window_intent',page='MAP',target=[1000,400,50,50],
            point=[1025,425],delay_ms=500,utc=f'2026-11-17T10:00:{2*i+1:02d}+00:00'))
    rows.append(dict(event='mirror_loop_stopped',passed=False))
    return run,rows


def save(run,rows):(run/'events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))


def test_older_native_map_verdicts_answer_storage_inside_an_active_session(tmp_path):
    run,rows=chain(tmp_path);save(run,rows)
    assert r._settled_map_inputs(run,rows)=={'frame-0001','frame-0002','frame-0003','frame-0004'}
    eligible={p.stem for p,_ in r._run_rows(run,True,2)}
    assert 'frame-0002' in eligible
    assert 'frame-0003' in eligible
    assert not {'frame-0004','frame-0005'}&eligible
    closed={p.stem for p,_ in r._run_rows(run,False,2)}
    assert 'frame-0004' in closed and 'frame-0005' not in closed


@pytest.mark.parametrize('start',['absent',None,'foreign'])
def test_legacy_start_uses_explicit_episode_but_null_and_conflict_stay_pinned(tmp_path,start):
    run,rows=chain(tmp_path)
    if start=='absent':rows[0].pop('run_scope')
    else:rows[0]['run_scope']=start
    rows.insert(1,dict(event='semantic_frame_proposal',episode='scope'))
    save(run,rows)
    assert bool(r._settled_map_inputs(run,rows))==(start=='absent')


@pytest.mark.parametrize('fault',['changed_image','missing_header','different_floor','unknown_input',
    'unjudged','wrong_target','out_of_box','stale_capture','foreign_scope'])
def test_a_bad_or_interrupted_verdict_cannot_answer_its_input(tmp_path,fault):
    run,rows=chain(tmp_path);p=run/'frame-0002.json';data=json.loads(p.read_text())
    intent=rows[2];result=rows[4]
    if fault=='changed_image':p.with_suffix('.png').write_bytes(b'changed')
    elif fault=='missing_header':data['ocr'].pop()
    elif fault=='different_floor':data['ocr'][0]['text']='Exploring Floor 4'
    elif fault=='unknown_input':rows.insert(3,dict(event='unknown_exploration_intent'))
    elif fault=='unjudged':result['outcome']='unjudged'
    elif fault=='wrong_target':result['target']=[1100,400,50,50]
    elif fault=='out_of_box':intent['point']=[0,0]
    elif fault=='stale_capture':data['utc']='2026-11-17T10:00:02.5+00:00'
    elif fault=='foreign_scope':rows.insert(1,dict(event='semantic_frame_proposal',episode='foreign'))
    p.write_text(json.dumps(data));save(run,rows)
    assert 'frame-0001' not in r._settled_map_inputs(run,rows)


def accepted_chain(tmp_path,contract):
    run=tmp_path/'evidence/runtime/active';run.mkdir(parents=True)
    rows=[dict(event='mirror_loop_start',run_scope='scope')]
    for i in range(1,7):
        name=f'frame-{i:04d}';second=2*i;utc=f'2026-11-17T10:00:{second:02d}+00:00'
        scene='MAP' if i%2 else 'NODE_PREVIEW'
        picture=run/(name+'.png');cv2.imwrite(str(picture),np.full((1080,1920,3),i,np.uint8))
        record=dict(frame=name,scene=scene,size=[1920,1080],utc=utc,
            image_sha256=hashlib.sha256(picture.read_bytes()).hexdigest(),
            ocr=[dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
                 dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)] if scene=='MAP'
                else [dict(text='Enter',box=[1670,780,122,61],score=.99)])
        picture.with_suffix('.json').write_text(json.dumps(record))
        rows.append(dict(event='map_observed',frame=name,scene=scene,utc=utc))
        if scene=='MAP':
            intent=dict(event='window_intent',page='MAP',target=[1000,400,50,50],
                point=[1025,425],delay_ms=500,utc=f'2026-11-17T10:00:{second+1:02d}+00:00')
            if contract is not None:intent['expect']=contract
            rows.append(intent)
        else:rows.append(dict(event='map_click_result',frame=f'frame-{i-1:04d}',
            after_frame=name,after_image_sha256=record['image_sha256'],target=[1000,400,50,50],
            outcome='accepted',page='NODE_PREVIEW',utc=f'2026-11-17T10:00:{second:02d}.5+00:00'))
    save(run,rows);return run,rows


def test_original_preview_contract_closes_older_navigation_inside_active_session(tmp_path):
    run,rows=accepted_chain(tmp_path,['NODE_PANEL','NODE_PREVIEW','UNKNOWN'])
    assert r._settled_map_inputs(run,rows)=={'frame-0001'}
    eligible={p.stem for p,_ in r._run_rows(run,True,2)}
    assert 'frame-0001' in eligible
    assert not {'frame-0003','frame-0005','frame-0006'}&eligible
    assert all((run/(f'frame-{i:04d}.json')).exists() for i in range(1,7))


@pytest.mark.parametrize('contract',[None,['NODE_PANEL','UNKNOWN'],[],['NODE_PREVIEW',None],
                                     ['NODE_PREVIEW','NODE_PREVIEW']])
def test_preview_cannot_widen_absent_narrow_or_invalid_original_contract(tmp_path,contract):
    run,rows=accepted_chain(tmp_path,contract)
    assert r._settled_map_inputs(run,rows)==set()
    assert 'frame-0001' not in {p.stem for p,_ in r._run_rows(run,True,2)}
