"""Mandatory startup ownership checks; no optional historical frame dependency."""
import copy
import pytest
from maalimbus import runner,service_notice
from maalimbus.vision import Text,classify
from test_recovery_budget import _loop


def title():
    return dict(scene='TITLE',frame='frame-0001',size=[1920,1080],image_sha256='a'*64,
        ocr=[dict(text='TOUCH TO START',box=[844,810,224,41],score=.99)])


def update_notice():
    record=title();record['ocr']+= [dict(text=text,box=box,score=.99) for text,box in (
        ('Game client is not up to date.',[720,465,500,40]),
        ('Please update to the latest version.',[700,510,540,40]),
        ('Close',[760,685,100,35]),('Go to Store',[1010,685,200,35]))]
    return record


def shutdown_notice(scene='GIFT_SEARCH'):
    # live pi-20261125-195746 frame-0048: the dialog over the gift search page.
    return dict(scene=scene,frame='frame-0048',size=[1920,1080],image_sha256='c'*64,ocr=[
        dict(text='E.G.O Gift Search',box=[218,52,290,40],score=.99),
        dict(text='Refuse Gift',box=[1302,843,152,34],score=.99),
        dict(text='Cannot operate the game.',box=[778,466,356,36],score=1.0),
        dict(text='Shutting down now.',box=[826,510,268,28],score=1.0),
        dict(text='Close',box=[910,678,92,40],score=1.0)])


def download_notice(scene='HOME'):
    # live packaged-mirror-20261126-042150 frame-2244: the dialog over the main menu.
    return dict(scene=scene,frame='frame-2244',size=[1920,1080],image_sha256='d'*64,ocr=[
        dict(text='Window',box=[1202,968,80,28],score=.99),dict(text='Drive',box=[1438,968,68,28],score=.99),
        dict(text='A new download has been added.',box=[712,464,488,34],score=.999),
        dict(text='The game will be closed; please restart the',box=[650,500,618,40],score=.998),
        dict(text='game to download the update.',box=[734,540,446,39],score=.995),
        dict(text='Confirm',box=[926,724,114,40],score=1.0)])


@pytest.mark.parametrize('missing',[None,'Confirm','game to download the update.'])
def test_the_restart_to_download_dialog_ends_the_invocation_and_presses_nothing(missing,tmp_path,monkeypatch):
    record=download_notice()
    if missing:record['ocr']=[r for r in record['ocr'] if r['text']!=missing]
    notice=service_notice.from_record(record)
    assert notice['kind']=='restart_for_download' and notice['complete'] is (missing is None)
    assert service_notice.close_candidates(record)==[]
    loop=_loop(tmp_path);loop.state['pending']={'keep':'business'}
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    result=loop.step()
    assert result['stopped']=='the_game_asks_to_be_restarted_to_download_an_update'
    assert not result['input_sent'] and not loop.device.clicks
    assert loop.state['pending']=={'keep':'business'}
    assert not runner.events(tmp_path,'window_intent')
    assert not service_notice.dismissed_successor(record,'HOME')


@pytest.mark.parametrize('missing',[None,'Close','Shutting down now.'])
def test_the_shutdown_dialog_ends_the_invocation_by_name_and_presses_nothing(missing,tmp_path,monkeypatch):
    record=shutdown_notice()
    if missing:record['ocr']=[r for r in record['ocr'] if r['text']!=missing]
    notice=service_notice.from_record(record)
    assert notice['kind']=='session_shutdown' and notice['complete'] is (missing is None)
    # Its Close shuts the client down: it is never offered as a way on.
    assert service_notice.close_candidates(record)==[]
    loop=_loop(tmp_path);loop.state['pending']={'keep':'business'}
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    result=loop.step()
    assert result['stopped']=='the_game_says_it_cannot_be_operated_and_is_shutting_down'
    assert not result['input_sent'] and not loop.device.clicks
    assert loop.state['pending']=={'keep':'business'}
    assert not runner.events(tmp_path,'window_intent')


def test_the_page_under_the_shutdown_dialog_is_not_a_dismissed_notice():
    for page in ('HOME','TITLE','DRIVE','MIRROR_ENTRY'):
        assert not service_notice.dismissed_successor(shutdown_notice(page),page)
    # The maintenance notice keeps its own kind; the two are told apart by their titles.
    maintenance=dict(shutdown_notice(),ocr=[
        dict(text='Server is under Scheduled Maintenance.',box=[686,470,542,28],score=1.0),
        dict(text='You will be able to login after 12:00 (KST)',box=[674,504,566,36],score=.99),
        dict(text='Close',box=[910,678,92,40],score=1.0)])
    assert service_notice.from_record(maintenance)['kind']=='scheduled_maintenance'


