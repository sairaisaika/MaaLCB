"""Reset-modal ownership and bounded re-opening of an unconfirmed reset."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus import runner
from maalimbus.deployment_transaction import DeploymentTransaction
from maalimbus.storage import write_json


ORDER=[3,4,9,1,7,2,12,5,8,10,11,6]
OLD=[11,9,3,10,4,8,12,2,5,1,7,6]


def transaction(tmp_path):
    tx=DeploymentTransaction(tmp_path/'deployment.json')
    tx.prepare('scope',ORDER,(12,12),OLD);tx.intent('clear',(12,12))
    return tx


def proof(tmp_path,n):
    path=tmp_path/f'frame-{n:04}.json';png=path.with_suffix('.png');png.write_bytes(b'pixels')
    image=hashlib.sha256(png.read_bytes()).hexdigest()
    write_json(path,dict(scene='PRE_BATTLE_TEAM',image_sha256=image,observation=n))
    return dict(frame=str(path),record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        image_sha256=image,participants=[12,12],numbers=OLD)


def test_reopen_retains_original_pending_then_confirm_and_zero_count_settle_it(tmp_path):
    tx=transaction(tmp_path);original=deepcopy(tx.data['pending'])
    assert tx.prepare('scope',ORDER,(12,12),OLD)['reset_reopen_required']
    evidence=proof(tmp_path,1);tx.reserve_clear_reopen('scope',(12,12),OLD,evidence)
    assert all(tx.data['pending'][k]==v for k,v in original.items())
    assert tx.data['pending']['reopen_proofs']==[evidence]
    tx=DeploymentTransaction(tx.path);tx.confirm_clear('scope')
    with pytest.raises(ValueError):tx.reserve_clear_reopen('scope',(12,12),OLD,proof(tmp_path,2))
    tx.observe((0,12));assert tx.data['pending'] is None
    assert not tx.prepare('scope',ORDER,(0,12))['reset_required']


def test_reopen_attempts_are_bounded_across_restarts_and_cannot_reuse_a_frame(tmp_path):
    tx=transaction(tmp_path);evidence=proof(tmp_path,1)
    tx.reserve_clear_reopen('scope',(12,12),OLD,evidence)
    before=tx.path.read_bytes()
    with pytest.raises(ValueError):tx.reserve_clear_reopen('scope',(12,12),OLD,evidence)
    assert tx.path.read_bytes()==before
    tx=DeploymentTransaction(tx.path);tx.reserve_clear_reopen('scope',(12,12),OLD,proof(tmp_path,2))
    before=tx.path.read_bytes()
    with pytest.raises(ValueError,match='budget exhausted'):tx.prepare('scope',ORDER,(12,12),OLD)
    with pytest.raises(ValueError):tx.reserve_clear_reopen('scope',(12,12),OLD,proof(tmp_path,3))
    assert tx.path.read_bytes()==before


@pytest.mark.parametrize('fault',['foreign_scope','partial_counter','unread_badge','already_correct',
    'confirm_sent','card_pending','submit_pending','changed_png','changed_record','missing_png','missing_record','wrong_proof_count'])
def test_other_pending_states_and_changed_evidence_never_gain_retry_permission(tmp_path,fault):
    tx=transaction(tmp_path);evidence=proof(tmp_path,1);scope='scope';count=(12,12);numbers=list(OLD)
    if fault=='foreign_scope':scope='other'
    elif fault=='partial_counter':count=(11,12)
    elif fault=='unread_badge':numbers[0]=None
    elif fault=='already_correct':
        for position,card in enumerate(ORDER,1):numbers[card-1]=position
    elif fault=='confirm_sent':tx.data['pending']['confirm_sent']=True
    elif fault=='card_pending':tx.data['pending']['kind']='card'
    elif fault=='submit_pending':tx.data['submit_pending']=True
    elif fault=='changed_png':Path(evidence['frame']).with_suffix('.png').write_bytes(b'changed')
    elif fault=='changed_record':Path(evidence['frame']).write_text('{}')
    elif fault=='missing_png':Path(evidence['frame']).with_suffix('.png').unlink()
    elif fault=='missing_record':Path(evidence['frame']).unlink()
    elif fault=='wrong_proof_count':evidence['participants']=[0,12]
    write_json(tx.path,tx.data);before=tx.path.read_bytes()
    with pytest.raises(ValueError):tx.reserve_clear_reopen(scope,count,numbers,evidence)
    assert tx.path.read_bytes()==before


def test_actual_reset_modal_reaches_its_owner_before_background_party_fallback(tmp_path,monkeypatch):
    import maalimbus.party_vision as party
    root=Path(__file__).resolve().parents[1]
    path=root/'evidence/runtime/packaged-mirror-20261116-234249/frame-0004.json'
    assert path.is_file(), 'actual regression frame must remain retained'
    record=json.loads(path.read_text(encoding='utf8'))
    write_json(tmp_path/'frame-0001.json',record)
    clicks=[]
    loop=runner.MirrorRunner(SimpleNamespace(controller=None,click=lambda *p:clicks.append(p)),
        settings=dict(interval=0),directory=tmp_path)
    loop.deployment_transaction=transaction(tmp_path);loop.run_id='scope'
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:('frame-0001.png',[]))
    domain_plan=party.plan;ownership=[]
    def guarded(*args,**kw):
        result=domain_plan(*args,**kw);ownership.append(kw)
        assert result is None, 'background party must not own a named modal'
        return result
    monkeypatch.setattr(party,'plan',guarded)
    class ModalOwnerReached(Exception):pass
    def planned(page,**kw):
        assert page=='DEPLOYMENT_RESET' and kw['team']['reset_pending']
        x,y,w,h=kw['controls']['deployment_reset.confirm']
        assert 990<x<1200 and 700<y<800 and w>100
        raise ModalOwnerReached()
    monkeypatch.setattr(runner,'plan_step',planned)
    with pytest.raises(ModalOwnerReached):loop.step()
    assert clicks==[] and not loop.deployment_transaction.data['pending'].get('confirm_sent')
    assert ownership[0]['scene']=='DEPLOYMENT_RESET' and ownership[0]['unresolved']


@pytest.mark.parametrize('scene',['DEPLOYMENT_RESET','SHOP_PURCHASE','UNKNOWN_DIALOG',
    'PRE_BATTLE_TEAM','BATTLE_HUD','UNKNOWN'])
def test_fallback_reader_cannot_spend_background_counter_or_pending_input(scene):
    from maalimbus import party_vision
    from maalimbus.vision import Text
    reads=[Text('Total Participants',(1620,770,170,20),.99),
           Text('12/12',(1800,770,65,20),.99)]
    assert party_vision.plan(reads,(1920,1080)) is not None
    assert party_vision.plan(reads,(1920,1080),scene=scene,unresolved=scene=='UNKNOWN') is None
