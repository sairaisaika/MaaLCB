"""Page chrome is not a destination one lattice step from the party."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from maalimbus import map_dispatch,runner,window


@pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261117-061129')
@pytest.mark.parametrize('name',['frame-0021','frame-0023','frame-0026'])
def test_actual_moving_progress_sheet_never_exposes_its_background_map(name):
    from maalimbus.vision import Text,classify
    from maalimbus.dungeon_progress import floating_panel
    from maalimbus.learning_dataset import digest
    root=Path(__file__).resolve().parents[1]
    p=root/'evidence/runtime/packaged-mirror-20261117-061129'/(name+'.json')
    record=json.loads(p.read_text(encoding='utf8'))
    assert digest(p.with_suffix('.png'))==record['image_sha256']
    texts=[Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']]
    assert floating_panel(texts,record['size'])
    locale=json.loads((root/'assets/resource/en/locale.json').read_text(encoding='utf8'))
    assert classify(texts,locale,record['size'])=='DUNGEON_PROGRESS'
    assert not floating_panel([t for t in texts if t.text!='Config'],record['size'])


def test_progress_control_is_not_a_map_node_even_when_no_destination_is_visible():
    plan=window.plan_step('MAP',controls={'map.progress_button':runner.MAP_PROGRESS_CONTROL},candidates=[])
    assert plan['target_role']=='page_control' and plan['control_id']=='map.progress_button'
    assert map_dispatch.is_progress_action(plan)
    assert not map_dispatch.is_node_action(plan)
    assert window.successor_ok(plan,'DUNGEON_PROGRESS')
    assert not window.successor_ok(plan,'SHOP')


@pytest.mark.parametrize('fields',[{},dict(target_role='page_control'),
    dict(target_role='page_control',control_id='arbitrary_control'),dict(target_role='map_node')])
def test_legacy_or_unbound_targets_keep_the_node_reach_guard(fields):
    plan=dict(page='MAP',action='click',**fields)
    assert map_dispatch.is_node_action(plan)
    assert not map_dispatch.is_progress_action(plan)


@pytest.mark.parametrize('scene',['DUNGEON_PROGRESS','SHOP_PURCHASE','GIFT_PICK','NODE_PANEL','UNKNOWN_DIALOG'])
def test_known_foregrounds_do_not_grant_background_map_probes(scene):
    assert not map_dispatch.can_probe_header_only(scene)
    assert map_dispatch.can_probe_header_only('UNKNOWN')


@pytest.mark.parametrize('fault',[None,'foreign','victory','reward','preparing','missing_scope'])
def test_only_current_unfinished_entered_scope_restores_the_resume_goal(fault):
    active=dict(id='current',phase='entered',victory=False,reward=False)
    if fault=='foreign':active['id']='old'
    elif fault=='missing_scope':active.pop('id')
    elif fault=='victory':active['victory']=True
    elif fault=='reward':active['reward']=True
    elif fault=='preparing':active['phase']='preparing'
    original=deepcopy(active);state={}
    assert map_dispatch.resume_navigation_requested(state,active,'current') is (fault is None)
    assert active==original and state=={}


def test_whole_runner_dispatches_progress_once_without_reserving_a_node(tmp_path,monkeypatch):
    source=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-060043/frame-0018.json'
    assert source.exists(),'actual stopped MAP observation must be retained'
    before=json.loads(source.read_text(encoding='utf8'));before['frame']='frame-0001'
    shutil.copyfile(source.with_suffix('.png'),tmp_path/'frame-0001.png')
    (tmp_path/'frame-0001.json').write_text(json.dumps(before),encoding='utf8')
    # The successor here is synthetic; native DUNGEON_PROGRESS acceptance remains a live check.
    after=dict(scene='DUNGEON_PROGRESS',frame='frame-0002',image_sha256='2'*64,size=[1920,1080],ocr=[])
    reads=iter([before,after,after])
    device=runner.FakeDevice();loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    loop.state['map_refused_streak']=3
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(loop,'_normalise_view_once',lambda r:r)
    monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:('frame-0001.png',[[1100,500,100,100]]))
    monkeypatch.setattr(loop,'_map_click_allowed',lambda point:pytest.fail('page control was tested as node'))
    result=loop.step()
    assert len(device.clicks)==1
    x,y=device.clicks[0];bx,by,bw,bh=runner.MAP_PROGRESS_CONTROL
    assert bx<=x<bx+bw and by<=y<by+bh
    assert result['input_sent']
    assert loop.artifacts['steps'][-1]['page_after']=='DUNGEON_PROGRESS'
    assert not loop.state.get('map_pending') and not loop.state.get('map_unjudged')
    assert not loop.state.get('map_committed')


def test_actual_progress_modal_uses_its_own_window_control_not_blind_map_boxes(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    source=root/'evidence/runtime/packaged-mirror-20261117-061129/frame-0021.json'
    before=json.loads(source.read_text(encoding='utf8'));before['frame']='frame-0001'
    assert before['scene']=='DUNGEON_PROGRESS' and runner._header_was_read(before)
    shutil.copyfile(source.with_suffix('.png'),tmp_path/'frame-0001.png')
    (tmp_path/'frame-0001.json').write_text(json.dumps(before),encoding='utf8')
    after=dict(scene='RESUME_DIALOG',frame='frame-0002',image_sha256='2'*64,size=[1920,1080],ocr=[])
    reads=iter([before,after,after]);device=runner.FakeDevice()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    loop.state['resume_requested']=True
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:(None,None))
    monkeypatch.setattr(runner,'blind_map_boxes',lambda *a,**kw:pytest.fail('known modal became background map'))
    monkeypatch.setattr(loop,'_map_click_allowed',lambda point:pytest.fail('modal control tested as node'))
    result=loop.step()
    assert result['input_sent'] and len(device.clicks)==1
    target=loop.artifacts['steps'][-1]['plan']['target'];x,y=device.clicks[0]
    assert target[0]<=x<target[0]+target[2] and target[1]<=y<target[1]+target[3]
    assert loop.artifacts['steps'][-1]['page_after']=='RESUME_DIALOG'
    assert not loop.state.get('map_pending') and not loop.state.get('map_blind_tried')
