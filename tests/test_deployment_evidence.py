"""A domain-settled count increment can bound diagnostic images, not spending."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maalimbus.deployment_evidence import selection_commit,validate_commit,diagnostic_index
from maalimbus import capture_retention as retention,workspace


def frame(root,n,picked):
    p=root/f'frame-{n:04}.json'
    image=np.full((1080,1920,3),n,np.uint8)
    image[:128,:128]=np.random.default_rng(n).integers(0,256,(128,128,3),dtype=np.uint8)
    cv2.imwrite(str(p.with_suffix('.png')),image)
    d=dict(scene='PRE_BATTLE_TEAM',size=[1920,1080],frame=p.stem,
           image_sha256=hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest(),
           ocr=[dict(text=f'{picked}/12',score=.99,box=[1610,745,250,80])])
    p.write_text(json.dumps(d));return p


def test_real_native_increment_binds_originals_without_input_or_state_write():
    root=Path(__file__).resolve().parents[1];r=root/'evidence/runtime/packaged-mirror-20261117-073927'
    before,after=r/'frame-0006.json',r/'frame-0007.json'
    if not before.exists():pytest.skip('local real selection corpus absent')
    prior={p:p.read_bytes() for p in (before,after,before.with_suffix('.png'),after.with_suffix('.png'))}
    commit=selection_commit(before,after,'isolated-scope',[3,4,9,1,7,2,12,5,8,10,11,6],[3])
    assert commit['count_before']==[0,12] and commit['count_after']==[1,12]
    assert validate_commit(commit,r)==commit and all(p.read_bytes()==b for p,b in prior.items())


@pytest.mark.parametrize('fault',['jump','wrong_prefix','boolean','rewritten_hash','wrong_page','foreign_path'])
def test_unproven_or_changed_selection_cannot_be_a_retention_commit(tmp_path,fault):
    a=frame(tmp_path,1,0);b=frame(tmp_path,2,2 if fault=='jump' else 1)
    if fault in ('jump','wrong_prefix','boolean'):
        sequence={'jump':[3],'wrong_prefix':[4],'boolean':[True]}[fault]
        with pytest.raises(ValueError):selection_commit(a,b,'scope',[3,4],sequence)
        return
    c=selection_commit(a,b,'scope',[3,4],[3])
    if fault=='rewritten_hash':c['after']['png_sha256']='0'*64
    elif fault=='foreign_path':c['after']['record']='../frame-0002.json'
    else:
        d=json.loads(b.read_text());d['scene']='SHOP_PURCHASE';b.write_text(json.dumps(d))
    with pytest.raises(ValueError):validate_commit(c,tmp_path)


def test_pressure_preserves_two_latest_commits_pending_reference_and_all_json(tmp_path):
    r=tmp_path/'evidence/runtime/current';r.mkdir(parents=True);rows=[];commits=[]
    for k in range(4):
        a=frame(r,2*k+1,k);b=frame(r,2*k+2,k+1)
        c=selection_commit(a,b,'scope',list(range(1,13)),list(range(1,k+2)));commits.append(c)
        rows += [dict(event='map_observed',frame=a.stem,scene='PRE_BATTLE_TEAM'),
            dict(event='window_intent',page='PRE_BATTLE_TEAM',reason='team_card_joins_the_next_unpicked_identity'),
            dict(event='map_observed',frame=b.stem,scene='PRE_BATTLE_TEAM'),
            dict(event='deployment_selection_committed',commit=c,input_sent=False)]
    (r/'events.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    assert retention._older_selection_diagnostics(r,rows)=={'frame-0001','frame-0002','frame-0003','frame-0004'}
    config=tmp_path/'config';config.mkdir();(config/'pending.json').write_text(json.dumps(dict(pending=str(r/'frame-0003.json'))))
    original={p:p.read_bytes() for p in r.glob('*.json')}
    # The unlink trail itself needs pre-existing headroom; the next capture
    # allocation creates pressure, rather than starting above the hard cap.
    result=retention.plan(tmp_path,r,30000,recent=2,budget=workspace.size(tmp_path)+20000)
    assert result['sufficient']
    removed={Path(x['path']).name for x in result['files']}
    assert 'frame-0002.png' in removed and 'frame-0003.png' not in removed
    assert not removed.intersection(f'frame-{n:04}.png' for n in (1,5,6,7,8))
    assert all(p.read_bytes()==b for p,b in original.items())
    damaged=deepcopy(rows);damaged[-1]['commit']['after']['png_sha256']='0'*64
    # The corrupt receipt never authorizes its own pair; two latest valid
    # receipts remain. An independently valid earlier commit is still valid.
    assert retention._older_selection_diagnostics(r,damaged)=={'frame-0001','frame-0002'}
    retention.apply(tmp_path,r,result)
    assert all(p.read_bytes()==b for p,b in original.items())
    a=frame(r,9,4);b=frame(r,10,5)
    rows.append(dict(event='deployment_selection_committed',commit=selection_commit(
        a,b,'scope',list(range(1,13)),list(range(1,6)))))
    eligible=retention._older_selection_diagnostics(r,rows)
    assert {'frame-0005','frame-0006'}<=eligible
    assert not eligible.intersection(f'frame-{n:04}' for n in (7,8,9,10))


def recorder(base,name,start,end,minute,*,scope='scope'):
    r=base/name;r.mkdir(parents=True);first=frame(r,1,start);rows=[dict(event='map_observed',frame=first.stem,
        scene='PRE_BATTLE_TEAM',utc=f'2026-11-17T10:{minute:02}:00+00:00',input_sent=False)]
    for k in range(start,end):
        n=2+2*(k-start);a=frame(r,n,k);b=frame(r,n+1,k+1)
        stamp=lambda sec:f'2026-11-17T10:{minute:02}:{sec:02}+00:00'
        rows += [dict(event='map_observed',frame=a.stem,scene='PRE_BATTLE_TEAM',utc=stamp(n),input_sent=False),
            dict(event='window_intent',page='PRE_BATTLE_TEAM',reason='team_card_joins_the_next_unpicked_identity',utc=stamp(n)),
            dict(event='map_observed',frame=b.stem,scene='PRE_BATTLE_TEAM',utc=stamp(n+1),input_sent=False),
            dict(event='deployment_selection_committed',utc=stamp(n+1),commit=selection_commit(
                a,b,scope,list(range(1,13)),list(range(1,k+2))),input_sent=False)]
    rows.append(dict(event='mirror_loop_stopped',utc=f'2026-11-17T10:{minute:02}:59+00:00'))
    (r/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in rows)+'\n');return r,rows


@pytest.mark.parametrize('barrier',[None,'foreign_scope','battle','reset'])
def test_cross_recorder_projection_follows_scope_and_native_page_barriers(tmp_path,barrier):
    base=tmp_path/'evidence/runtime';old,rows=recorder(base,'old',0,3,0)
    new,_=recorder(base,'new',3,5,2,scope='other' if barrier=='foreign_scope' else 'scope')
    if barrier in ('battle','reset'):
        rows.append(dict(event='map_observed',frame='frame-0007',utc='2026-11-17T10:01:00+00:00',
                         scene='BATTLE_HUD' if barrier=='battle' else 'DEPLOYMENT_RESET'))
        (old/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in rows)+'\n')
    index=diagnostic_index((base,))
    if barrier:
        assert not index[old]['superseded'] and not index[old]['bootstrap']
    else:
        assert {'frame-0006','frame-0007'}<=index[old]['superseded']
        assert index[old]['bootstrap']=={'frame-0001'}
        eligible={p.stem for p,r in retention._run_rows(old,False,2,index)}
        assert {'frame-0001','frame-0006','frame-0007'}<=eligible
        config=tmp_path/'config';config.mkdir();(config/'pending.json').write_text(json.dumps(dict(pending=str(old/'frame-0006.json'))))
        result=retention.plan(tmp_path,new,50000,recent=2,budget=workspace.size(tmp_path)+20000)
        assert not {str(old/'frame-0006.png'),str(old/'frame-0007.png')}.intersection(
            str(tmp_path/row['path']) for row in result['files'])


@pytest.mark.parametrize('fault',[None,'intent','explicit_stop','foreign','no_newer_read'])
def test_only_closed_input_free_capacity_previews_can_follow_newer_same_checkpoint(tmp_path,fault):
    base=tmp_path/'evidence/runtime';recorder(base,'committed',0,2,0)
    def preview(name,minute,*,closed):
        r=base/name;r.mkdir();rows=[dict(event='mirror_loop_start',run_scope='other' if fault=='foreign' else 'scope')]
        for n in (1,2):
            p=frame(r,n,2);rows.append(dict(event='map_observed',frame=p.stem,scene='PRE_BATTLE_TEAM',
                input_sent=False,utc=f'2026-11-17T10:{minute:02}:{n:02}+00:00'))
        if closed:rows.append(dict(event='mirror_loop_stopped',clicks_sent=0,reason='evidence_capacity_unavailable_before_input'))
        if fault=='intent' and closed:rows.insert(1,dict(event='flow_intent'))
        if fault=='explicit_stop' and closed:rows[0]['stop_page']='PRE_BATTLE_TEAM'
        (r/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in rows)+'\n');return r
    old=preview('failed-readonly',2,closed=True)
    if fault!='no_newer_read':preview('current',3,closed=False)
    index=diagnostic_index((base,));found=index.get(old,{}).get('previews',set())
    assert found==({'frame-0001','frame-0002'} if fault is None else set())
    if fault is None:
        eligible={p.stem for p,r in retention._run_rows(old,False,2,index)}
        assert eligible=={'frame-0001','frame-0002'}


@pytest.mark.parametrize('fault',[None,'incomplete','foreign','changed_hud','missing_hud_anchors','other_input','wrong_submit'])
def test_native_battle_successor_closes_only_the_complete_selection_diagnostics(tmp_path,fault):
    base=tmp_path/'evidence/runtime'
    r,rows=recorder(base,'submitted',9 if fault=='incomplete' else 10,11 if fault=='incomplete' else 12,0)
    rows.pop()
    rows.insert(0,dict(event='mirror_loop_start',run_scope='foreign' if fault=='foreign' else 'scope'))
    before=frame(r,6,11 if fault=='incomplete' else 12)
    hud=frame(r,7,12);record=json.loads(hud.read_text());record['scene']='BATTLE_HUD'
    record['ocr']=[dict(text='WAVE',box=[20,30,60,30],score=.99),dict(text='TURN',box=[20,90,60,30],score=.99)]
    if fault=='missing_hud_anchors':record['ocr']=[]
    hud.write_text(json.dumps(record))
    if fault=='changed_hud':hud.with_suffix('.png').write_bytes(b'changed')
    rows += [dict(event='map_observed',frame=before.stem,scene='PRE_BATTLE_TEAM',utc='2026-11-17T10:00:10+00:00'),
             dict(event='window_intent',page='PRE_BATTLE_TEAM',reason='other' if fault=='wrong_submit' else 'battle_button_submits_the_team')]
    if fault=='other_input':rows.append(dict(event='flow_intent'))
    rows += [dict(event='map_observed',frame=hud.stem,scene='BATTLE_HUD',utc='2026-11-17T10:00:12+00:00'),
             dict(event='mirror_loop_stopped')]
    (r/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in rows)+'\n')
    original={p:p.read_bytes() for p in r.glob('*.json')}
    index=diagnostic_index((base,));superseded=index[r]['superseded']
    assert bool(superseded)==(fault is None)
    if fault is None:
        eligible={p.stem for p,_ in retention._run_rows(r,False,2,index)}
        assert {'frame-0001','frame-0002','frame-0003','frame-0004','frame-0005'}<=eligible
        assert not {'frame-0006','frame-0007'}.intersection(eligible)
        (tmp_path/'config').mkdir()
        (tmp_path/'config/pending.json').write_text(json.dumps(dict(proof=str(r/'frame-0004.json'))))
        plan=retention.plan(tmp_path,r,30000,recent=2,budget=workspace.size(tmp_path)+20000)
        assert not {str(r/'frame-0004.png'),str(r/'frame-0005.png')}.intersection(
            str(tmp_path/x['path']) for x in plan['files'])
    assert all(p.read_bytes()==value for p,value in original.items())


@pytest.mark.parametrize('fault',[None,'foreign','page_boundary','turn','input','stop_page','changed','no_newer'])
def test_input_free_hud_capacity_snapshots_follow_same_native_page_visit_only(tmp_path,fault):
    base=tmp_path/'evidence/runtime';base.mkdir(parents=True)
    def hud_run(name,minute,closed):
        r=base/name;r.mkdir();rows=[dict(event='mirror_loop_start',run_scope='other' if not closed and fault=='foreign' else 'scope')]
        for n in (1,2):
            p=frame(r,n,12);record=json.loads(p.read_text());record['scene']='BATTLE_HUD'
            record['ocr']=[dict(text='WAVE',box=[20,30,60,30],score=.99),dict(text='TURN',box=[20,90,60,30],score=.99),
                           dict(text='2' if not closed and fault=='turn' else '1',box=[80,90,35,30],score=.99)]
            p.write_text(json.dumps(record));rows.append(dict(event='map_observed' if n==1 else 'battle_observed',frame=p.stem,scene='BATTLE_HUD',
                utc=f'2026-11-17T10:{minute:02}:{n:02}+00:00',input_sent=False))
            if n==2:rows[-1].pop('input_sent')  # native battle observer has no input-sent field
            if closed and fault=='changed':p.with_suffix('.png').write_bytes(b'changed')
        if closed:
            if fault=='input':rows.insert(1,dict(event='flow_intent'))
            if fault=='stop_page':rows[0]['stop_page']='BATTLE_HUD'
            rows.append(dict(event='mirror_loop_stopped',clicks_sent=0,reason='evidence_capacity_unavailable_before_input'))
        (r/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in rows)+'\n');return r
    old=hud_run('old',0,True)
    if fault=='page_boundary':
        mid=base/'different-page';mid.mkdir();(mid/'events.jsonl').write_text(json.dumps(dict(
            event='map_observed',frame='frame-0001',scene='PRE_BATTLE_TEAM',utc='2026-11-17T10:01:00+00:00'))+'\n')
    if fault!='no_newer':hud_run('new',2,False)
    index=diagnostic_index((base,));eligible=index.get(old,{}).get('previews',set())
    assert eligible==({'frame-0001','frame-0002'} if fault is None else set())
