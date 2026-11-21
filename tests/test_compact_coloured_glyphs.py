"""Real compact-blue board, themed variants and shared consumer handoffs."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus import map_node_geometry as geometry,runner

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence/runtime/packaged-mirror-20261119-074547/frame-0121.json'


def retained(tmp_path,width=1920,pan=(0,0),hue=None,source=SOURCE):
    if not source.is_file():pytest.skip('Original blue failure not retained on this host')
    original=source.read_bytes();record=json.loads(original)
    pixels=source.with_suffix('.png').read_bytes()
    assert hashlib.sha256(pixels).hexdigest()==record['image_sha256']
    image=cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR)
    if hue is not None:
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        mask=(hsv[:,:,0]>=90)&(hsv[:,:,0]<=130)&(hsv[:,:,1]>=100)
        mask[:260]=False;mask[900:]=False;hsv[:,:,0][mask]=hue
        image=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    dx,dy=pan;image[260:900]=cv2.warpAffine(image[260:900],np.float32([[1,0,dx],[0,1,dy]]),(1920,640))
    scale=width/1920;image=cv2.resize(image,(width,round(1080*scale)),interpolation=cv2.INTER_AREA)
    ok,encoded=cv2.imencode('.png',image);assert ok
    (tmp_path/'derived.png').write_bytes(encoded.tobytes())
    record.update(frame='derived',size=[width,image.shape[0]],image_sha256=hashlib.sha256(encoded.tobytes()).hexdigest())
    record['ocr']=[dict(r,box=[round(v*scale) for v in r['box']]) for r in record['ocr']]
    (tmp_path/'derived.json').write_text(json.dumps(record),encoding='utf8')
    return image,record,original


@pytest.mark.parametrize('width',[1920,1280])
@pytest.mark.parametrize('pan',[(0,0),(80,-20)])
@pytest.mark.parametrize('hue',[None,0,30,85])
def test_compact_body_proposal_survives_internal_zoom_resolution_pan_and_theme(tmp_path,width,pan,hue):
    image,record,original=retained(tmp_path,width,pan,hue)
    found=geometry.connected_compact_nodes(image)
    assert len(found)==1
    scale=width/1920;point=((1054+pan[0])*scale,(594+pan[1])*scale)
    assert all(abs(a-b)<6*scale for a,b in zip(found[0]['point'],point))
    assert found[0]['saturated_share']>=.70 and found[0]['body']['box'][2]<40*scale
    _,boxes=runner.candidates_of(tmp_path,record)
    assert boxes and record['map_connected_step']['source']=='train_body_and_supported_compact_glyph'
    assert SOURCE.read_bytes()==original


@pytest.mark.parametrize('fault',['train','grey','body','edge'])
def test_a_compact_body_cannot_supply_its_own_missing_train_or_edge(tmp_path,fault):
    image,_,_=retained(tmp_path)
    if fault=='train':image[530:655,830:897]=0
    elif fault=='body':image[573:642,1018:1092]=0
    elif fault=='edge':image[580:628,925:1015]=0
    else:
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        mask=(hsv[:,:,0]>=90)&(hsv[:,:,0]<=130);hsv[:,:,1][mask]=0
        image=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    assert geometry.connected_compact_nodes(image)==[]


def test_visible_compact_destination_skips_view_gestures_then_uses_the_real_step_carrier(tmp_path,monkeypatch):
    _,record,_=retained(tmp_path);device=runner.FakeDevice();device.controller=object()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    monkeypatch.setattr(loop,'_prepare_view_change',lambda:True)
    assert loop._normalise_view_once(record) is record
    assert not device.swipes and not device.clicks
    successor=dict(scene='NODE_PANEL',frame='synthetic-panel',size=[1920,1080],ocr=[])
    reads=iter([record,successor,successor]);monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a,**kw:None)
    result=loop.step()
    assert result['input_sent'] and not result['stopped'] and len(device.clicks)==1
    x,y=device.clicks[0];assert 1035<x<1075 and 578<y<610


def test_multiple_supported_bodies_stay_alternatives_not_a_claim_of_one_identity(monkeypatch):
    image=np.zeros((1080,1920,3),np.uint8)
    monkeypatch.setattr(geometry,'connected_red_node',lambda image:None)
    monkeypatch.setattr(geometry,'connected_ring_node',lambda image,**kw:None)
    choices=[dict(target=[800,400,27,24],step=190),dict(target=[800,560,27,24],step=245)]
    monkeypatch.setattr(geometry,'connected_compact_nodes',lambda image:choices)
    assert geometry.connected_nodes(image)==choices
    assert geometry.connected_node(image) is None


LARGE=ROOT/'evidence/runtime/packaged-mirror-20261119-091739/frame-0124.json'


@pytest.mark.parametrize('width',[1920,1280])
@pytest.mark.parametrize('pan',[(0,0),(70,20)])
@pytest.mark.parametrize('hue',[None,0,30,85])
def test_large_internal_zoom_body_uses_lamps_not_click_box_or_screen_width(tmp_path,width,pan,hue):
    image,record,original=retained(tmp_path,width,pan,hue,source=LARGE)
    name,boxes=runner.candidates_of(tmp_path,record)
    assert name and len(boxes)==1
    found=record['map_connected_step'];scale=width/1920
    expected=((1087+pan[0])*scale,(418+pan[1])*scale)
    assert all(abs(a-b)<6*scale for a,b in zip(found['point'],expected))
    assert found['saturated_share']>=.70
    assert found['body']['box'][2]>70*scale
    assert 5<found['step']/found['lamp_gap']<6
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=record['map_party'],map_step_reach=record['map_step_reach'])
    assert loop._map_click_allowed(found['point'])
    assert not loop._map_click_allowed([found['point'][0]+383*scale,found['point'][1]])
    assert LARGE.read_bytes()==original


@pytest.mark.parametrize('fault',['train','body','grey','edge'])
def test_large_body_keeps_independent_proof_requirements(tmp_path,fault):
    image,_,_=retained(tmp_path,source=LARGE)
    if fault=='train':image[275:458,635:780]=0
    elif fault=='body':image[375:495,1010:1160]=0
    elif fault=='edge':image[375:485,830:1010]=0
    else:
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        mask=(hsv[:,:,0]>=90)&(hsv[:,:,0]<=130);hsv[:,:,1][mask]=0
        image=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    assert geometry.connected_compact_nodes(image)==[]


def test_large_zoom_visible_goal_has_one_shared_normalization_dispatch_contract(tmp_path,monkeypatch):
    _,record,_=retained(tmp_path,source=LARGE)
    device=runner.FakeDevice();device.controller=object()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    monkeypatch.setattr(loop,'_prepare_view_change',lambda:True)
    assert loop._normalise_view_once(record) is record
    assert not device.clicks and not device.swipes
    successor=dict(scene='NODE_PANEL',frame='synthetic-large-panel',size=[1920,1080],ocr=[])
    reads=iter([record,successor,successor]);monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a,**kw:None)
    result=loop.step()
    assert result['input_sent'] and not result['stopped'] and len(device.clicks)==1
    x,y=device.clicks[0];assert 1050<x<1130 and 390<y<450


@pytest.mark.parametrize('gap',[35,70])
def test_body_size_follows_independent_internal_scale_without_retained_files(monkeypatch,gap):
    image=np.zeros((1080,1920,3),np.uint8)
    party=(500,450);target=(round(500+5.5*gap),450)
    monkeypatch.setattr(geometry,'train_body',lambda im:dict(party=list(party),lamp_gap=gap))
    cv2.line(image,party,target,(240,120,20),5)
    # Break the body/path connected component just before the glyph, outside
    # the middle half whose independent support the reader actually measures.
    cv2.line(image,(target[0]-gap,450),(target[0],450),(0,0,0),9)
    bw,bh=round(1.35*gap),round(.8*gap)
    cv2.rectangle(image,(target[0]-bw//2,450-bh//2),(target[0]+bw//2,450+bh//2),(240,120,20),4)
    rows=geometry.connected_compact_nodes(image)
    assert len(rows)==1 and abs(rows[0]['point'][0]-target[0])<3


def test_nested_theme_glow_pairs_do_not_duplicate_one_clock_but_two_trains_still_refuse(tmp_path):
    image,_,_=retained(tmp_path,hue=30,source=LARGE)
    found=geometry.train_body(image)
    assert found and 65<found['lamp_gap']<75
    assert abs(found['party'][0]-704)<4 and abs(found['party'][1]-431)<4
    image[275:458,180:325]=image[275:458,635:780].copy()
    assert geometry.train_body(image) is None
    assert geometry.connected_compact_nodes(image)==[]