@pytest.mark.parametrize('page',['TITLE','UNKNOWN','LOADING','CONNECTING'])
def test_acknowledged_login_waits_on_original_clock_without_second_input(page,tmp_path,monkeypatch):
    loop=_loop(tmp_path);clock=[100.]
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop.state['pending']={'business':'keep'}
    assert loop._startup_handoff(title())['input_sent'];deadline=loop.startup_deadline
    clock[0]=130.;record=dict(title(),scene=page,frame='frame-0002')
    result=loop._startup_handoff(record)
    assert result['waiting'] and not result['input_sent'] and not result['done']
    assert loop.startup_deadline==deadline and len(loop.device.clicks)==1
    assert loop.state['pending']=={'business':'keep'}
    assert runner.events(tmp_path,'login_response_wait')[-1]['remaining_seconds']==150.


def test_login_wait_obeys_tighter_task_deadline_and_home_can_settle(tmp_path,monkeypatch):
    loop=_loop(tmp_path);clock=[100.]
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop._startup_handoff(title());original=loop.startup_deadline;loop.deadline=110.
    assert loop._startup_handoff(title())['waiting']
    assert runner.events(tmp_path,'login_response_wait')[-1]['remaining_seconds']==10.
    home=dict(title(),scene='HOME',frame='frame-0002',image_sha256='b'*64)
    assert loop._startup_handoff(home) is None and 'login_input_entry' not in loop.state
    assert loop.startup_deadline==original and len(loop.device.clicks)==1


def test_title_deadline_exhaustion_names_missing_response_not_an_input_failure(tmp_path,monkeypatch):
    loop=_loop(tmp_path);clock=[100.]
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop._startup_handoff(title());clock[0]=281.
    result=loop._startup_handoff(title())
    assert result['stopped']=='login_response_not_observed_before_deadline'
    assert len(loop.device.clicks)==1 and loop.startup_deadline==280.


@pytest.mark.parametrize('missing',[None,'Close','Go to Store','Please update to the latest version.'])
def test_client_update_foreground_veto_never_grants_close_or_store(missing,tmp_path,monkeypatch):
    record=update_notice()
    if missing:record['ocr']=[r for r in record['ocr'] if r['text']!=missing]
    notice=service_notice.from_record(record)
    assert notice['kind']=='client_update_required'
    assert service_notice.close_candidates(record)==[]
    assert classify([Text(r['text'],tuple(r['box']),r['score']) for r in record['ocr']],{},record['size'])=='UNKNOWN_DIALOG'
    loop=_loop(tmp_path);loop.state['pending']={'keep':'business'}
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    result=loop.step()
    assert result['stopped']=='game_client_update_required' and not result['input_sent']
    assert not loop.device.clicks and loop.state['pending']=={'keep':'business'}
    assert not runner.events(tmp_path,'window_intent')


def test_delayed_client_update_preempts_pending_login_wait(tmp_path,monkeypatch):
    loop=_loop(tmp_path);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop._startup_handoff(title());entry=loop.state['login_input_entry']
    result=loop._startup_handoff(update_notice())
    assert result['stopped']=='game_client_update_required' and len(loop.device.clicks)==1
    assert loop.state['login_input_entry'] is entry and not entry['passed']


def test_observe_only_does_not_wait_or_repeat_an_old_login(tmp_path,monkeypatch):
    loop=_loop(tmp_path);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop._startup_handoff(title());deadline=loop.startup_deadline
    loop.settings=runner.Settings({'observe_only':True})
    result=loop._startup_handoff(title())
    assert result['done'] and not result['input_sent'] and len(loop.device.clicks)==1
    assert loop.startup_deadline==deadline


def test_expired_unknown_can_still_reach_normal_independent_reread(tmp_path,monkeypatch):
    loop=_loop(tmp_path);clock=[100.]
    monkeypatch.setattr(runner.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(runner.time,'sleep',lambda *a:None)
    loop._startup_handoff(title());clock[0]=281.
    assert loop._startup_handoff(dict(title(),scene='UNKNOWN')) is None
    assert loop.startup_deadline==280. and len(loop.device.clicks)==1
