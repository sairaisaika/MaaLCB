from types import SimpleNamespace
import numpy as np
import pytest
from maalimbus.grace_balance_native import repair
from maalimbus.grace_vision import available_starlight
from maalimbus.vision import Text

def call(values):
    iterator=iter(values)
    def native(kind,config,image):
        assert config.only_rec is False
        value=next(iterator)
        rows=[] if value is None else [SimpleNamespace(text=str(value),score=.999)]
        return SimpleNamespace(hit=bool(rows),filtered_results=rows)
    return native

@pytest.mark.parametrize('number',[5,25,75,95,105,116,1000])
@pytest.mark.parametrize('size',[(1920,1080),(1280,720)])
def test_independent_detected_balance_agrees_without_changing_floor(number,size):
    from maalimbus.native_gestures import frame_coordinates
    label=Text('Avallable',frame_coordinates((1392,49,84,30),size),.99)
    records,proof=repair(call([number,number]),np.zeros((size[1],size[0],3)),[label])
    assert available_starlight(records,size)==number
    assert len(proof)==2

@pytest.mark.parametrize('values',[[75,70],[75,None],[None,None]])
def test_missing_or_conflicting_crops_do_not_prove_number(values):
    records,_=repair(call(values),np.zeros((1080,1920,3)),[Text('Available',(1392,49,84,30),.99)])
    assert available_starlight(records,(1920,1080)) is None

def test_detection_does_not_delete_a_conflicting_fullframe_number():
    records,_=repair(call([75,75]),np.zeros((1080,1920,3)),[
        Text('Available',(1392,49,84,30),.99),Text('7',(1520,45,30,40),.95)])
    assert available_starlight(records,(1920,1080)) is None

def test_missing_label_is_zero_native_call():
    records,proof=repair(lambda *a:pytest.fail('No anchor'),np.zeros((1080,1920,3)),[])
    assert records==[] and proof==[]


@pytest.mark.parametrize('label_score,count',[(.99,1),(.84,1),(.99,2)])
def test_partial_caption_only_requests_a_new_exact_native_label(label_score,count):
    calls=[]
    def native(kind,config,image):
        calls.append(config)
        rows=([SimpleNamespace(text='Available',score=label_score)]*count if config.only_rec
              else [SimpleNamespace(text='14',score=.999)])
        return SimpleNamespace(hit=True,filtered_results=rows)
    records,proof=repair(native,np.zeros((720,1280,3)),[Text('Availabl',(918,42,42,9),.95)])
    proven=label_score>=.85 and count==1
    assert available_starlight(records,(1280,720))==(14 if proven else None)
    assert len(calls)==(3 if proven else 1)
    assert proof[0]['purpose']=='available_starlight_label'
