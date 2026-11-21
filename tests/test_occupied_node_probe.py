"""Occupied-room inspection is bounded navigation, never an inferred map move."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from maalimbus import map_node_geometry, runner
from maalimbus.unknown_exploration import Exploration, candidates

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'evidence/runtime/packaged-mirror-20261117-064652/frame-0014.json'
GOLD = ROOT/'evidence/runtime/packaged-mirror-20261119-205814/frame-0039.png'


def actual():
    record = json.loads(SOURCE.read_text(encoding='utf8'))
    assert hashlib.sha256(SOURCE.with_suffix('.png').read_bytes()).hexdigest()==record['image_sha256']
    return record, cv2.imread(str(SOURCE.with_suffix('.png')))


@pytest.mark.parametrize('scale',[1,2/3])
def test_actual_right_edge_train_is_not_the_middle_gold_badge(scale):
    _, image=actual()
    if scale!=1:image=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    anchor=map_node_geometry.occupied_node(image)
    assert anchor and abs(anchor['party'][0]-1823*scale)<4 and abs(anchor['party'][1]-605*scale)<4
    x,y,w,h=anchor['box']
    assert x<=anchor['party'][0]<x+w and y<=anchor['party'][1]<y+h
    assert runner.party_point(image)==tuple(anchor['party'])


@pytest.mark.parametrize('part',['left_lamp','clock','flame','red_base'])
def test_removing_an_independent_sprite_part_abstains(part):
    _,image=actual();image=image.copy()
    regions=dict(left_lamp=(1799,584,1814,600),clock=(1809,554,1833,588),
                 flame=(1812,524,1837,561),red_base=(1795,600,1852,632))
    x0,y0,x1,y1=regions[part];image[y0:y1,x0:x1]=0
    assert map_node_geometry.occupied_node(image) is None


def test_actual_gold_ring_needs_both_flanks_of_the_same_train():
    if not GOLD.is_file():
        pytest.skip('local native Floor 3 capture not available')
    image = cv2.imread(str(GOLD))
    anchor = map_node_geometry.occupied_node(image)
    assert anchor['source'] == 'unique_train_on_gold_ring'
    assert anchor['party'] == [704, 431]
    assert min(anchor['gold_flank_shares']) >= .28
    image[403:468, 764:809] = 0
    assert map_node_geometry.occupied_node(image) is None


def setup(tmp_path):
    before=tmp_path/'frame-0001.json'
    record,_=actual();record['frame']='frame-0001'
    before.write_text(json.dumps(record),encoding='utf8')
    shutil.copyfile(SOURCE.with_suffix('.png'),before.with_suffix('.png'))
    explorer=Exploration(tmp_path/'exploration.json',tmp_path/'reviews','isolated-run')
    explorer.data['attempts']=[dict(candidate=dict(kind='map_viewport_pan_'+kind),success=False)
                               for kind in ('down','left','right')]
    return before,record,explorer


def after_frame(tmp_path,page):
    path=tmp_path/'frame-0002.json'
    cv2.imwrite(str(path.with_suffix('.png')),np.zeros((108,192,3),np.uint8))
    record=dict(scene=page,frame='frame-0002',size=[192,108],ocr=[],
                image_sha256=hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest())
    path.write_text(json.dumps(record),encoding='utf8')
    return path,record


@pytest.mark.parametrize('page',['NODE_PANEL','MAP','HOME','UNKNOWN'])
def test_one_extra_inspection_requires_named_expected_successor_and_human_review(tmp_path,page):
    before,record,e=setup(tmp_path)
    assert e.choose(record) is None  # no canonical native pixels, no fourth probe
    assert e.current_room_ready(record,before)
    c=e.choose(record,before);assert c['kind']=='map_current_node_inspection'
    x,y,w,h=c['box'];index=e.reserve(before,c,(x+w//2,y+h//2),500)
    e.acknowledge(index)
    assert e.choose(record,before) is None
    after,_=after_frame(tmp_path,page);outcome=e.finish(after,page)
    assert outcome['success'] is (page=='NODE_PANEL')
    proposal=json.loads(Path(outcome['proposal']).read_text())
    assert not proposal['training_eligible'] and not proposal['input_authorized'] and not proposal['reviewed']
    if page!='NODE_PANEL':assert e.choose(record,before) is None


@pytest.mark.parametrize('label',['Forfeit','Dungeon Progress','Purchase'])
def test_background_map_never_authorizes_inspection_over_exit_or_cost_overlay(tmp_path,label):
    before,record,e=setup(tmp_path)
    record['ocr'].append(dict(text=label,box=[800,300,100,30],score=.99))
    assert candidates(record,before)==[]


def test_different_canonical_record_cannot_lend_its_sprite_to_another_page(tmp_path):
    before,record,e=setup(tmp_path);record=deepcopy(record);record['image_sha256']='0'*64
    with pytest.raises(ValueError,match='canonical frame'):e.choose(record,before)
    assert e.data['pending'] is None and len(e.data['attempts'])==3


def test_map_pans_keep_their_budget_through_pause_and_home(tmp_path):
    before, record, explorer = setup(tmp_path)
    known = candidates(record)[0]
    for attempt in explorer.data['attempts']:
        attempt['candidate'].update(floor=known['floor'], pack=known['pack'])
        attempt['dispatch_confirmed'] = True
    left, right = explorer.data['attempts'][1:]
    down = explorer.data['attempts'][0]
    historical = dict(left, episode_resolved=True, resolution_page='HOME')
    explorer.data['attempts'] = [down, historical, down, left]
    home, _ = after_frame(tmp_path, 'HOME')
    explorer.resolve_episode(home, 'HOME')
    assert not explorer.data['attempts'][-1].get('episode_resolved')
    assert explorer.continuing_map_recovery(record,before)
    assert explorer.choose(record,before)['kind'] == 'map_viewport_pan_right'
    explorer.data['attempts'].append(right)
    assert explorer.choose(record,before)['kind'] == 'map_current_node_inspection'
    room, _ = after_frame(tmp_path, 'NODE_PANEL')
    explorer.resolve_episode(room, 'NODE_PANEL')
    assert explorer.data['attempts'][-1]['resolution_page'] == 'NODE_PANEL'
    assert not explorer.continuing_map_recovery(record,before)
    assert explorer.choose(record,before)['kind'] == 'map_viewport_pan_down'


def test_full_runner_probe_uses_current_room_box_not_node_distance_and_persists_review(tmp_path,monkeypatch):
    before,record,e=setup(tmp_path)
    device=runner.FakeDevice();loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(rounds=1,interval=0))
    loop.exploration=e;loop.store=SimpleNamespace(data={'active':{}})
    monkeypatch.setattr(loop,'_map_click_allowed',lambda p:pytest.fail('occupied room is not a destination'))
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a:None)
    def observe(**kwargs):return after_frame(tmp_path,'NODE_PANEL')[1]
    monkeypatch.setattr(loop,'_observe',observe)
    result=loop._explore_unknown(record,'frame-0001.png',[])
    assert result['input_sent'] and len(device.clicks)==1
    assert device.clicks[0][0]>1800 and loop.artifacts['clicks_sent']==1
    assert e.data['pending'] is None and e.data['attempts'][-1]['success']
    assert not loop.state.get('map_pending') and not loop.state.get('map_committed')


def test_current_room_probe_prevents_normalization_from_hiding_its_fresh_control(tmp_path,monkeypatch):
    _,record,e=setup(tmp_path)
    device=SimpleNamespace(controller=object())
    loop=runner.MirrorRunner(device,directory=tmp_path,settings={});loop.exploration=e
    monkeypatch.setattr(runner,'normalise_view',lambda *a,**kw:pytest.fail('known current-room box was moved'))
    assert loop._normalise_view_once(record) is record
    assert not loop.state.get('view_normalised')


def test_optional_map_zoom_defers_when_the_native_door_requires_fresh_planning(tmp_path,monkeypatch):
    from maalimbus.evidence_capacity import FreshPlanningRequired

    def before_pinch(*args):
        raise FreshPlanningRequired('funded storage maintenance requires a new capture')

    device=SimpleNamespace(controller=object(),pinch=before_pinch)
    loop=runner.MirrorRunner(device,directory=tmp_path,settings={})
    record=dict(scene='MAP', frame='frame-0001',size=[1920,1080])
    monkeypatch.setattr(runner,'frame_for',lambda *args:(None,None))
    monkeypatch.setattr(runner,'normalise_view',lambda measure,zoom,drag:zoom())
    assert loop._normalise_view_once(record) is None
    assert loop.state['view_read_pending'] and not loop.state['view_refresh_input_sent']
    assert loop.state['view_normalised'] and not loop.state.get('map_pending')


def test_actual_maa_viewport_direction_replay_centres_without_moving_valid_height():
    # Actual frame0003 ->0004 shifted the map upward into side chrome. The
    # replay models Maa content following its swipe endpoint, not reversed axes.
    point=[1823,605];drags=[]
    def measure():return tuple(point),(1920,1080)
    def drag(dx,dy):drags.append((dx,dy));point[0]+=dx;point[1]+=dy
    outcome=runner.normalise_view(measure,lambda *a:None,drag)
    assert outcome['centred'] and point==[960,605]
    assert 1<=len(drags)<=4 and all(dx<0 and dy==0 for dx,dy in drags)
