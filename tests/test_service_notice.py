"""The real outage modal cannot become background entry or a new run receipt."""
from pathlib import Path
import copy,hashlib,json
import pytest
from maalimbus import service_notice,runner
from maalimbus.vision import Text,classify
from test_recovery_budget import _loop

ROOT=Path(__file__).resolve().parents[1]


def actual_notice():
    p=ROOT/'evidence/runtime/packaged-mirror-20261118-200244/frame-0011.json'
    v=json.loads(p.read_bytes())
    assert hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest()==v['image_sha256']
    return v


def records(v):return [Text(r['text'],tuple(r['box']),r['score']) for r in v['ocr']]


def test_real_server_notice_precedes_background_before_entry():
    v=actual_notice();locale=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())
    notice=service_notice.from_record(v)
    assert notice['complete'] and notice['resume_text'].endswith('12:00 (KST)')
    assert classify(records(v),locale,v['size'])=='UNKNOWN_DIALOG'
    # Exact causality: without the foreground title the same retained background
    # is the old MIRROR_ENTRY; this is not a blanket ban on the ordinary menu.
    v['ocr']=[r for r in v['ocr'] if r['text']!='Server is under Scheduled Maintenance.']
    assert service_notice.from_record(v) is None
    assert classify(records(v),locale,v['size'])=='MIRROR_ENTRY'


@pytest.mark.parametrize('missing',['Close','You will be able to login after 12:00 (KST)'])
def test_partial_known_notice_also_vetoes_background_without_a_click_grant(missing):
    v=actual_notice();v['ocr']=[r for r in v['ocr'] if r['text']!=missing]
    assert service_notice.from_record(v)['complete'] is False
    locale=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())
    assert classify(records(v),locale,v['size'])=='UNKNOWN_DIALOG'


@pytest.mark.parametrize('fault',['weak','off_band','different_title'])
def test_unrelated_or_weak_caption_does_not_invent_outage(fault):
    v=actual_notice();row=next(r for r in v['ocr'] if 'Scheduled Maintenance' in r['text'])
    if fault=='weak':row['score']=.89
    elif fault=='off_band':row['box']=[30,30,542,26]
    else:row['text']='Scheduled reward maintenance bonus'
    assert service_notice.from_record(v) is None


@pytest.mark.parametrize('scene',['MIRROR_ENTRY','UNKNOWN','TITLE'])
def test_notice_owner_stops_before_any_dungeon_reconciliation_or_admission(scene,tmp_path,monkeypatch):
    v=actual_notice();v['scene']=scene;loop=_loop(tmp_path)
    pending={'unjudged':'keep'};loop.state['pending']=copy.deepcopy(pending)
    monkeypatch.setattr(loop,'_observe',lambda **kw:v)
    loop.device.before_input=lambda *a:pytest.fail('Outage cannot reserve a new input')
    result=loop.step()
    assert result['stopped']=='service_notice_requires_durable_navigation' and result['done']
    assert result['input_sent'] is False and result['target'] is None
    assert loop.device.clicks==[] and loop.device.swipes==[] and loop.device.pinches==[]
    assert loop.state['pending']==pending and not loop.state.get('login_attempts')
    event=runner.events(tmp_path,'server_notice_observed')[-1]
    assert event['notice']['complete'] and event['business_pending_preserved']
    assert not runner.events(tmp_path,'window_intent')


def test_runner_node_job_cannot_traverse_legacy_entry_confirmation(monkeypatch):
    calls=[];job=object()
    class Tasker:
        def post_task(self,*args):calls.append(args);return job
    monkeypatch.setattr(runner,'wait_task',lambda tasker,handle,**kw:{'task_succeeded':handle is job})
    assert runner.run_node(Tasker(),'MirrorDrive',100.)['task_succeeded']
    assert calls==[('MirrorDrive',{'MirrorDrive':{'next':[],'on_error':[]}})]
    calls.clear();runner.run_node(Tasker(),'LimbusMapObserve',100.)
    assert calls==[('LimbusMapObserve',)]


