"""Independent neutral ring/path/pitch proof; no widened distance fallback."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus import map_node_geometry as geometry,map_vision,runner
from maalimbus.window import plan_step

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'evidence'/'runtime'/'packaged-mirror-20261119-044504'


def marker(x,y):
    return map_vision.NodeMarker((x-20,y-74,40,40),(x-95,y-95,190,190))


def ring(image,x,y,value=210):
    angles=np.arange(6)*np.pi/3+np.pi/6
    points=np.column_stack((x+51*np.cos(angles),y+51*np.sin(angles))).round().astype(np.int32)
    cv2.polylines(image,[points],True,(value,)*3,3)


def scene(monkeypatch,fault=None):
    image=np.zeros((1080,1920,3),np.uint8)
    markers=[marker(900,400),marker(1200,400)]
    if fault=='one_column':markers=markers[:1]
    if fault=='ambiguous':markers.append(marker(900,600))
    monkeypatch.setattr(map_vision,'node_markers',lambda *a,**kw:markers)
    body=None if fault=='no_train' else {'party':[700 if fault=='conflicting_train' else 600,400]}
    monkeypatch.setattr(geometry,'train_body',lambda *a,**kw:body)
    target=(1200,400) if fault=='two_steps' else (900,400)
    cv2.line(image,(600,400),target,((170,)*3 if fault=='dim_path' else (240,)*3),5)
    ring(image,*target,100 if fault=='dim_ring' else 210)
    if fault=='ambiguous':
        cv2.line(image,(600,400),(900,600),(240,)*3,5);ring(image,900,600)
    if fault=='missing_path':image[390:411,680:825]=0
    if fault=='missing_ring':image[335:465,835:965]=0
    if fault=='solid_wash':image[335:465,835:965]=200
    return image


def test_neutral_ring_uses_independent_columns_and_one_bright_outgoing_path(monkeypatch):
    found=geometry._connected_white_outline(scene(monkeypatch),(600,400))
    assert found and found['point']==[900,400] and found['measured_column_pitch']==300
    assert found['bright_share']>=.7 and 'warm_share' not in found
    assert found['step']>1.9*found['target'][2]


@pytest.mark.parametrize('fault',['one_column','no_train','conflicting_train','two_steps','ambiguous',
    'dim_path','dim_ring','missing_path','missing_ring','solid_wash'])
def test_each_missing_or_conflicting_independent_measurement_withholds_shortcut(monkeypatch,fault):
    assert geometry._connected_white_outline(scene(monkeypatch,fault),(600,400)) is None


@pytest.fixture
def retained(request):
    stem,point=request.param;path=RUN/(stem+'.json')
    if not path.is_file() or not path.with_suffix('.png').is_file():
        pytest.skip('Retained white-path run unavailable; mandatory independent-part checks still execute')
    before=path.read_bytes();record=json.loads(before);pixels=path.with_suffix('.png').read_bytes()
    assert hashlib.sha256(pixels).hexdigest()==record['image_sha256']
    return path,before,record,cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR),point


@pytest.mark.parametrize('retained',[
    ('frame-0042',(1088,819)),('frame-0048',(1197,784)),('frame-0050',(1197,784))],indirect=True)
@pytest.mark.parametrize('width',[1920,1280])
def test_hash_bound_full_candidate_chain_and_dispatch_gate_use_measured_pitch(retained,width,tmp_path):
    path,before,record,image,point=retained;scale=width/image.shape[1]
    image=cv2.resize(image,(width,round(image.shape[0]*scale)),interpolation=cv2.INTER_AREA)
    ok,encoded=cv2.imencode('.png',image);assert ok
    (tmp_path/'derived.png').write_bytes(encoded.tobytes())
    derived=dict(record,frame='derived',size=[image.shape[1],image.shape[0]],
        image_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),derived_from=record['image_sha256'])
    derived['ocr']=[dict(r,box=[round(v*scale) for v in r['box']]) for r in record['ocr']]
    (tmp_path/'derived.json').write_text(json.dumps(derived),encoding='utf8')
    _,boxes=runner.candidates_of(tmp_path,derived)
    assert len(boxes)==1
    found=derived['map_connected_step']
    assert all(abs(a-b*scale)<6*scale for a,b in zip(found['point'],point))
    assert abs(found['measured_column_pitch']-384*scale)<3
    assert found['bright_share']>=.7 and 'warm_share' not in found
    plan=plan_step('MAP',candidates=boxes);assert list(plan['target'])==boxes[0]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=derived['map_party'],map_step_reach=derived['map_step_reach'])
    assert loop._map_click_allowed(found['point'])
    assert not loop._map_click_allowed([found['point'][0]+384*scale,found['point'][1]])
    assert loop.device.clicks==[] and path.read_bytes()==before


@pytest.mark.parametrize('retained',[('frame-0050',(1197,784))],indirect=True)
@pytest.mark.parametrize('part,box,value',[
    ('path',(900,760,220,45),170),('ring',(1126,740,145,145),0),
    ('flame',(790,625,45,45),0),('independent_column',(1540,680,95,80),0)])
def test_actual_pixels_without_an_independent_part_do_not_invent_a_connected_node(retained,part,box,value):
    _,_,_,image,_=retained;x,y,w,h=box;image[y:y+h,x:x+w]=value
    assert geometry._connected_white_outline(image,(813,779),template=runner.node_badge_template()) is None
