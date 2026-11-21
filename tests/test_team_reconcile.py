"""Whole Runner respects a saved Teams slot, independent of the preset label."""
import json
import numpy as np
import pytest

from maalimbus.runner import MirrorRunner,FrameObserver,FakeDevice,controls_by_id,_load_registry
from maalimbus.storage import ProfileStore,RunStore,SINNERS,read_json
from maalimbus.policies import Team

ORDER=[3,4,9,1,7,2,12,5,8,10,11,6]
OTHER=[10,8,3,5,9,12,11,6,2,4,1,7]


def frame(order,header='Preset #1',scene='PRE_BATTLE_TEAM'):
    image=np.zeros((1080,1920,3),np.uint8)
    def token(text,box):return dict(text=text,box=box,score=.99)
    rows=[token(header,[150,254,100,24]),token('Clear Selection',[1640,704,190,26]),
          token('12/12',[1610,745,250,80]),token('To Battle!',[1672,859,146,44])]
    controls=controls_by_id(_load_registry())
    for badge,sinner in enumerate(order,1):
        x,y,w,h=controls[f'pre_battle.card_{sinner:02d}']
        rows.extend([token(str(badge),[x+int(w*.45),y+int(h*.2),22,30]),
                     token('SELECTED',[x+10,y+int(h*.5),w-20,30])])
    return dict(scene=scene,size=[1920,1080],ocr=rows,image=image)


def window(tmp_path,monkeypatch,observed,header='Preset #1',successor='DEPLOYMENT_RESET',width=1920):
    config=tmp_path/'config';config.mkdir()
    monkeypatch.setenv('MAALIMBUS_DATA_PATH',str(config))
    profiles=[Team(slot,frozenset({'Charge'}),deployment=tuple(SINNERS[n-1] for n in order))
              for slot,order in [(1,OTHER),(2,ORDER)]]
    ProfileStore(config/'user-team-profiles.json').save(profiles)
    store=RunStore(config/'user-run-ledger.json',[profiles[1]]);scope=store.start()
    before=frame(observed,header)
    if width!=1920:
        import cv2
        scale=width/1920
        before['size']=[width,round(1080*scale)]
        before['image']=cv2.resize(before['image'],tuple(before['size']))
        for row in before['ocr']:row['box']=[round(v*scale) for v in row['box']]
    after=dict(scene=successor,size=before['size'],image=before['image'],ocr=[])
    observer=FrameObserver(tmp_path/'frames',[before,after,after])
    device=FakeDevice([before['image'],after['image']])
    runner=MirrorRunner(device,settings=dict(team=2,rounds=1,interval=0,stop_page=successor),
        store=store,run_id=scope,directory=tmp_path/'frames',observer=observer)
    return runner,device,store


@pytest.mark.parametrize('width',[1920,1280])
def test_preset_one_keeps_team_two_and_matching_order_needs_only_submit(tmp_path,monkeypatch,width):
    runner,device,store=window(tmp_path,monkeypatch,ORDER,successor='BATTLE_HUD',width=width)
    runner.step()
    assert len(device.clicks)==1
    assert runner.deployment_transaction.data['order']==ORDER
    assert runner.deployment_transaction.data['sequence']==[]
    assert runner.state['deployment_order_source']=='saved_verified_on_page'
    assert store.team_slot==2 and store.data['active']['team']==2
    assert all(0<=tap[0]<width for tap in device.clicks)


def test_readable_other_order_is_reset_instead_of_overwriting_saved_order(tmp_path,monkeypatch):
    runner,device,store=window(tmp_path,monkeypatch,OTHER)
    runner.step()
    assert len(device.clicks)==1
    assert runner.deployment_transaction.data['order']==ORDER
    assert runner.deployment_transaction.data['pending']['kind']=='clear'
    assert runner.state['deployment_order_source']=='config'
    assert store.team_slot==2


def test_explicit_foreign_team_header_refuses_without_adopting_another_build(tmp_path,monkeypatch):
    runner,device,store=window(tmp_path,monkeypatch,OTHER,header='TEAMS #1')
    before=store.path.read_bytes()
    result=runner.step()
    assert result['stopped']=='the_board_shows_a_different_saved_team_than_the_plan_deploys'
    assert not device.clicks and store.path.read_bytes()==before
    assert runner.deployment_transaction.data is None
