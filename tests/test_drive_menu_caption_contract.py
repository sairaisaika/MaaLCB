"""Mandatory old/new menu contracts, independent of retained-run availability."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from maalimbus.drive_menu_native import repair
from maalimbus.vision import Text,classify,drive_menu_probe,DRIVE_MIRROR_BAND
from maalimbus.native_gestures import frame_coordinates

ROOT=Path(__file__).resolve().parents[1]
LOCALE=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())


@pytest.mark.parametrize('size',[(1920,1080),(1280,720)])
@pytest.mark.parametrize('row',[185,270])
def test_old_and_event_layouts_request_detector_and_preserve_native_box(size,row):
    scale=lambda box:frame_coordinates(box,size)
    records=[Text('Luxcavation',scale((592,row,164,25)),.99)]
    image=np.zeros((size[1],size[0],3),np.uint8);calls=[]
    target=scale((640,318 if row==185 else 483,119,21))
    def native(kind,param,pixels):
        assert pixels is image
        calls.append(param)
        is_heading=len(calls)==1
        assert param.only_rec is is_heading and param.threshold==.9
        result=SimpleNamespace(text='Inferno' if is_heading else 'Dungeons',score=.99,box=target)
        return SimpleNamespace(hit=True,filtered_results=[result])
    out,proof=repair(native,image,records,LOCALE)
    assert classify(records,LOCALE,size)!='HOME'
    assert classify(out,LOCALE,size)=='DRIVE' and out[-1].box==target
    left,top,right,bottom=DRIVE_MIRROR_BAND
    assert proof[-1]['roi']==[round(left*size[0]),round(top*size[1]),round((right-left)*size[0]),round((bottom-top)*size[1])]


@pytest.mark.parametrize('box',[(0,0,50,20),(640,318,0,21),(640,318,-2,21),
    (1800,318,200,21),(640,318,119),None,(640.,318,119,21),(True,318,119,21)])
def test_detector_cannot_turn_invalid_or_off_band_box_into_a_control(box):
    records=[Text('Inferno',(1610,210,150,30),.99)]
    def native(*args):
        return SimpleNamespace(hit=True,filtered_results=[SimpleNamespace(text='Dungeons',score=.99,box=box)])
    out,proof=repair(native,np.zeros((1080,1920,3),np.uint8),records,LOCALE)
    assert out==records and not proof[0]['results']
    assert classify(out,LOCALE,(1920,1080))!='DRIVE'


@pytest.mark.parametrize('text,score',[('Dungeons',.89),('Under Construction',.999),('Dirror',.999)])
def test_wrong_or_weak_native_caption_never_grants_drive(text,score):
    records=[Text('Inferno',(1610,210,150,30),.99)]
    def native(*args):
        return SimpleNamespace(hit=True,filtered_results=[SimpleNamespace(text=text,score=score,box=(640,318,119,21))])
    out,proof=repair(native,np.zeros((1080,1920,3),np.uint8),records,LOCALE)
    assert out==records and not proof[0]['results']


def test_native_target_and_classifier_share_declared_menu_band():
    pipeline=json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_bytes())
    assert pipeline['MirrorDrive']['custom_recognition_param']['roi']==list(DRIVE_MIRROR_BAND)
