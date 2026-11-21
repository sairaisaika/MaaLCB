"""Cold native launch waits on one clock; text refusals never move other pages."""
import pytest
from maalimbus import runner
from test_recovery_budget import _loop


@pytest.mark.parametrize('page',['UNKNOWN','LOADING','SHOP','BATTLE_HUD','PRE_BATTLE_TEAM'])
def test_nonmap_viewport_backstop_never_dispatches(page,tmp_path):
    loop=_loop(tmp_path)
    for gesture in ('pinch_out','drag_down','pan_left'):
        assert loop._viewport_recovery(page,gesture) is False
    assert loop.device.pinches==[] and loop.device.swipes==[] and loop.device.clicks==[]
    assert loop._map_zoom_once(page,{}, {}, {}) is None


def test_retained_stop_reason_and_actual_ladder_use_the_same_kind(tmp_path,monkeypatch):
    loop=_loop(tmp_path);monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    entry=dict(stopped_reason='page_unreadable_after_waiting')
    assert loop._recover('UNKNOWN',loop.state,entry,{}) is not None
    fields=runner.events(tmp_path,'window_recovery')[-1]
    assert fields['refused_kind']==fields['deciding_kind']=='unreadable_text'
    assert fields['recovery_action']=='reread_text' and fields['gesture']=='wait'
    assert loop.device.pinches==[] and loop.device.swipes==[]
    assert loop._recover('UNKNOWN',loop.state,entry,{}) is None


def test_cold_wait_preserves_pending_and_uses_original_absolute_deadline(tmp_path,monkeypatch):
    loop=_loop(tmp_path);clock=[100.0]
    loop.startup_deadline=280.;loop.deadline=110.
    loop.state['pending']={'proof':'keep'}
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(loop,'_observe',lambda:dict(scene='LOADING',frame='frame-0001',ocr=[]))
    result=loop.step()
    assert result['startup'] and not result['input_sent'] and not result['done']
    assert loop.startup_deadline==280. and loop.state['pending']=={'proof':'keep'}
    event=runner.events(tmp_path,'cold_start_wait')[-1]
    assert event['remaining_seconds']==10.
    assert loop.device.pinches==[] and loop.device.swipes==[] and loop.device.clicks==[]


def test_named_archived_image_cannot_borrow_newer_pixels(tmp_path,monkeypatch):
    from test_native_image_archive import batch
    from maalimbus import native_image_archive
    from test_observation_frame import capture
    path,entry,body=batch(tmp_path,monkeypatch)
    native_image_archive.compact(tmp_path)
    image,name=runner.frame_for(path.parent,dict(frame=path.stem,frame_ref={'own':True}))
    assert name==path.with_suffix('.png').name and image.shape==(16,24,3)
    capture(path.parent,'frame-0002')
    index=native_image_archive.load_index(tmp_path)
    (tmp_path/index['members'][entry['path']]['archive']).write_bytes(b'changed')
    with pytest.raises(ValueError):runner.frame_for(path.parent,dict(frame=path.stem,frame_ref={'own':True}))


