"""Internal map zoom is not capture size; a shop glyph is not a reward ornament."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus import map_node_geometry as geometry,map_vision,runner
from maalimbus.window import plan_step

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence'/'runtime'/'packaged-mirror-20261119-060820'/'frame-0163.json'


def fixture(monkeypatch,pitch=192,fault=None):
    image=np.zeros((1080,1920,3),np.uint8);party=(850,300)
    columns=[850-2*pitch,850-pitch,850]
    rows=[dict(kind='gold_badge_node',box=[x-95,y-95,190,190])
          for x,y in [(columns[0],309),(columns[1],309),(columns[1],309+160),(columns[2],309+160)]]
    if fault=='missing_columns':rows=[r for r in rows if r['box'][0]+95==columns[1]]
    if fault=='missing_rows':rows=[r for r in rows if r['box'][1]+95==309]
    if fault=='wrong_phase':
        for row in rows:row['box'][0]+=pitch/2
    monkeypatch.setattr(map_vision,'map_clicks',lambda *a,**kw:rows)
    monkeypatch.setattr(map_vision,'node_markers',lambda *a,**kw:[])
    monkeypatch.setattr(geometry,'train_body',lambda *a,**kw:None if fault=='missing_train' else {'party':party})
    target=(850+pitch,460)
    if fault=='two_steps':target=(850+2*pitch,460)
    if fault=='backwards':target=(850-pitch,460)
    def draw(point):
        cv2.line(image,(850,300),point,((170,)*3 if fault=='dim_path' else (240,)*3),5)
        angles=np.arange(6)*np.pi/3+np.pi/6
        ring=np.column_stack((point[0]+.17*pitch*np.cos(angles),point[1]+.17*pitch*np.sin(angles))).round().astype(np.int32)
        if fault!='missing_ring':cv2.polylines(image,[ring],True,(210,)*3,3)
        # Interior art is independent from the outer hexagon; no reward marker above it.
        cv2.rectangle(image,(point[0]-9,point[1]-6),(point[0]+9,point[1]-3),(230,)*3,-1)
        if fault=='solid_wash':cv2.fillPoly(image,[ring],(210,)*3)
    draw(target)
    if fault=='ambiguous':draw((850+pitch,300))
    return image,(850,300),target


@pytest.mark.parametrize('pitch',[192,384])
def test_shared_lattice_finds_unmarked_diagonal_endpoint_at_two_internal_zooms(monkeypatch,pitch):
    image,party,target=fixture(monkeypatch,pitch)
    found=geometry._connected_white_outline(image,party)
    assert found['point']==list(target) and found['measured_column_pitch']==pitch
    assert found['seed_source']=='train_calibrated_lattice'
    assert found['bright_share']>=.7 and found['lattice_measurement']['row_phase_shift']==-9


@pytest.mark.parametrize('fault',['missing_columns','missing_rows','wrong_phase','missing_train',
    'missing_ring','dim_path','solid_wash','two_steps','backwards','ambiguous'])
def test_missing_or_contradictory_graph_parts_do_not_grant_a_destination(monkeypatch,fault):
    image,party,_=fixture(monkeypatch,fault=fault)
    assert geometry._connected_white_outline(image,party) is None


@pytest.mark.parametrize('width',[1920,1280])
@pytest.mark.parametrize('pan',[(0,0),(150,50),(-150,-50)])
def test_actual_shop_endpoint_full_candidate_and_dispatch_chain(width,pan,tmp_path):
    if not SOURCE.is_file() or not SOURCE.with_suffix('.png').is_file():
        pytest.skip('Retained shop failure unavailable; mandatory zoom/role/graph checks still execute')
    original=SOURCE.read_bytes();record=json.loads(original);pixels=SOURCE.with_suffix('.png').read_bytes()
    assert hashlib.sha256(pixels).hexdigest()==record['image_sha256']
    image=cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR)
    dx,dy=pan;top,bottom=240,905
    image[top:bottom]=cv2.warpAffine(image[top:bottom],np.float32([[1,0,dx],[0,1,dy]]),(1920,bottom-top))
    scale=width/1920;image=cv2.resize(image,(width,round(1080*scale)),interpolation=cv2.INTER_AREA)
    ok,encoded=cv2.imencode('.png',image);assert ok
    (tmp_path/'derived.png').write_bytes(encoded.tobytes())
    derived=dict(record,frame='derived',size=[width,image.shape[0]],image_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),
        derived_from=record['image_sha256'],map_body_pan=list(pan))
    derived['ocr']=[dict(r,box=[round(v*scale) for v in r['box']]) for r in record['ocr']]
    (tmp_path/'derived.json').write_text(json.dumps(derived),encoding='utf8')
    _,boxes=runner.candidates_of(tmp_path,derived);assert len(boxes)==1
    found=derived['map_connected_step'];wanted=((1124+dx)*scale,(607+dy)*scale)
    assert all(abs(a-b)<6*scale for a,b in zip(found['point'],wanted))
    assert abs(found['measured_column_pitch']-192*scale)<3
    assert found['bright_share']>=.7 and found['seed_source']=='train_calibrated_lattice'
    plan=plan_step('MAP',candidates=boxes);assert list(plan['target'])==boxes[0]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=derived['map_party'],map_step_reach=derived['map_step_reach'])
    assert loop._map_click_allowed(found['point'])
    assert not loop._map_click_allowed([(1315+dx)*scale,(607+dy)*scale])
    assert not loop.device.clicks and SOURCE.read_bytes()==original
