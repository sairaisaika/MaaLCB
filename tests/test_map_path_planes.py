"""Node appearance x edge appearance; retained red/white full-candidate regression."""
import hashlib,json,shutil
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus import map_node_geometry as geometry,map_vision,runner
from maalimbus.window import plan_step

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence'/'runtime'/'packaged-mirror-20261119-071105'/'frame-0037.json'


def scene(monkeypatch,family,appearance):
    image=np.zeros((1080,1920,3),np.uint8);party=(600,400);target=(900,400)
    monkeypatch.setattr(geometry,'train_body',lambda *a,**kw:dict(party=list(party),lamp_gap=60))
    monkeypatch.setattr(map_vision,'locomotive_marker',lambda *a,**kw:party)
    rows=[dict(kind='gold_badge_node',box=[205,314,190,190]),
          dict(kind='gold_badge_node',box=[505,474,190,190])]
    if family=='lit':rows.append(dict(kind='lit_ring',box=[850,350,100,100]))
    monkeypatch.setattr(map_vision,'map_clicks',lambda *a,**kw:rows)
    monkeypatch.setattr(map_vision,'node_markers',lambda *a,**kw:[])
    color={'warm':(20,120,240),'blue':(240,120,20),'white':(240,240,240),'grey':(125,125,125)}
    if appearance=='chevrons':
        for x in (730,745,760):
            cv2.polylines(image,[np.int32([[x,390],[x+8,400],[x,410]])],False,(240,)*3,3)
    elif appearance=='split':
        cv2.line(image,party,(750,400),color['warm'],5)
        cv2.line(image,(750,400),target,color['white'],5)
    elif appearance!='absent':cv2.line(image,party,target,color[appearance],5)
    radius=60 if family=='red' else 51
    angles=np.arange(6)*np.pi/3+np.pi/6
    polygon=np.column_stack((900+radius*np.cos(angles),400+radius*np.sin(angles))).round().astype(np.int32)
    outline=(0,0,240) if family=='red' else (20,160,240) if family=='lit' else (210,)*3
    cv2.polylines(image,[polygon],True,outline,7 if family=='red' else 3)
    return image,party


def read(image,party,family):
    return (geometry.connected_red_node(image) if family=='red' else
            geometry.connected_ring_node(image) if family=='lit' else
            geometry._connected_white_outline(image,party))


@pytest.mark.parametrize('family',['red','lit','neutral'])
@pytest.mark.parametrize('appearance',['warm','blue','white'])
def test_each_outline_family_accepts_independently_supported_path(monkeypatch,family,appearance):
    image,party=scene(monkeypatch,family,appearance);found=read(image,party,family)
    assert found and abs(found['point'][0]-900)<5 and abs(found['point'][1]-400)<5
    key=('bright_share' if appearance=='white' else
         'saturated_share' if appearance=='blue' and family=='red' else 'warm_share')
    assert found[key]>=.70 and len([k for k in ('warm_share','saturated_share','bright_share') if k in found])==1


@pytest.mark.parametrize('family',['red','lit','neutral'])
@pytest.mark.parametrize('appearance',['grey','chevrons','absent','split'])
def test_dim_or_fragmentary_support_cannot_be_manufactured_into_one_edge(monkeypatch,family,appearance):
    image,party=scene(monkeypatch,family,appearance)
    assert read(image,party,family) is None


@pytest.mark.parametrize('appearance',['warm','blue','white'])
def test_a_supported_path_cannot_make_an_open_red_chevron_into_a_destination(monkeypatch,appearance):
    image,party=scene(monkeypatch,'red',appearance)
    image[330:470,830:970]=0
    color={'warm':(20,120,240),'blue':(240,120,20),'white':(240,240,240)}
    cv2.line(image,party,(900,400),color[appearance],5)
    cv2.polylines(image,[np.int32([[840,345],[950,400],[840,455]])],False,(0,0,240),7)
    assert geometry.connected_red_node(image) is None


def retained(tmp_path,width=1920,pan=(0,0)):
    if not SOURCE.is_file() or not SOURCE.with_suffix('.png').is_file():
        pytest.skip('Retained red/white failure unavailable; mandatory appearance matrix still executes')
    original=SOURCE.read_bytes();raw=json.loads(original);pixels=SOURCE.with_suffix('.png').read_bytes()
    assert hashlib.sha256(pixels).hexdigest()==raw['image_sha256']
    image=cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR)
    dx,dy=pan;top,bottom=240,905
    image[top:bottom]=cv2.warpAffine(image[top:bottom],np.float32([[1,0,dx],[0,1,dy]]),(1920,bottom-top))
    scale=width/1920;image=cv2.resize(image,(width,round(1080*scale)),interpolation=cv2.INTER_AREA)
    ok,encoded=cv2.imencode('.png',image);assert ok
    (tmp_path/'derived.png').write_bytes(encoded.tobytes())
    record=dict(raw,frame='derived',size=[width,image.shape[0]],image_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),
        derived_from=raw['image_sha256'],map_body_pan=list(pan))
    record['ocr']=[dict(r,box=[round(v*scale) for v in r['box']]) for r in raw['ocr']]
    (tmp_path/'derived.json').write_text(json.dumps(record),encoding='utf8')
    return record,original


@pytest.mark.parametrize('width',[1920,1280])
@pytest.mark.parametrize('pan',[(0,0),(100,30)])
def test_original_red_outline_white_edge_survives_scale_pan_and_dispatch_reach(width,pan,tmp_path):
    record,original=retained(tmp_path,width,pan);_,boxes=runner.candidates_of(tmp_path,record)
    assert len(boxes)==1;found=record['map_connected_step'];scale=width/1920
    expected=((1087+pan[0])*scale,(432+pan[1])*scale)
    assert all(abs(a-b)<6*scale for a,b in zip(found['point'],expected))
    assert found['bright_share']>=.70 and found['path_support']['warm_share']==0
    plan=plan_step('MAP',candidates=boxes);assert list(plan['target'])==boxes[0]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=record['map_party'],map_step_reach=record['map_step_reach'])
    assert loop._map_click_allowed(found['point'])
    assert not loop._map_click_allowed([found['point'][0]+383*scale,found['point'][1]])
    assert loop.device.clicks==[] and SOURCE.read_bytes()==original


def test_whole_runner_carries_measured_red_white_target_to_one_simulated_input(tmp_path,monkeypatch):
    record,_=retained(tmp_path)
    # Synthetic page-family successor exercises carrier/reach without claiming
    # the current boss was entered physically or naming its actual encounter.
    successor=dict(scene='NODE_PANEL',frame='synthetic-panel',size=[1920,1080],ocr=[])
    reads=iter([record,successor,successor]);device=runner.FakeDevice()
    device.controller=object()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(loop,'_prepare_view_change',lambda:True)
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a,**kw:None)
    result=loop.step()
    assert result['input_sent'] and not result['stopped'] and len(device.clicks)==1
    x,y=device.clicks[0];assert 1030<x<1140 and 390<y<470
    assert loop.artifacts['steps'][-1]['page_after']=='NODE_PANEL'


def test_actual_red_white_visible_goal_defers_viewport_gestures(tmp_path,monkeypatch):
    record,_=retained(tmp_path);device=runner.FakeDevice();device.controller=object()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings={})
    monkeypatch.setattr(loop,'_prepare_view_change',lambda:True)
    assert loop._normalise_view_once(record) is record
    assert loop.state['view_normalised'] is True
    assert not device.clicks and not device.swipes
    assert not loop.artifacts.get('last_step_sent')