def test_title_uses_normal_native_input_door_and_never_reconciles_dungeon_pending(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from maalimbus.vision import Text,classify
    path=Path(__file__).resolve().parents[1]/'evidence/runtime/window-20261117-043656/frame-0006.json'
    raw=json.loads(path.read_bytes())
    assert classify([Text(r['text'],tuple(r['box']),r['score']) for r in raw['ocr']],{},raw['size'])=='TITLE'
    loop=_loop(tmp_path);loop.state['pending']={'unjudged':'must remain'}
    clock=[100.];monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(loop,'_observe',lambda:dict(raw,scene='TITLE'))
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    admissions=[];loop.device.before_input=lambda *args:admissions.append(args)
    first=loop.step();deadline=loop.startup_deadline;second=loop.step()
    clock[0]=deadline+1;third=loop.step()
    assert first['input_sent'] and second['waiting'] and not second['input_sent']
    assert third['stopped']=='login_response_not_observed_before_deadline'
    assert loop.startup_deadline==deadline and len(loop.device.clicks)==1 and len(admissions)==1
    assert loop.state['pending']=={'unjudged':'must remain'}
    for row in runner.events(tmp_path,'window_intent'):
        x,y,w,h=row['target'];px,py=row['click_point']
        assert x<=px<=x+w and y<=py<=y+h and 350<=row['delay_ms']<=750


def test_title_observe_only_never_taps_or_starts_a_timer(tmp_path,monkeypatch):
    loop=_loop(tmp_path);loop.settings=runner.Settings({'observe_only':True})
    monkeypatch.setattr(loop,'_observe',lambda:dict(scene='TITLE',size=[1920,1080],
        ocr=[dict(text='TOUCH TO START',box=[850,808,216,41],score=.99)]))
    assert loop.step()['done'] and loop.device.clicks==[] and loop.startup_deadline is None


def _current_title():
    """Actual stopped installed invocation; literal paths retain its original pair."""
    import json,hashlib
    from pathlib import Path
    p=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261118-180151/frame-0003.json'
    raw=json.loads(p.read_bytes())
    assert hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest()==raw['image_sha256']
    return raw


def test_unknown_reread_title_reaches_the_login_owner_in_the_same_step(tmp_path,monkeypatch):
    raw=_current_title();loop=_loop(tmp_path);loop.state['pending']={'owned':'keep'}
    records=iter([dict(raw,scene='UNKNOWN',ocr=[]),raw])
    phases=[]
    def observe(**kw):phases.append(kw.get('phase'));return next(records)
    monkeypatch.setattr(loop,'_observe',observe)
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    admitted=[];loop.device.before_input=lambda *args:admitted.append(args)
    result=loop.step()
    assert result['page']=='TITLE' and result['input_sent'] and len(loop.device.clicks)==1
    assert phases==[None,'reread_unknown'] and len(admitted)==1
    assert runner.events(tmp_path,'unknown_reread_recovered')[-1]['now']=='TITLE'
    assert runner.events(tmp_path,'login_start_sent')[-1]['attempt']==1
    assert not runner.events(tmp_path,'window_page_retry')
    assert loop.state['pending']=={'owned':'keep'}


def test_login_storage_work_discards_unsent_plan_and_replans_fresh_caption(tmp_path,monkeypatch):
    raw=_current_title();loop=_loop(tmp_path)
    import copy
    second=copy.deepcopy(raw)
    second['ocr']=[dict(text='TOUCH TO START',box=[1010,810,120,35],score=.99)]
    records=iter([raw,second]);monkeypatch.setattr(loop,'_observe',lambda **kw:next(records))
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    admissions=[]
    def admit(*args):
        admissions.append(args)
        if len(admissions)==1:
            return dict(storage_maintenance=True,capacity_sequence=1,before_frame='frame-0003.json',
                        before_json_sha256='a'*64,before_image_sha256=raw['image_sha256'])
    loop.device.before_input=admit
    first=loop.step()
    assert first['waiting'] and not first['input_sent'] and not loop.device.clicks
    assert 'login_input_entry' not in loop.state and not loop.state.get('login_attempts')
    assert loop.startup_deadline is None and not runner.events(tmp_path,'window_intent')
    assert len(loop.artifacts['steps'])==1 and loop.artifacts['steps'][0]['passed'] is False
    result=loop.step();assert result['input_sent'] and len(loop.device.clicks)==1
    x,y=loop.device.clicks[0];assert 1010<=x<=1130 and 810<=y<=845
    assert loop.state['login_attempts']==1 and len(loop.artifacts['steps'])==2


def test_home_recovered_by_reread_settles_only_the_existing_login_input(tmp_path,monkeypatch):
    raw=_current_title();loop=_loop(tmp_path);monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    monkeypatch.setattr(loop,'_observe',lambda **kw:raw);loop.step()
    entry=loop.state['login_input_entry'];loop.state['pending']={'dungeon':'keep'}
    loop.startup_deadline=0.  # Exercise the normal reread after the cold-loading window.
    home=dict(frame='frame-0004',scene='HOME',size=[1920,1080],image_sha256='b'*64,ocr=[])
    records=iter([dict(home,scene='UNKNOWN'),home])
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(records))
    monkeypatch.setattr(loop,'_incoming_handoff',lambda page,record:loop._result(page,None,False,None,done=True))
    loop.step()
    assert entry['passed'] is True and entry['successor_frame']=='frame-0004'
    assert 'login_input_entry' not in loop.state and loop.state['pending']=={'dungeon':'keep'}
    assert len(loop.device.clicks)==1
    assert len(runner.events(tmp_path,'login_successor_observed'))==1
