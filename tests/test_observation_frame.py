"""Native observations keep one original pair; legacy replay is explicit."""
from dataclasses import FrozenInstanceError
import hashlib
import json

import cv2
import numpy as np
import pytest

from maalimbus.native_evidence import frame_reference,observation_frame
from maalimbus.runtime_contracts import FrameRef
from maalimbus import runner


def capture(directory,name='frame-0001',*,scene='UNKNOWN',utc='2026-11-18T00:00:00+00:00'):
    directory.mkdir(parents=True,exist_ok=True)
    ok,png=cv2.imencode('.png',np.zeros((16,24,3),np.uint8));assert ok
    raw=dict(frame=name,scene=scene,size=[24,16],utc=utc,
             image_sha256=hashlib.sha256(png).hexdigest(),
             ocr=[dict(text=scene,box=[1,1,10,5],score=.93)],
             local_ocr=[dict(purpose='own_crop',results=[])])
    if utc is None:raw.pop('utc')
    path=directory/(name+'.json');path.write_text(json.dumps(raw),encoding='utf8')
    path.with_suffix('.png').write_bytes(png)
    return path,raw


class Reader:
    requires_frame_ref=True
    def __init__(self,directory,event):self.directory=directory;self.event=event
    def observe(self,*,deadline=None):return dict(self.event)


