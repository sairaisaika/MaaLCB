"""Discarded read-only plans never become stale physical inputs or receipts."""
import hashlib
import json
import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

from maalimbus import capture_retention as retention
from maalimbus.runner import MirrorRunner,FakeDevice

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))


def write_frame(run,index,scene='DRIVE'):
    run.mkdir(parents=True,exist_ok=True);name=f'frame-{index:04d}'
    png=run/(name+'.png');cv2.imwrite(str(png),np.full((1080,1920,3),index,np.uint8))
    data=dict(frame=name,scene=scene,size=[1920,1080],utc=f'2026-11-18T10:00:{index*2:02d}+00:00',
        image_sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
        ocr=[dict(text='Drive',score=.99,box=[1430,950,100,35])])
    path=png.with_suffix('.json');path.write_text(json.dumps(data));return path,data


def proposal(tmp_path):
    run=tmp_path/'evidence/runtime/current';rows=[dict(event='mirror_loop_start',run_scope='scope')]
    for i in range(1,3):
        path,data=write_frame(run,i)
        rows.append(dict(event='map_observed',frame=path.stem,scene=data['scene'],
                         image_sha256=data['image_sha256'],utc=data['utc']))
    facts=dict(kind='plan',before_frame=path.relative_to(tmp_path).as_posix(),
               before_json_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               before_image_sha256=data['image_sha256'],capacity_sequence=7,input_sent=False)
    rows.append(dict(event='evidence_capacity_admitted',storage_maintenance=True,**facts))
    rows.append(dict(event='capacity_plan_discarded',utc='2026-11-18T10:00:05+00:00',**facts))
    return run,rows,path