def test_known_notice_recovered_by_reread_reaches_the_same_zero_input_owner(tmp_path,monkeypatch):
    v=actual_notice();v['scene']='UNKNOWN_DIALOG';loop=_loop(tmp_path)
    seq=iter([dict(scene='UNKNOWN',size=v['size'],ocr=[]),v])
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(seq))
    loop.state['pending']={'unjudged':'keep'}
    result=loop.step()
    assert result['stopped']=='service_notice_requires_durable_navigation' and not result['input_sent']
    assert not loop.device.clicks and loop.state['pending']=={'unjudged':'keep'}
    assert runner.events(tmp_path,'unknown_reread_recovered')[-1]['now']=='UNKNOWN_DIALOG'


def test_native_idle_reconciliation_cannot_retire_a_run_from_the_modal_background(tmp_path):
    from test_mirror_startup_reconciliation import old_run
    from maalimbus.run_wiring import reconcile_idle_entry
    store,scope=old_run(tmp_path/'config');before=store.path.read_bytes()
    proof=ROOT/'evidence/runtime/packaged-mirror-20261118-200244/frame-0011.json'
    # This original historical producer incorrectly called the modal MIRROR_ENTRY.
    assert json.loads(proof.read_bytes())['scene']=='MIRROR_ENTRY'
    result=reconcile_idle_entry(store,proof)
    assert not result['retired'] and result['reason']=='service_notice_preserves_active_run'
    assert store.path.read_bytes()==before and store.data['active']['id']==scope


def service_loop(tmp_path,monkeypatch):
    from test_mirror_startup_reconciliation import old_run
    from test_recovery_budget import _Journal
    store,scope=old_run(tmp_path/'config')
    directory=tmp_path/'evidence';directory.mkdir()
    loop=runner.MirrorRunner(runner.FakeDevice(),settings={'rounds':1,'interval':0},
        store=store,run_id=scope,directory=directory,journal=_Journal(directory))
    monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    return loop


def capture(loop,source,number,scene=None):
    import shutil
    path=loop.directory/f'frame-{number:04d}.json'
    record=json.loads(source.read_bytes())
    if scene is not None:record['scene']=scene
    record['frame']=path.stem
    path.write_text(json.dumps(record),encoding='utf8')
    shutil.copyfile(source.with_suffix('.png'),path.with_suffix('.png'))
    return record


NOTICE=ROOT/'dist/MaaLimbus/evidence/runtime/pi-20261119-012451/frame-0002.json'
# The notice frame was captured by the installed application, under the local build.
needs_notice=pytest.mark.needs_local('dist/MaaLimbus/evidence/runtime/pi-20261119-012451/frame-0002.json')
ENTRY=ROOT/'evidence/runtime/packaged-mirror-20261118-200244/frame-0004.json'


@needs_notice
def test_real_gui_notice_closes_once_then_independent_successor_only_labels_navigation(tmp_path,monkeypatch):
    loop=service_loop(tmp_path,monkeypatch)
    ledger=loop.store.path.read_bytes();loop.state['pending']={'keep':'business'}
    record=capture(loop,NOTICE,1,'UNKNOWN_DIALOG')
    result=loop._startup_handoff(record)
    assert result['input_sent'] and not result['done'] and len(loop.device.clicks)==1
    plan=loop.artifacts['steps'][-1]['plan']
    assert plan==runner.plan_step('UNKNOWN_DIALOG',controls={'unknown_dialog.close':service_notice.from_record(record)['close_box']})
    assert plan['expect']==['*'] and plan['advance']
    x,y=loop.device.clicks[0];bx,by,w,h=service_notice.from_record(record)['close_box']
    assert bx<=x<bx+w and by<=y<by+h
    state=loop.store.path.parent/'user-service-navigation.json'
    intent=json.loads(state.read_bytes())
    assert intent['pending']==0 and intent['attempts'][0]['dispatch_confirmed']
    assert 350<=intent['attempts'][0]['delay_ms']<=750
    record=capture(loop,ENTRY,2,'MIRROR_ENTRY')
    assert loop._startup_handoff(record) is None
    assert json.loads(state.read_bytes())['pending'] is None
    event=runner.events(loop.directory,'service_notice_navigation_reconciled')[-1]
    assert event['success'] and not event['server_availability_proven']
    proposal=json.loads(Path(event['proposal']).read_bytes())
    assert proposal['proposed_label']=='dismiss_service_notice_to_MIRROR_ENTRY'
    assert not proposal['training_eligible'] and not proposal['input_authorized']
    assert loop.store.path.read_bytes()==ledger and loop.state['pending']=={'keep':'business'}