def test_named_native_event_never_borrows_newer_page_hash_tokens_or_size(tmp_path):
    path,raw=capture(tmp_path,scene='BATTLE_HUD')
    capture(tmp_path,'frame-0002',scene='SHOP')
    event=dict(frame=path.stem,scene='BATTLE_HUD',utc='2026-11-18T01:00:00+00:00')
    result=runner.observe(Reader(tmp_path,event))
    assert result['ocr']==raw['ocr'] and result['local_ocr']==raw['local_ocr']
    assert result['image_sha256']==raw['image_sha256'] and result['size']==[24,16]
    assert result['frame_ref']['json_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['frame_ref']['record_path']==str(path.resolve())
    assert result['frame_ref']['captured_at']==raw['utc']
    assert result['utc']==event['utc'] and 'ocr' not in event


def test_shared_reference_is_immutable_but_not_a_domain_verdict(tmp_path):
    path,raw=capture(tmp_path)
    reference,record=frame_reference(path)
    assert isinstance(reference,FrameRef) and reference.size==(24,16)
    assert record==raw and reference.as_dict()['size']==[24,16]
    assert not hasattr(reference,'outcome') and not hasattr(reference,'input_authorized')
    with pytest.raises(FrozenInstanceError):reference.frame_id='frame-9999'
    encoded=reference.as_dict();encoded['size'][0]=9
    assert reference.size==(24,16)


def test_equal_pixels_do_not_merge_capture_or_session_identity(tmp_path):
    a,_=capture(tmp_path/'a')
    b,_=capture(tmp_path/'a','frame-0002',utc='2026-11-18T00:00:01+00:00')
    c,_=capture(tmp_path/'b')
    refs=[frame_reference(p)[0] for p in (a,b,c)]
    assert len({r.png_sha256 for r in refs})==1
    assert len(set(refs))==3


def test_historical_missing_capture_time_remains_unknown(tmp_path):
    path,_=capture(tmp_path,utc=None)
    event,ref,_=observation_frame(tmp_path,dict(frame=path.name,scene='UNKNOWN'))
    assert ref.captured_at is None and event['frame_ref']['captured_at'] is None
    assert 'utc' not in event and event['scene']=='UNKNOWN'


def test_domain_unreadable_hypothesis_is_not_overwritten_by_frame_binding(tmp_path):
    path,_=capture(tmp_path,scene='UNKNOWN')
    event=dict(frame=path.stem,scene='BATTLE_HUD',battle_scene='UNKNOWN',battle_read='unreadable')
    result=runner.observe(Reader(tmp_path,event))
    assert result['scene']=='BATTLE_HUD' and result['battle_read']=='unreadable'


@pytest.mark.parametrize('fault',[
    'missing_json','missing_png','broken_json','changed_png','wrong_size',
    'wrong_frame','wrong_event_hash','wrong_event_size','wrong_ocr','wrong_local',
    'wrong_ref','changed_json_after_ref','naive_time','invalid_time'])
def test_missing_changed_or_conflicting_native_proof_never_borrows_latest_or_repairs_pending(tmp_path,fault):
    path,raw=capture(tmp_path,scene='BATTLE_HUD')
    capture(tmp_path,'frame-0002',scene='SHOP')
    event=dict(frame=path.stem,scene='BATTLE_HUD')
    pending=tmp_path/'pending.json';pending.write_bytes(b'{"unjudged":"retain"}')
    if fault=='missing_json':path.unlink()
    elif fault=='missing_png':path.with_suffix('.png').unlink()
    elif fault=='broken_json':path.write_text('{')
    elif fault=='changed_png':path.with_suffix('.png').write_bytes(b'not the original PNG')
    elif fault in ('wrong_size','wrong_frame','naive_time','invalid_time'):
        key,value={'wrong_size':('size',[12,16]),'wrong_frame':('frame','frame-9999'),
                   'naive_time':('utc','2026-11-18T00:00:00'),'invalid_time':('utc','yesterday')}[fault]
        raw[key]=value;path.write_text(json.dumps(raw))
    elif fault=='wrong_event_hash':event['image_sha256']='f'*64
    elif fault=='wrong_event_size':event['size']=[48,32]
    elif fault=='wrong_ocr':event['ocr']=[dict(text='SHOP',score=.99,box=[1,1,10,5])]
    elif fault=='wrong_local':event['local_ocr']=[dict(purpose='foreign_crop')]
    elif fault=='wrong_ref':event['frame_ref']={'frame_id':'frame-9999'}
    elif fault=='changed_json_after_ref':
        event['frame_ref']=frame_reference(path)[0].as_dict()
        raw['utc']='2026-11-18T00:00:01+00:00';path.write_text(json.dumps(raw))
    with pytest.raises(runner.ReadNeverReturned,match='frame binding'):
        runner.observe(Reader(tmp_path,event))
    assert pending.read_bytes()==b'{"unjudged":"retain"}'


@pytest.mark.parametrize('name',[None,'','../frame-0001','C:\\frame-0001','frame-0001.txt','other'])
def test_native_frame_selector_cannot_default_to_latest(tmp_path,name):
    capture(tmp_path)
    with pytest.raises(runner.ReadNeverReturned):
        runner.observe(Reader(tmp_path,dict(frame=name,scene='UNKNOWN')))


def test_legacy_unnamed_frame_observer_is_not_promoted_to_native_reference(tmp_path):
    reader=runner.FrameObserver(tmp_path,[dict(scene='MAP',size=[24,16],ocr=[])])
    result=runner.observe(reader)
    assert result['scene']=='MAP' and 'frame_ref' not in result


def test_named_legacy_metadata_has_no_latest_fallback_or_fake_reference(tmp_path):
    path,raw=capture(tmp_path)
    capture(tmp_path,'frame-0002',scene='SHOP')
    reader=Reader(tmp_path,dict(frame=path.stem,scene='UNKNOWN'));reader.requires_frame_ref=False
    assert runner.observe(reader)['ocr']==raw['ocr']
    path.unlink()
    result=runner.observe(reader)
    assert 'ocr' not in result and 'frame_ref' not in result


@pytest.mark.parametrize('field,value',[
    ('frame_id','other'),('record_path',''),('json_sha256','x'*64),('png_sha256',None),
    ('size',[24,16]),('size',(True,16)),('size',(0,16)),('captured_at','2026-11-18')])
def test_frame_reference_structure_cannot_default_missing_fields_to_success(tmp_path,field,value):
    path,_=capture(tmp_path);reference,_=frame_reference(path)
    from dataclasses import replace
    with pytest.raises(ValueError):replace(reference,**{field:value})
