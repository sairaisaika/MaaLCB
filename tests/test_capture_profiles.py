"""Sizing is a read policy, never permission to act on a small alternate page."""
import hashlib
import json

import cv2
import numpy as np
import pytest

from maalimbus.capture_geometry import frame_coordinates
from maalimbus.capture_profiles import BattleCaptureObserver
from maalimbus.runner import ReadNeverReturned


class Controller:
    def __init__(self, *, reject_small=False):
        self.side=1920;self.requests=[];self.reject_small=reject_small

    def set_screenshot_target_long_side(self,side):
        self.requests.append(side)
        if side==1280 and self.reject_small:return False
        self.side=side
        return True


class Observer:
    """Portable protocol fixture, not native OCR/model accuracy evidence."""
    def __init__(self,directory,controller,scenes,*,fault=None):
        self.directory=directory;self.controller=controller;self.scenes=iter(scenes)
        self.calls=[];self.last_image=None;self.tasker=object();self.fault=fault

    def observe(self,*,deadline=None,battle_hint=None):
        scene=next(self.scenes);index=len(self.calls)+1
        side=self.controller.side
        if self.fault=='wrong_full_size' and index==3:side=1280
        size=[side,side*9//16];self.calls.append((side,deadline,battle_hint))
        self.last_image=np.zeros((size[1],size[0],3),np.uint8)
        ok,png=cv2.imencode('.png',self.last_image);assert ok
        words=[('WAVE',[88,37,46,32]),('1/1',[150,37,40,32]),('TURN',[20,97,42,22]),
               ('3',[98,95,16,26]),('Win',[1486,796,40,20]),('Rate',[1492,818,44,20]),
               ('Damage',[1472,863,76,26])] if scene=='BATTLE_HUD' else []
        data=dict(scene=scene,size=size,image_sha256=hashlib.sha256(png).hexdigest(),
                  ocr=[dict(text=t,box=frame_coordinates(box,size),score=.99) for t,box in words])
        name='frame-%04d'%index;path=self.directory/(name+'.json')
        if self.fault!='missing':
            path.write_text(json.dumps(data));path.with_suffix('.png').write_bytes(png)
        event=dict(frame=name,scene=scene,image_sha256=data['image_sha256'])
        if self.fault=='bad_low_hash' and index==2:event['image_sha256']='0'*64
        if self.fault=='omit_event_hash':event.pop('image_sha256')
        return event


def make(directory,scenes,*,fault=None,reject_small=False):
    controller=Controller(reject_small=reject_small)
    raw=Observer(directory,controller,scenes,fault=fault);notes=[]
    observer=BattleCaptureObserver(raw,controller,note=lambda name,**kw:notes.append((name,kw)))
    return observer,raw,controller,notes


def test_only_a_bound_qualified_hud_opts_into_small_and_other_page_is_reread_full(tmp_path):
    obs,raw,controller,notes=make(tmp_path,['BATTLE_HUD','BATTLE_HUD','SHOP','SHOP'])
    assert obs.observe()['frame']=='frame-0001'
    assert obs.observe()['frame']=='frame-0002'
    # The caller's deadline is a moment on the real monotonic clock, and a read is also
    # capped at thirty seconds from now. A constant such as 12345 only stayed the
    # tighter of the two on a machine that had been up for hours: GitHub's runner,
    # 525 s after boot, received its own cap instead. Five seconds from now is inside
    # the cap on every machine.
    import time
    deadline=time.monotonic()+5.0
    final=obs.observe(deadline=deadline)
    assert final['frame']=='frame-0004' and final['scene']=='SHOP'
    assert [c[0] for c in raw.calls]==[1920,1280,1280,1920]
    assert [c[1] for c in raw.calls[-2:]]==[deadline,deadline]
    assert controller.requests==[1920,1280,1920]
    fallback=[v for k,v in notes if k=='capture_profile_full_reread']
    assert len(fallback)==1 and fallback[0]['input_sent'] is False
    assert fallback[0]['before_record'].endswith('frame-0003.json')
    assert fallback[0]['after_record'].endswith('frame-0004.json')


def test_nonbattle_and_missing_native_binding_never_enable_small(tmp_path):
    obs,raw,controller,_=make(tmp_path,['SHOP','BATTLE_HUD','BATTLE_HUD'],fault='missing')
    for _ in range(3):obs.observe()
    assert controller.requests==[1920]
    assert [c[0] for c in raw.calls]==[1920,1920,1920]


def test_event_without_hash_binds_its_named_original_pair_before_downsizing(tmp_path):
    obs,raw,_,_=make(tmp_path,['BATTLE_HUD','BATTLE_HUD'],fault='omit_event_hash')
    for _ in range(2):
        value=obs.observe()
        record=json.loads((tmp_path/(value['frame']+'.json')).read_text())
        assert value['image_sha256']==record['image_sha256'] and value['size']==record['size']
    assert [c[0] for c in raw.calls]==[1920,1280]


def test_bad_low_binding_gets_fresh_full_instead_of_borrowing_old_controls(tmp_path):
    obs,raw,_,_=make(tmp_path,['BATTLE_HUD','BATTLE_HUD','SHOP'],fault='bad_low_hash')
    obs.observe()
    result=obs.observe()
    assert result['scene']=='SHOP' and result['frame']=='frame-0003'
    assert [c[0] for c in raw.calls]==[1920,1280,1920]


def test_rejected_option_disables_optimization_without_replacing_controller(tmp_path):
    obs,raw,controller,_=make(tmp_path,['BATTLE_HUD']*3,reject_small=True)
    for _ in range(3):obs.observe()
    assert controller.requests==[1920,1280,1920]
    assert not obs.enabled and [c[0] for c in raw.calls]==[1920]*3


def test_unproven_full_fallback_cannot_reach_planner_or_change_pending(tmp_path):
    pending=tmp_path/'pending.json';pending.write_bytes(b'{"unknown_intent":"preserve"}')
    obs,raw,_,_=make(tmp_path,['BATTLE_HUD','SHOP','SHOP'],fault='wrong_full_size')
    obs.observe();planned=[]
    with pytest.raises(ReadNeverReturned,match='full capture'):
        planned.append(obs.observe())
    assert planned==[] and pending.read_bytes()==b'{"unknown_intent":"preserve"}'
    assert [c[0] for c in raw.calls]==[1920,1280,1280]


def test_full_fallback_failure_does_not_retry_or_extend_deadline(tmp_path):
    obs,raw,_,_=make(tmp_path,['BATTLE_HUD','UNKNOWN'])
    import time
    deadline=time.monotonic()+5.0   # inside the thirty-second read cap on any machine
    obs.observe();original=raw.observe
    def bounded(**kw):
        if len(raw.calls)==2:
            assert kw['deadline']==deadline
            raise TimeoutError('original deadline elapsed')
        return original(**kw)
    raw.observe=bounded
    with pytest.raises(TimeoutError,match='original deadline'):
        obs.observe(deadline=deadline)
    assert len(raw.calls)==2
