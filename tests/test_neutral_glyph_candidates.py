"""Mandatory shape guards plus individually optional, hash-bound retained cases."""
import json,hashlib
from pathlib import Path
import cv2
import numpy as np
import pytest
from maalimbus.map_vision import neutral_node_glyphs
from maalimbus.runner import candidates_of,box_key

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'evidence'/'runtime'/'packaged-mirror-20261119-040251'


# A question mark as pixels of our own, 30x40 with a four-row gap above the dot that the
# vertical close has to bridge.  cv2.putText is not a fixture: OpenCV 5 draws the Hershey
# '?' 23 px wide where 4.x drew 24, one pixel under the glyph's minimum width.
GLYPH=np.repeat(np.repeat(np.array([[0,1,1,1,0],
                                    [1,0,0,0,1],
                                    [0,0,0,0,1],
                                    [0,0,0,1,0],
                                    [0,0,1,0,0],
                                    [0,0,0,0,0],
                                    [0,0,1,0,0]],bool),[6,6,6,6,6,4,6],axis=0),6,axis=1)


def glyphs(image,points,color=(200,200,200)):
    """Stamp the glyph with its bottom-left corner at each point."""
    height,width=GLYPH.shape
    for x,y in points:image[y-height:y,x:x+width][GLYPH]=color
    return image


def test_repeated_small_neutral_glyphs_are_proposals_with_measured_boxes():
    image=glyphs(np.zeros((1080,1920,3),np.uint8),[(700,350),(700,510)])
    rows=neutral_node_glyphs(image)
    assert len(rows)==2
    assert all(695<r['point'][0]<740 and r['source']=='repeated_compact_neutral_glyph' for r in rows)


@pytest.mark.parametrize('fault',['single','header','roster','right_controls','colored','diagonal_paths'])
def test_proposals_need_repeated_compact_neutral_map_content(fault):
    image=np.zeros((1080,1920,3),np.uint8)
    if fault=='diagonal_paths':
        for y in (300,460):cv2.line(image,(700,y),(880,y+130),(220,220,220),6)
    else:
        points={'single':[(700,350)],'header':[(700,80),(700,160)],
                'roster':[(700,950),(700,1050)],'right_controls':[(1850,350),(1850,510)]}.get(fault,[(700,350),(700,510)])
        glyphs(image,points,(0,220,220) if fault=='colored' else (200,200,200))
    assert neutral_node_glyphs(image)==[]


@pytest.fixture
def retained(request):
    stem,point=request.param
    path=RUN/(stem+'.json')
    if not path.is_file() or not path.with_suffix('.png').is_file():
        pytest.skip('Retained event-layout run unavailable; mandatory shape checks still execute')
    record=json.loads(path.read_bytes());pixels=path.with_suffix('.png').read_bytes()
    assert hashlib.sha256(pixels).hexdigest()==record['image_sha256']
    return record,cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR),point


@pytest.mark.parametrize('retained',[
    ('frame-0036',(1087,409)),('frame-0043',(864,325)),('frame-0051',(288,445))],indirect=True)
@pytest.mark.parametrize('width',[1920,1280])
def test_full_candidate_chain_prefers_real_glyph_after_zoom_or_pan(retained,width,tmp_path):
    record,image,expected=retained
    scale=width/image.shape[1];height=round(image.shape[0]*scale)
    derived=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
    ok,encoded=cv2.imencode('.png',derived);assert ok
    (tmp_path/'derived.png').write_bytes(encoded.tobytes())
    record=dict(record,frame='derived',size=[width,height],image_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),
                derived_from=record['image_sha256'])
    record['ocr']=[dict(r,box=[round(v*scale) for v in r['box']]) for r in record['ocr']]
    (tmp_path/'derived.json').write_text(json.dumps(record),encoding='utf8')
    _,boxes=candidates_of(tmp_path,record)
    assert boxes
    x,y,w,h=boxes[0];point=(x+w/2,y+h/2)
    assert abs(point[0]-expected[0]*scale)<20*scale
    assert abs(point[1]-expected[1]*scale)<24*scale
    assert record['map_candidate_kinds'][box_key(boxes[0])]=='lit_icon'
    assert record['map_native_glyphs']


@pytest.mark.parametrize('retained',[('frame-0043',(864,325))],indirect=True)
def test_erasing_the_glyphs_keeps_bright_paths_but_removes_their_proposals(retained):
    _,image,_=retained;rows=neutral_node_glyphs(image);assert len(rows)==3
    absent=image.copy()
    for r in rows:
        x,y,w,h=r['box'];absent[y:y+h,x:x+w]=0
    assert neutral_node_glyphs(absent)==[]