@needs_notice
def test_repeated_modal_stops_only_after_one_acknowledged_close(tmp_path,monkeypatch):
    loop=service_loop(tmp_path,monkeypatch)
    loop._startup_handoff(capture(loop,NOTICE,1,'UNKNOWN_DIALOG'))
    for number in (2,3):
        result=loop._startup_handoff(capture(loop,NOTICE,number,'UNKNOWN_DIALOG'))
        assert result['waiting'] and not result['input_sent']
    result=loop._startup_handoff(capture(loop,NOTICE,4,'UNKNOWN_DIALOG'))
    assert result['stopped']=='service_notice_repeated_after_close'
    assert len(loop.device.clicks)==1
    state=json.loads((loop.store.path.parent/'user-service-navigation.json').read_bytes())
    assert state['pending'] is None and not state['attempts'][0]['success']


@needs_notice
def test_sdk_failure_keeps_pending_zero_and_restart_does_not_replay(tmp_path,monkeypatch):
    loop=service_loop(tmp_path,monkeypatch)
    def fail(*a):raise RuntimeError('Native route failed')
    loop.device.click=fail
    with pytest.raises(RuntimeError,match='Native route'):
        loop._startup_handoff(capture(loop,NOTICE,1,'UNKNOWN_DIALOG'))
    state=loop.store.path.parent/'user-service-navigation.json';saved=state.read_bytes()
    result=loop._startup_handoff(capture(loop,NOTICE,2,'UNKNOWN_DIALOG'))
    assert result['stopped']=='service_notice_dispatch_outcome_unproven'
    assert state.read_bytes()==saved and json.loads(saved)['pending']==0


@pytest.mark.parametrize('fault',['weak_title','missing_title','missing_resume','duplicate_close'])
def test_partial_modal_never_becomes_dismissal_success(fault):
    record=actual_notice();record['scene']='MIRROR_ENTRY'
    if fault=='weak_title':
        next(t for t in record['ocr'] if 'Scheduled Maintenance' in t['text'])['score']=.6
    elif fault=='missing_title':record['ocr']=[r for r in record['ocr'] if 'Scheduled Maintenance' not in r['text']]
    elif fault=='missing_resume':record['ocr']=[r for r in record['ocr'] if 'login after' not in r['text']]
    else:record['ocr'].append(copy.deepcopy(next(t for t in record['ocr'] if t['text']=='Close')))
    assert not service_notice.dismissed_successor(record,'MIRROR_ENTRY')


@needs_notice
def test_storage_reobserve_does_not_reserve_or_consume_notice_attempt(tmp_path,monkeypatch):
    loop=service_loop(tmp_path,monkeypatch)
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a:dict(storage_maintenance=True))
    sentinel={'waiting':True}
    monkeypatch.setattr(loop,'_capacity_reobserve',lambda *a:sentinel)
    assert loop._startup_handoff(capture(loop,NOTICE,1,'UNKNOWN_DIALOG')) is sentinel
    assert not loop.device.clicks
    assert not (loop.store.path.parent/'user-service-navigation.json').exists()


@needs_notice
def test_acknowledgement_write_failure_records_sent_input_and_preserves_disk_intent(tmp_path,monkeypatch):
    from maalimbus import unknown_exploration
    loop=service_loop(tmp_path,monkeypatch)
    write=unknown_exploration.write_json
    def fail_ack(path,data):
        if any(a.get('dispatch_confirmed') for a in data.get('attempts',[])):
            raise OSError('Injected ACK write failure')
        return write(path,data)
    monkeypatch.setattr(unknown_exploration,'write_json',fail_ack)
    with pytest.raises(OSError,match='ACK write'):
        loop._startup_handoff(capture(loop,NOTICE,1,'UNKNOWN_DIALOG'))
    assert len(loop.device.clicks)==loop.artifacts['clicks_sent']==1
    assert loop.artifacts['steps'][-1]['input_sent']
    state=loop.store.path.parent/'user-service-navigation.json';saved=state.read_bytes()
    assert json.loads(saved)['pending']==0
    assert not json.loads(saved)['attempts'][0]['dispatch_confirmed']
    result=loop._startup_handoff(capture(loop,NOTICE,2,'UNKNOWN_DIALOG'))
    assert result['stopped']=='service_notice_dispatch_outcome_unproven'
    assert state.read_bytes()==saved and len(loop.device.clicks)==1
