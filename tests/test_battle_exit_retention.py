"""Closing a battle container answers diagnostics, not victory or payout."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from test_hud_evidence import recorder,save
from maalimbus.hud_evidence import diagnostic_index
from maalimbus import capture_retention as retention,workspace


@pytest.mark.parametrize('fault',[None,'missing_pack','changed_image','stale_capture','unknown_input'])
def test_native_map_exit_closes_read_diagnostics_but_keeps_its_final_pair(tmp_path,fault):
    base=tmp_path/'evidence/runtime';run,rows=recorder(base,'battle',0);rows.pop()
    next(r for r in reversed(rows) if r['event']=='window_intent')['reason']='start_button_submits_the_assigned_turn'
    p=run/'frame-0006.json';image=np.full((1080,1920,3),6,np.uint8);cv2.imwrite(str(p.with_suffix('.png')),image)
    data=dict(frame=p.stem,scene='MAP',size=[1920,1080],utc='2026-11-17T10:00:12+00:00',
        image_sha256=hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest(),
        ocr=[dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
             dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)])
    if fault=='missing_pack':data['ocr'].pop()
    if fault=='stale_capture':data['utc']='2026-11-17T10:00:01+00:00'
    p.write_text(json.dumps(data))
    if fault=='changed_image':p.with_suffix('.png').write_bytes(b'changed')
    if fault=='unknown_input':rows.append(dict(event='window_intent',page='BATTLE_HUD',reason='unknown_ego_input'))
    rows.append(dict(event='map_observed',scene='MAP',frame=p.stem,utc='2026-11-17T10:00:13+00:00'))
    rows.append(dict(event='mirror_loop_stopped',passed=False));save(run,rows)
    projection=diagnostic_index((base,)).get(run,{})
    assert projection.get('required',set())==({'frame-0004','frame-0006'} if fault is None else set())
    if fault is None:
        eligible={p.stem for p,_ in retention._run_rows(run,True,2,hud_index={run:projection})}
        assert {'frame-0002','frame-0003'}<=eligible
        assert not {'frame-0004','frame-0006'}&eligible


def pair_plan(tmp_path,monkeypatch):
    base=tmp_path/'evidence/runtime';old,_=recorder(base,'old',0);new,_=recorder(base,'new',2)
    protected={p for run in (old,new) for p in run.glob('frame-*.*') if not (run==old and p.stem in ('frame-0002','frame-0003'))}
    monkeypatch.setattr(retention,'_reference_keep',lambda root:protected)
    used=workspace.size(tmp_path)
    # One PNG would satisfy the deficit. The causal pair still retires together.
    additional=(old/'frame-0002.png').stat().st_size-13_288
    plan=retention.plan(tmp_path,new,additional,budget=used,recent=2)
    return old,new,protected,plan


def test_pressure_selects_the_whole_eligible_pair_not_only_its_first_witness(tmp_path,monkeypatch):
    old,new,_,plan=pair_plan(tmp_path,monkeypatch)
    assert plan['sufficient']
    assert {Path(r['path']).stem for r in plan['files']}=={'frame-0002','frame-0003'}


@pytest.mark.parametrize('fault',[None,'new_reference','changed_record'])
def test_interrupted_retirement_has_durable_remaining_intents_not_game_evidence(tmp_path,monkeypatch,fault):
    old,new,protected,_=pair_plan(tmp_path,monkeypatch)
    used=workspace.size(tmp_path)
    plan=retention.plan(tmp_path,new,25_000,budget=used+20_000,recent=2)
    assert len(plan['files'])==2
    # A reclaimed frame is moved to the archive beside the project, not unlinked, so the
    # interruption is injected where the frame leaves the project.
    retire=retention.retire_capture
    def interrupted(png,*args,**kwargs):
        if png==old/'frame-0003.png':raise OSError('injected interruption after first retirement')
        return retire(png,*args,**kwargs)
    monkeypatch.setattr(retention,'retire_capture',interrupted)
    with pytest.raises(OSError):retention.apply(tmp_path,new,plan)
    monkeypatch.setattr(retention,'retire_capture',retire)
    assert not (old/'frame-0002.png').exists() and (old/'frame-0003.png').exists()
    archive=tmp_path.parent/(tmp_path.name+retention.ARCHIVE_SUFFIX)
    assert (archive/(old/'frame-0002.png').relative_to(tmp_path)).is_file()
    if fault=='new_reference':protected.add(old/'frame-0003.png')
    if fault=='changed_record':
        p=old/'frame-0003.json';d=json.loads(p.read_text());d['new']='changed';p.write_text(json.dumps(d))
    resumed=retention.plan(tmp_path,new,20_001,budget=workspace.size(tmp_path)+20_000,recent=2)
    if fault:
        assert not resumed['sufficient'] and not resumed['files']
    else:
        assert resumed['sufficient'] and len(resumed['files'])==1
        retention.apply(tmp_path,new,resumed)
        assert not (old/'frame-0003.png').exists()
        assert (old/'frame-0002.json').exists() and (old/'frame-0003.json').exists()
