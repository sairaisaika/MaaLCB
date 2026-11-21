"""An intentional named-page handoff is read-only and is not a failed run."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus import runner
from maalimbus.deployment_transaction import DeploymentTransaction
from maalimbus.storage import RunStore,write_json


def loop_for(tmp_path,monkeypatch,page,**settings):
    def forbidden(*args,**kwargs):raise AssertionError('handoff cannot send input or normalize')
    device=SimpleNamespace(controller=object(),click=forbidden,swipe=forbidden)
    loop=runner.MirrorRunner(device,settings=dict(interval=0,stop_page=page,**settings),
                             directory=tmp_path)
    record=dict(scene=page,size=[1920,1080],ocr=[],image_sha256='fresh-native-hash')
    frame=tmp_path/'frame-0001.json';write_json(frame,record)
    monkeypatch.setattr(loop,'_observe',lambda **kwargs:record)
    monkeypatch.setattr(loop,'_normalise_view_once',forbidden)
    monkeypatch.setattr(runner,'candidates_of',forbidden)
    return loop,record


@pytest.mark.parametrize('page',['MAP','BATTLE_HUD','GIFT_PICK','SHOP','RUN_CLAIM'])
def test_named_incoming_page_stops_before_every_view_or_candidate_action(tmp_path,monkeypatch,page):
    loop,record=loop_for(tmp_path,monkeypatch,page)
    result=loop.step();summary=loop.summary()
    assert result['done'] and result['stopped']=='stop_page_reached'
    assert not result['input_sent'] and summary['clicks_sent']==0
    assert summary['passed'] and summary['reason']=='window_steps_passed'
    assert summary['page_before']==summary['page_after']==page
    assert not summary['verified_clear'] and 'view_normalised' not in loop.state


@pytest.mark.parametrize('fault',['foreign_scope','unknown','observe_only',None])
def test_only_same_scope_fresh_battle_handoff_settles_an_existing_submit(tmp_path,monkeypatch,fault):
    page='UNKNOWN' if fault=='unknown' else 'BATTLE_HUD'
    loop,record=loop_for(tmp_path,monkeypatch,page,observe_only=fault=='observe_only')
    path=tmp_path/'deployment.json'
    write_json(path,dict(scope='other' if fault=='foreign_scope' else 'current',
                         submit_pending=True,submitted=False,pending=None))
    transaction=DeploymentTransaction(path);loop.deployment_transaction=transaction
    loop.run_id='current';before=path.read_bytes()
    result=loop.step();summary=loop.summary()
    if fault is None:
        assert transaction.data['submitted'] and not transaction.data['submit_pending']
        assert Path(transaction.data['battle_proof']).is_file()
    else:assert path.read_bytes()==before
    assert not result['input_sent'] and summary['clicks_sent']==0
    assert summary['passed']==(fault!='unknown')
    assert not summary['verified_clear']


def test_entry_successor_is_settled_before_read_only_handoff_without_clear_credit(tmp_path,monkeypatch):
    loop,record=loop_for(tmp_path,monkeypatch,'STAR_GRACES')
    store=RunStore(tmp_path/'ledger.json',[SimpleNamespace(slot=2)])
    scope=store.start();before=tmp_path/'before.json';write_json(before,dict(scene='DUNGEON_TEAM'))
    store.entry_intent(scope,2,before)
    loop.store=store;loop.run_id=scope
    result=loop.step();active=store.data['active']
    assert result['done'] and not result['input_sent']
    assert active['id']==scope and active['phase']=='entered'
    assert not active['floors'] and not active['victory'] and not active['reward']
    assert store.data['rotation']==store.data['completed_runs']==0
