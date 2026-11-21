"""Retained shared navigation is never enough to turn the mode menu into HOME."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json
import numpy as np
import pytest
from maalimbus import drive_menu_native as menu
from maalimbus.vision import Text,classify,drive_menu_probe
from maalimbus.native_gestures import frame_coordinates

ROOT=Path(__file__).resolve().parents[1]
LOCALE=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())
RUN=ROOT/'evidence/runtime/packaged-mirror-20261118-190145'
# Per test, not per module: the unanchored-read test below needs no frame.
needs_run=pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261118-190145')


def retained(run,name):
    p=run/(name+'.json');v=json.loads(p.read_bytes())
    assert hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest()==v['image_sha256']
    return v,[Text(t['text'],tuple(t['box']),t['score']) for t in v['ocr']]


@needs_run
@pytest.mark.parametrize('name',['frame-0018','frame-0019','frame-0020','frame-0022'])
def test_current_native_mode_frames_keep_their_content_owner(name):
    v,records=retained(RUN,name)
    assert drive_menu_probe(records,LOCALE,v['size'])
    assert classify(records,LOCALE,v['size'])!='HOME'


@needs_run
@pytest.mark.parametrize('size',[(1920,1080),(1280,720)])
def test_split_heading_requests_only_same_image_native_crops_then_full_guards(size):
    v,records=retained(RUN,'frame-0019');records=[Text(t.text,frame_coordinates(t.box,size),t.score) for t in records]
    image=np.zeros((size[1],size[0],3),np.uint8);calls=[]
    def native(kind,param,pixels):
        assert pixels is image
        calls.append(param)
        assert param.only_rec is (len(calls)==1)
        row=SimpleNamespace(text='Inferno' if len(calls)==1 else 'Dungeons',score=.999,
                            box=frame_coordinates((634,483,90,18),size))
        return SimpleNamespace(hit=True,filtered_results=[row])
    repaired,proof=menu.repair(native,image,records,LOCALE)
    assert classify(repaired,LOCALE,size)=='DRIVE'
    assert len(calls)==2 and [p['purpose'] for p in proof]==['drive_inferno_caption','drive_mirror_caption']
    assert repaired[-1].box==frame_coordinates((634,483,90,18),size)
    assert [p['only_rec'] for p in proof]==[True,False]
    assert all(p['threshold']==.9 and p['results'] for p in proof)
    assert classify(records,LOCALE,size)!='DRIVE'


@pytest.mark.parametrize('fault',['absent','low_score','wrong_caption','wrong_roi'])
def test_missing_or_weak_independent_menu_anchor_is_zero_native_calls(fault):
    text='Luxcavation' if fault!='wrong_caption' else 'Lux'
    box=(592,270,164,25) if fault!='wrong_roi' else (50,50,164,25)
    records=[] if fault=='absent' else [Text(text,box,.89 if fault=='low_score' else .99)]
    image=np.zeros((1080,1920,3),np.uint8)
    result,proof=menu.repair(lambda *a:pytest.fail('Unanchored mode read'),image,records,LOCALE)
    assert result==records and proof==[]


@needs_run
@pytest.mark.parametrize('fault',['missing','below_threshold','partial'])
def test_a_probe_or_bad_native_caption_never_proves_the_drive_page(fault):
    v,records=retained(RUN,'frame-0019')
    def native(*a):
        rows=[] if fault=='missing' else [SimpleNamespace(text='Inferno' if fault=='below_threshold' else 'nferno',score=.79 if fault=='below_threshold' else .999)]
        return SimpleNamespace(hit=bool(rows),filtered_results=rows)
    out,proof=menu.repair(native,np.zeros((1080,1920,3),np.uint8),records,LOCALE)
    assert classify(out,LOCALE,v['size'])=='UNKNOWN'
    assert not any(p['results'] for p in proof)


@needs_run
def test_complete_heading_keeps_one_existing_mirror_crop():
    v,records=retained(RUN,'frame-0018');calls=[]
    def native(kind,param,image):
        calls.append(param);return SimpleNamespace(hit=True,filtered_results=[SimpleNamespace(text='Dungeons',score=.99,box=(634,483,90,18))])
    out,proof=menu.repair(native,np.zeros((1080,1920,3),np.uint8),records,LOCALE)
    assert classify(out,LOCALE,v['size'])=='DRIVE'
    assert len(calls)==1 and proof[0]['purpose']=='drive_mirror_caption'
    assert not calls[0].only_rec
