"""Exercise the three dispatch routes, rather than counting `if` spellings."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from maalimbus import runner
from maalimbus.storage import write_json


@pytest.mark.parametrize('point,allowed', [([150,150],True),([151,150],False),([100,49],False)])
def test_one_step_boundary_uses_both_axes_without_sending_input(tmp_path,point,allowed):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=[100,100],map_step_reach={'reach':50})
    assert loop._map_click_allowed(point) is allowed
    assert loop.device.clicks==[]


@pytest.mark.parametrize('route',['planned','header_only','exploration'])
def test_each_map_dispatch_withholds_before_reserving_an_unsent_input(tmp_path,monkeypatch,route):
    record=dict(scene='MAP',frame='frame-0001',size=[1920,1080],image_sha256='x'*64,local_ocr=[],ocr=[
        dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
        dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)])
    if route=='header_only':
        record['scene']='UNKNOWN';record['ocr'].pop()
    write_json(tmp_path/'frame-0001.json',record)
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,
                             settings=dict(interval=0,rounds=1))
    loop.state.update(map_pending=None,map_committed=None)
    before={key:deepcopy(loop.state.get(key)) for key in ('map_pending','map_committed','map_click_frame')}
    checked=[]
    def refuse(point):checked.append(point);return False
    def forbidden(*a,**kw):pytest.fail('withheld input must not admit capacity or reserve an intent')
    monkeypatch.setattr(loop,'_map_click_allowed',refuse)
    # The normal planner may reserve evidence capacity before choosing an
    # in-box random point. Neither that storage admission nor a withheld
    # header/exploration proposal may become a game transaction.
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a,**kw:None if route=='planned' else forbidden())
    monkeypatch.setattr(loop,'_normalise_view_once',lambda r:None)
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    monkeypatch.setattr(loop,'_recover',lambda *a,**kw:loop._result(record['scene'],None,False,None,waiting=True))
    target=[1000,400,50,50]
    if route=='exploration':
        loop.store=SimpleNamespace(data={'active':{}})
        loop.exploration=SimpleNamespace(choose=lambda *a:dict(box=target,action='click'),reserve=forbidden)
        result=loop._explore_unknown(record,'frame-0001',[])
        assert result is None
    else:
        monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:('frame-0001.png',[target] if route=='planned' else []))
        monkeypatch.setattr(runner,'blind_map_boxes',lambda *a,**kw:[target])
        result=loop.step()
        assert result['waiting']
    assert checked, repr(result)
    assert loop.device.clicks==[] and loop.artifacts['clicks_sent']==0
    assert {key:loop.state.get(key) for key in before}==before
