"""Search geometry supports capture sizes but never supplies an identity class."""
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from maalimbus import neural_shadow
from maalimbus.capture_geometry import analysis_image
from maalimbus.native_evidence import bound_frame

ROOT=Path(__file__).resolve().parents[1]
FRAME=ROOT/'evidence/runtime/packaged-mirror-20261117-124654/frame-0004.json'


def retained(side):
    if not FRAME.is_file() or not FRAME.with_suffix('.png').is_file():
        pytest.skip('retained private pre-battle frame is not distributed')
    _,record=bound_frame(FRAME);image=cv2.imread(str(FRAME.with_suffix('.png')))
    scale=side/image.shape[1]
    record['size']=[side,side*9//16]
    for text in record['ocr']:text['box']=[round(v*scale) for v in text['box']]
    return cv2.resize(image,tuple(record['size']),interpolation=cv2.INTER_AREA),record


def synthetic_search_layout(side):
    """Geometry fixture only; it contains no sinner artwork or model truth."""
    image=np.zeros((1080,1920,3),np.uint8)
    for n in range(12):
        x,y=350+n%6*198,225+n//6*298
        cv2.rectangle(image,(x,y),(x+185,y+273),(0,210,255),6)
    scale=side/1920
    record=dict(scene='PRE_BATTLE_TEAM',size=[side,side*9//16],ocr=[
        dict(text=word,box=[round(v*scale) for v in box],score=.99)
        for word,box in [('Details',[1360,172,78,28]),('Battle!',[1672,859,146,44])]])
    return cv2.resize(image,tuple(record['size']),interpolation=cv2.INTER_AREA),record


@pytest.mark.parametrize('side',[1280,1920])
def test_retained_native_page_has_twelve_measured_capture_space_search_regions(side):
    image,record=retained(side)
    rois=neural_shadow.verified_card_rois(image,record)
    assert len(rois)==12
    for row in rois:
        x,y,w,h=row['roi']
        assert 0<=x<x+w<=side and 0<=y<y+h<=image.shape[0]
        assert min(row['border_scores'].values())>=.72
        assert row['analysis_size']==[1920,1080]
        assert row['class_source']=='native_neural_only_not_grid_position'
        assert 'class_id' not in row and 'label' not in row


@pytest.mark.parametrize('side',[1280,1920])
@pytest.mark.parametrize('fault',['wrong_page','missing_details','missing_battle','wrong_size'])
def test_mechanical_resize_cannot_replace_own_page_evidence(side,fault):
    image,record=retained(side)
    if fault=='wrong_page':record['scene']='GIFT_PICK'
    elif fault=='wrong_size':record['size']=[640,360]
    else:
        key='Details' if fault=='missing_details' else 'Battle'
        record['ocr']=[t for t in record['ocr'] if key.lower() not in t['text'].lower()]
    assert neural_shadow.verified_card_rois(image,record)==[]


@pytest.mark.parametrize('side',[1280,1920])
@pytest.mark.parametrize('edge',['left','right','top','bottom'])
def test_erasing_any_one_visible_edge_removes_its_search_authority(side,edge):
    image,record=retained(side)
    first=neural_shadow.verified_card_rois(image,record)[0]
    x,y,w,h=first['measured_boundary'];strip=round(24*side/1920)
    if edge in ('left','right'):
        cx=x if edge=='left' else x+w
        image[y:y+h,max(0,cx-strip):cx+strip]=0
    else:
        cy=y if edge=='top' else y+h
        image[max(0,cy-strip):cy+strip,x:x+w]=0
    assert first['grid_slot'] not in [r['grid_slot'] for r in neural_shadow.verified_card_rois(image,record)]


def test_native_model_receives_the_original_capture_and_owns_the_class(tmp_path,monkeypatch):
    image,record=synthetic_search_layout(1280)
    (tmp_path/'neural-learning.json').write_text(json.dumps(dict(mode='shadow',roi_mode='verified_card_edges')))
    monkeypatch.setattr(neural_shadow,'verified_model',lambda *a:('isolated-unit-model',{},dict(quality_passed=False)))
    calls=[]
    class Context:
        def run_recognition_direct(self,kind,param,pixels):
            assert pixels is image,'Interpolated analysis must not become model input'
            calls.append(param.roi)
            rows=([SimpleNamespace(cls_index=3,box=param.roi,score=.99)] if len(calls)==1 else [])
            return SimpleNamespace(hit=bool(rows),filtered_results=rows)
    value=neural_shadow.observe(Context(),image,tmp_path,record=record)
    assert len(calls)==12 and value['native_inference_executed']
    assert value['boxes'][0]['class_id']==3  # first grid slot is not the class
    assert value['native_quality_passed'] is False
    assert value['training_eligible'] is False and value['input_authorized'] is False


@pytest.mark.parametrize('side',[1280,1920])
def test_portable_four_edge_geometry_still_requires_own_page_captions(side):
    image,record=synthetic_search_layout(side)
    assert len(neural_shadow.verified_card_rois(image,record))==12
    record['ocr']=[]
    assert neural_shadow.verified_card_rois(image,record)==[]


def test_unsupported_shape_is_not_silently_stretched_into_a_supported_profile():
    assert analysis_image(np.zeros((768,1024,3),np.uint8)) is None
