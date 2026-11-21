"""Read-only shop interpretation needs no transaction and cannot settle one."""
import json
import numpy as np

from maalimbus import runner


def record():
    def text(word,box):return dict(text=word,box=box,score=.99)
    return dict(scene='SHOP',size=[1920,1080],image=np.zeros((1080,1920,3),np.uint8),ocr=[
        text('Shop',[170,145,100,35]),text('100',[850,180,80,35]),
        text('Refresh',[1490,160,100,35]),text('15',[1510,210,40,30]),
        text('Leave',[1622,945,150,53]),text('20',[915,460,30,30]),
        text('Oracle',[850,494,160,30]),text('20',[1145,460,30,30]),
        text('Scalpel',[1080,494,160,30])])


class PendingTransaction:
    def __init__(self):self.data={'pending':{'kind':'refresh','stage':'reserved'}}
    def __getattr__(self,name):
        raise AssertionError('Read-only flow tried transaction effect: '+name)


def run(directory,*,observe,pending=None):
    device=runner.FakeDevice()
    observer=runner.FrameObserver(directory,[record()])
    loop=runner.MirrorRunner(device,directory=directory,observer=observer,
        settings=dict(observe_only=observe,steps=1,interval=0,stall_seconds=0,progress_seconds=0))
    loop.shop_transaction=pending
    result=loop.run(steps=1,interval=0,round_limit=1)
    assert device.clicks==[] and device.swipes==[] and device.keys==[]
    return result


def test_observe_only_shop_without_scope_reaches_normal_read_only_handoff(tmp_path):
    result=run(tmp_path,observe=True)
    assert result['reason']=='observe_only',result
    assert result['clicks_sent']==0


def test_observe_only_never_reconciles_or_labels_an_existing_pending(tmp_path):
    pending=PendingTransaction();original=json.dumps(pending.data,sort_keys=True)
    result=run(tmp_path,observe=True,pending=pending)
    assert result['reason']=='observe_only'
    assert json.dumps(pending.data,sort_keys=True)==original
    assert not list(tmp_path.glob('user-*.json'))


def test_active_shop_without_scope_still_refuses_before_any_input(tmp_path):
    result=run(tmp_path,observe=False)
    assert result['reason']=='shop_transaction_scope_missing',result
