"""A named title flow must execute through the free-function Maa dispatch path."""
from types import SimpleNamespace
import time
import pytest
from maalimbus import runner
from maalimbus.session_flow import flow


def test_actual_flow_dispatch_has_no_undefined_runner_owner_and_touches_once(tmp_path,monkeypatch):
    before=dict(scene='UNKNOWN',size=[1920,1080],image_sha256='before',ocr=[
        dict(text='TOUCHTOSTART',box=[844,802,224,51],score=.998)])
    after=dict(scene='HOME',size=[1920,1080],image_sha256='after',ocr=[])
    records=iter([before,after]);events=[];points=[]
    observer=SimpleNamespace(observe=lambda **kw:next(records),directory=tmp_path)
    controller=SimpleNamespace(id='owned',post_click=lambda *p:points.append(p) or 'job')
    journal=SimpleNamespace(record=lambda n,**f:events.append((n,f)))
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    def dispatch(c,job,**kw):
        assert c is controller and job=='job'
        kw['on_soft']('isolated soft observation')
    monkeypatch.setattr(runner,'dispatch',dispatch)
    result=runner.run_flow(None,controller,journal,tmp_path,time.monotonic()+10,
                           [flow('launch')[2]],observer=observer,rounds=1)
    assert result[0]['passed'] and result[0]['clicks']==1 and len(points)==1
    intent=next(f for n,f in events if n=='flow_intent')
    x,y=points[0];bx,by,bw,bh=intent['target']
    assert bx<=x<bx+bw and by<=y<by+bh and 350<=intent['delay_ms']<=750
    assert any(n=='window_intent_soft' for n,_ in events)


def test_flow_observe_only_does_not_touch_even_a_readable_title(tmp_path):
    record=dict(scene='UNKNOWN',size=[1920,1080],image_sha256='before',ocr=[
        dict(text='TOUCHTOSTART',box=[844,802,224,51],score=.998)])
    observer=SimpleNamespace(observe=lambda **kw:record,directory=tmp_path)
    controller=SimpleNamespace(post_click=lambda *p:pytest.fail('read-only click'))
    result=runner.run_flow(None,controller,SimpleNamespace(),tmp_path,time.monotonic()+10,
                           [flow('launch')[2]],observer=observer,observe_only=True)
    assert result[0]['reason']=='observe_only'


@pytest.mark.parametrize('gesture',['click','swipe'])
def test_one_shot_successor_logging_uses_the_native_journal_record_interface(tmp_path,monkeypatch,gesture):
    readings=iter([dict(scene='RESUME_DIALOG',image_sha256='before'),
                   dict(scene='MIRROR_ENTRY',image_sha256='after')])
    observer=SimpleNamespace(observe=lambda **kw:next(readings),directory=tmp_path)
    events=[];sent=[]
    journal=SimpleNamespace(record=lambda n,**f:events.append((n,f)))
    device=SimpleNamespace(click=lambda *p:sent.append(p),swipe=lambda *p:sent.append(p))
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    method=getattr(runner,'one_shot_'+gesture)
    parts=[100,100,50,50] if gesture=='click' else [100,100,200,200,500]
    result=method(device,observer,parts,journal=journal,rounds=1)
    assert result['passed'] and len(sent)==1
    assert any(n=='window_reobserve' and f['round']==1 for n,f in events)