def save(run,rows):(run/'events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))


def test_only_explicit_discarded_duplicate_can_override_a_diagnostic_tail(tmp_path):
    run,rows,path=proposal(tmp_path);save(run,rows)
    assert retention._discarded_capacity_plans(run,rows)=={path.stem}
    originals={p:p.read_bytes() for p in run.glob('*.json')}
    journal=(run/'events.jsonl').read_bytes()
    assert retention.prune_discarded_plan(run,rows[-1]['before_frame'])>0
    assert not path.with_suffix('.png').exists() and (run/'frame-0001.png').exists()
    assert all(p.read_bytes()==body for p,body in originals.items())
    assert (run/'events.jsonl').read_bytes()==journal


@pytest.mark.parametrize('fault',['no_admission','not_maintenance','wrong_json_hash','wrong_image_hash',
    'bad_sequence','foreign_recorder','unknown_page','different_size','actual_input',
    'intervening_input','sent_true','changed_picture','no_prior_representative'])
def test_incomplete_or_owned_proposal_keeps_its_image(tmp_path,fault):
    run,rows,path=proposal(tmp_path)
    if fault=='no_admission':rows.pop(-2)
    elif fault=='not_maintenance':rows[-2]['storage_maintenance']=False
    elif fault=='wrong_json_hash':rows[-1]['before_json_sha256']='0'*64
    elif fault=='wrong_image_hash':rows[-1]['before_image_sha256']='0'*64
    elif fault=='bad_sequence':
        rows[-1]['capacity_sequence']=None;rows[-2]['capacity_sequence']=None
    elif fault=='foreign_recorder':
        for row in rows[-2:]:row['before_frame']='evidence/runtime/foreign/'+path.name
    elif fault=='unknown_page':
        data=json.loads(path.read_bytes());data['scene']='UNKNOWN';path.write_text(json.dumps(data))
    elif fault=='different_size':
        data=json.loads((run/'frame-0001.json').read_bytes());data['size']=[1,1]
        (run/'frame-0001.json').write_text(json.dumps(data))
    elif fault=='actual_input':rows.append(dict(event='window_intent',frame=path.stem))
    elif fault=='intervening_input':rows.insert(2,dict(event='unknown_exploration_intent'))
    elif fault=='sent_true':rows[-1]['input_sent']=True
    elif fault=='changed_picture':path.with_suffix('.png').write_bytes(b'changed')
    elif fault=='no_prior_representative':rows.pop(1)
    save(run,rows)
    assert not retention._discarded_capacity_plans(run,rows)
    if fault=='foreign_recorder':
        with pytest.raises(ValueError,match='another recorder'):
            retention.prune_discarded_plan(run,rows[-1]['before_frame'])
    else:assert retention.prune_discarded_plan(run,rows[-1].get('before_frame',str(path)))==0
    assert path.with_suffix('.png').exists()


@pytest.mark.parametrize('owner',['pending','review','source','domain'])
def test_pending_review_source_or_domain_requirement_overrides_proposal_disposal(tmp_path,monkeypatch,owner):
    run,rows,path=proposal(tmp_path);save(run,rows)
    if owner=='domain':
        from maalimbus import deployment_evidence
        monkeypatch.setattr(deployment_evidence,'diagnostic_index',lambda *a:{
            run:dict(required={path.stem},causal_pairs=set())})
    else:
        state=tmp_path/({'pending':'config/pending.json','review':'build/learning-review/frames/r/proposal.json',
                         'source':'tests/consumer.py'}[owner]);state.parent.mkdir(parents=True)
        state.write_text('FRAME='+repr(path.relative_to(tmp_path).as_posix()) if owner=='source'
                         else json.dumps({'pending':True,'frame':str(path)}))
    assert retention.prune_discarded_plan(run,rows[-1]['before_frame'])==0
    assert path.with_suffix('.png').exists()


class Notes:
    def __init__(self):self.events=[]
    def record(self,event,**details):self.events.append((event,details))


def test_native_journal_correlates_reads_actions_and_retries(tmp_path):
    import recognition

    journal = recognition.Journal(tmp_path)
    journal.record('preflight_passed')
    journal.begin_step()
    journal.record('map_observed', frame='frame-0001')
    journal.record('capacity_plan_discarded', input_sent=False)
    journal.begin_step()
    journal.record('map_observed', frame='frame-0002')
    journal.record('window_intent')
    journal.record('step_observation', phase='settle', frame='frame-0003')
    journal.end_step()
    journal.record('mirror_loop_stopped')
    rows = [json.loads(row) for row in (tmp_path/'events.jsonl').read_text().splitlines()]
    assert [row.get('step_attempt') for row in rows] == [None,1,1,2,2,2,None]


def instance(tmp_path,monkeypatch,*,always=False):
    notes=Notes();device=FakeDevice([]);run=tmp_path/'runner'
    loop=MirrorRunner(device,settings={'interval':0.0,'rounds':1,'page_tries':2},directory=run,journal=notes)
    seen=[]
    def observe(**kwargs):
        n=len(seen)+1;path,data=write_frame(run,n,'HOME')
        data['ocr'][0]['box']=[1430 if n==1 else 1520,950,60,35]
        # HOME uses its registered native control, not a free OCR caption.
        # Model the observer publishing the current control projection too.
        loop.controls['home.drive_button']=data['ocr'][0]['box']
        path.write_text(json.dumps(data));seen.append(data)
        return data
    monkeypatch.setattr(loop,'_observe',observe)
    def admit(*args):
        if always or len(seen)==1:
            path=run/(seen[-1]['frame']+'.json')
            return dict(storage_maintenance=True,before_frame=str(path),
                before_json_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                before_image_sha256=seen[-1]['image_sha256'],capacity_sequence=len(seen))
        return None
    monkeypatch.setattr(loop,'_admit_capacity',admit)
    return loop,device,notes,seen


def test_real_loop_reobserves_before_any_intent_or_physical_call(tmp_path,monkeypatch):
    loop,device,notes,seen=instance(tmp_path,monkeypatch)
    result=loop.step()
    assert result['waiting'] and not result['done'] and not result['input_sent']
    assert not device.clicks and not any(event=='window_intent' for event,_ in notes.events)
    assert loop.artifacts['steps'][-1]['handled_retry'] is True
    assert loop.artifacts['steps'][-1]['passed'] is False
    assert notes.events[-1][0]=='capacity_plan_discarded'


def test_repeated_storage_work_has_a_bounded_zero_input_ending(tmp_path,monkeypatch):
    loop,device,notes,_=instance(tmp_path,monkeypatch,always=True)
    for _ in range(3):assert loop.step()['waiting']
    result=loop.step()
    assert result['done'] and result['stopped']=='evidence_capacity_unavailable_before_input'
    assert not device.clicks and not any(event=='window_intent' for event,_ in notes.events)
    assert loop.artifacts['steps'][-1]['handled_retry'] is False


def test_next_input_is_replanned_against_the_new_native_control(tmp_path,monkeypatch):
    loop,device,_,seen=instance(tmp_path,monkeypatch)
    assert loop.step()['waiting'] and not device.clicks
    loop.step()
    assert len(device.clicks)==1 and len(seen)>=2
    x,y=device.clicks[0]
    assert 1520<=x<1580 and 950<=y<985
    assert loop.state['capacity_reobservations']==0


def test_interrupted_proposal_retirement_loses_authority_after_a_real_intent(tmp_path):
    run,rows,path=proposal(tmp_path);save(run,rows)
    png=path.with_suffix('.png')
    item=dict(event='capture_reclaim_intent',path=str(png.relative_to(tmp_path)),
        record=str(path.relative_to(tmp_path)),sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
        record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scene='DRIVE',
        reason='unreferenced_intermediate_capture',diagnostic_role='discarded_noninput_plan')
    (run/'capture-retention.jsonl').write_text(json.dumps(item)+'\n')
    assert png in retention._unfinished_retirements(tmp_path,[run.parent])
    rows.append(dict(event='window_intent',frame=path.stem));save(run,rows)
    assert png not in retention._unfinished_retirements(tmp_path,[run.parent])
    assert png.exists()


def test_real_recorder_pool_runner_and_device_converge_on_fresh_control(tmp_path,monkeypatch):
    """One pipeline, not separate mocked True/False capacity admissions."""
    import recognition
    from maalimbus import evidence_capacity as capacity,runner
    from test_evidence_capacity import Controller
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    run=tmp_path/'evidence/runtime/current';journal=recognition.Journal(run,history_maintenance=True)
    controller=Controller()
    device=runner.MaaDevice(controller,target_long_side=0,before_input=journal.before_input,
                            wait=lambda *args,**kwargs:None)
    loop=MirrorRunner(device,settings={'interval':0,'rounds':1},directory=run,journal=journal)
    seen=[]
    def observe(**kwargs):
        n=len(seen)+1;scene='HOME' if n<=2 else 'DRIVE'
        box=[1430 if n==1 else 1520,950,60,35]
        name=journal.frame(np.full((1080,1920,3),n,np.uint8),[] ,scene)
        data=json.loads((run/(name+'.json')).read_bytes())
        loop.controls['home.drive_button']=box;seen.append(data)
        return data
    monkeypatch.setattr(loop,'_observe',observe)
    maintenance=[]
    def reserve(directory,amount,*,application_root):
        # Initial frame publication is not input-plan maintenance. Inject the
        # actual reservation contract only at the larger plan boundary.
        first=amount>10_000_000 and not maintenance
        if first:maintenance.append(amount)
        return dict(storage_maintenance=first)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    first=loop.step()
    assert first['waiting'] and not first['input_sent'] and not controller.sent
    assert not any(json.loads(line)['event']=='window_intent'
                   for line in (run/'events.jsonl').read_text().splitlines())
    second=loop.step()
    assert second['input_sent'] and not second['stopped']
    assert len(controller.sent)==1 and controller.sent[0][0]=='click'
    _,x,y=controller.sent[0];assert 1520<=x<1580 and 950<=y<985
    assert loop.state['capacity_reobservations']==0
    assert len(maintenance)==1 and not capacity.EvidenceCapacity(tmp_path).load()['owner'].get('fresh_capture_required')


def test_capacity_refresh_abandons_only_the_notice_plan(tmp_path, monkeypatch):
    from test_shop_receipt_acknowledgement import frame, notice, pending_purchase, shelf, started

    tx, before = started(tmp_path)
    pending_purchase(tx, before)
    original = tx.path.read_bytes()
    run = tmp_path / 'runner'
    run.mkdir()
    device = FakeDevice([])
    loop = MirrorRunner(device, directory=run, run_id='scope',
                        settings={'interval': 0, 'rounds': 1})
    loop.shop_transaction = tx
    observations = []

    def observe(**kwargs):
        number = len(observations) + 1
        path = frame(run, f'frame-{number:04d}', notice(shelf()), 'GIFT_GET')
        record = json.loads(path.read_bytes())
        record['frame'] = path.stem
        observations.append(path)
        return record

    def admit(kind, payload):
        assert kind == 'plan'
        if len(observations) == 1:
            path = observations[-1]
            return dict(storage_maintenance=True, before_frame=str(path), capacity_sequence=1,
                        before_json_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        before_image_sha256=hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest())
        return None

    monkeypatch.setattr(loop, '_observe', observe)
    monkeypatch.setattr(loop, '_admit_capacity', admit)
    first = loop.step()
    assert first['waiting'] and not first['input_sent']
    assert tx.path.read_bytes() == original
    assert not device.clicks

    loop.step()
    assert len(device.clicks) == 1
    assert tx.data['pending']['stage'] == 'overlay_intent'
    assert tx.data['pending']['overlay_acknowledgement']['frame']['path'] == str(observations[1])
    assert not tx.bought_names
