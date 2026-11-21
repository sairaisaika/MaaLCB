"""Unspent placeholders cannot prevent staging an ordinary storage rewrite."""
import json
from pathlib import Path
import pytest
import numpy as np
from test_evidence_capacity import captured, Controller
from maalimbus import evidence_capacity as capacity,workspace,runner


def prepared(captured,tmp_path):
    journal,image,_=captured
    first=journal.before_input('plan',('click',10,20))
    journal.frame(image,[],'MAP')
    pool=capacity.EvidenceCapacity(tmp_path);previous=pool.load()
    path=tmp_path/'config/pending.json';path.parent.mkdir();path.write_text('{"pending":true}')
    return journal,pool,previous,first,path


def pressure(monkeypatch,tmp_path,previous,target):
    actual=workspace.size;growth=target-previous['bytes']
    state={'extra':workspace.BUDGET_BYTES-actual(tmp_path)-growth-capacity.JOURNAL_HEADROOM+1}
    monkeypatch.setattr(workspace,'size',lambda p:actual(p)+(state['extra'] if Path(p).resolve()==tmp_path else 0))
    return state


def test_handoff_funds_fresh_observation_without_spending_input_successors(captured,tmp_path,monkeypatch):
    journal,pool,previous,first,pending=prepared(captured,tmp_path)
    state=pressure(monkeypatch,tmp_path,previous,first['reserved_bytes']);seen=[]
    def reclaim(directory,amount,*,application_root):
        seen.append((pool.load()['bytes'],amount))
        # A rewrite needs more room than is free while the old placeholder is
        # held. This is independent of the final reservation's net growth.
        assert workspace.size(tmp_path)+3_000_000<=workspace.BUDGET_BYTES
        if len(seen)==1:state['extra']-=previous['owner']['pair_bound']+1_000_000
        workspace.require_space(tmp_path,amount)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reclaim)
    before={p:p.read_bytes() for p in journal.directory.glob('frame-*')}
    result=journal.before_input('plan',('click',10,20))
    pair=previous['owner']['pair_bound']
    assert seen==[(0,pair+capacity.STOP_BYTES+capacity.JOURNAL_HEADROOM)]
    assert result['reserved_bytes']==pair+capacity.STOP_BYTES
    assert result['purpose']=='refresh' and result['successor_pairs']==0 and result['input_sent'] is False
    assert result['reobserve_pairs']==1 and result['reobserve_pair_bound']==pair
    assert result['storage_credit_handoff_bytes']==previous['bytes']
    assert pool.load()['bytes']==pair+capacity.STOP_BYTES
    assert pool.load()['owner']['fresh_capture_required'] is True
    assert {p:p.read_bytes() for p in before}==before and json.loads(pending.read_bytes())['pending'] is True
    # The read has no input guarantee to spend. Its actual new record must
    # independently fund two complete successors before the physical door.
    journal.frame(captured[1],[],'MAP')
    readmitted=journal.before_input('plan',('click',10,20))
    assert not readmitted.get('storage_maintenance')
    assert readmitted['purpose']=='input' and readmitted['successor_pairs']==2
    assert pool.load()['bytes']>=first['reserved_bytes']
    assert not pool.load()['owner'].get('fresh_capture_required')
    def unexpected(*args,**kwargs):raise AssertionError('Physical input was not already fully funded')
    monkeypatch.setattr(capacity.capture_retention,'reserve',unexpected)
    native=Controller();device=runner.MaaDevice(native,target_long_side=0,before_input=journal.before_input,wait=lambda *a,**k:None)
    device.click(10,20)
    assert native.sent==[('click',10,20)]
    assert json.loads(pending.read_bytes())['pending'] is True


def test_failed_readmission_cannot_mutate_pending_or_create_new_input_authority(captured,tmp_path,monkeypatch):
    journal,pool,previous,first,pending=prepared(captured,tmp_path)
    pressure(monkeypatch,tmp_path,previous,first['reserved_bytes'])
    before={p:p.read_bytes() for p in journal.directory.glob('frame-*')}
    def refuse(*args,**kwargs):
        assert pool.load()['bytes']==0
        raise ValueError('Protected evidence fills the budget')
    monkeypatch.setattr(capacity.capture_retention,'reserve',refuse)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Protected evidence'):
        journal.before_input('click',('click',10,20))
    assert pool.load()['bytes']==0 and pool.load()['owner']==previous['owner']
    assert {p:p.read_bytes() for p in before}==before and json.loads(pending.read_bytes())['pending'] is True
    rows=[json.loads(line) for line in (journal.directory/'events.jsonl').read_text().splitlines()]
    assert sum(row['event']=='evidence_capacity_admitted' for row in rows)==1
    assert not any(row.get('input_sent') is True or row['event']=='window_intent' for row in rows)


def test_foreign_writer_credit_is_not_released_by_this_journal(captured,tmp_path,monkeypatch):
    journal,pool,previous,first,_=prepared(captured,tmp_path)
    previous=pool._resize(previous['bytes'],owner={'directory':'foreign'},consumer='foreign')
    pressure(monkeypatch,tmp_path,previous,first['reserved_bytes'])
    def refuse(*args,**kwargs):
        assert pool.load()==previous
        raise ValueError('Foreign credit retained')
    monkeypatch.setattr(capacity.capture_retention,'reserve',refuse)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Foreign credit'):
        journal.before_input('click',('click',10,20))
    assert pool.load()==previous


def test_normal_topup_keeps_existing_credit_without_handoff(captured,tmp_path,monkeypatch):
    journal,pool,previous,first,_=prepared(captured,tmp_path);seen=[]
    def reserve(directory,amount,*,application_root):
        seen.append(amount);assert pool.load()==previous
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    result=journal.before_input('click',('click',10,20))
    assert seen==[first['reserved_bytes']-previous['bytes']+capacity.JOURNAL_HEADROOM]
    assert 'storage_credit_handoff_bytes' not in result
    assert result['reserved_bytes']==first['reserved_bytes']


def test_interrupted_handoff_keeps_valid_two_slot_accounting_and_actual_proof(captured,tmp_path,monkeypatch):
    journal,pool,previous,first,pending=prepared(captured,tmp_path)
    pressure(monkeypatch,tmp_path,previous,first['reserved_bytes'])
    resize=capacity.EvidenceCapacity._resize
    class PowerLoss(BaseException):pass
    def interrupt(self,amount,**kwargs):
        result=resize(self,amount,**kwargs)
        if amount==0:raise PowerLoss()
        return result
    monkeypatch.setattr(capacity.EvidenceCapacity,'_resize',interrupt)
    before={p:p.read_bytes() for p in journal.directory.glob('frame-*')}
    with pytest.raises(PowerLoss):journal.before_input('click',('click',10,20))
    current=pool.load();assert current['state']=='ready' and current['bytes']==0
    assert current['owner']==previous['owner']
    assert {p:p.read_bytes() for p in before}==before and json.loads(pending.read_bytes())['pending'] is True


@pytest.mark.parametrize('kind',['plan','click','swipe','key','pinch'])
def test_stale_before_proof_cannot_spend_funded_refresh_credit(captured,tmp_path,monkeypatch,kind):
    journal,_,_=captured;calls=[]
    def reserve(*args,**kwargs):
        calls.append(args[1]);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    admitted=journal.before_input('plan',('click',10,20));assert admitted['reobserve_pairs']==1
    pool=capacity.EvidenceCapacity(tmp_path);before=pool.load()
    snapshots={p:p.read_bytes() for p in (*pool.slots,pool.credit)}
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):
        journal.before_input(kind,(kind,10,20))
    assert pool.load()==before and all(p.read_bytes()==body for p,body in snapshots.items())
    assert len(calls)==1


def test_unfunded_extra_observation_preserves_proof_pending_and_no_input(captured,tmp_path,monkeypatch):
    journal,_,_=captured;calls=[]
    pending=tmp_path/'pending.json';pending.write_text('{"pending":true}');saved=pending.read_bytes()
    frames={p:p.read_bytes() for p in journal.directory.iterdir()}
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+capacity.STOP_BYTES)
    def reserve(*args,**kwargs):
        calls.append(args[1])
        raise ValueError('Protected evidence cannot fund fresh capture')
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='cannot fund fresh'):
        journal.before_input('plan',('click',10,20))
    assert not capacity.EvidenceCapacity(tmp_path).exists
    assert len(calls)==1
    assert pending.read_bytes()==saved and {p:p.read_bytes() for p in journal.directory.iterdir()}==frames


def test_full_native_refresh_then_two_incompressible_successors_need_no_new_reservation(captured,tmp_path,monkeypatch):
    journal,_,_=captured;journal.capacity_successor_size=(1920,1080);calls=[]
    def reserve(*args,**kwargs):
        calls.append(args[1]);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    admission=journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path)
    pair=pool.load()['owner']['pair_bound'];base=2*pair+capacity.STOP_BYTES
    assert admission['reserved_bytes']==pair+capacity.STOP_BYTES and admission['reobserve_pairs']==1
    assert admission['purpose']=='refresh' and admission['successor_pairs']==0
    limit=workspace.size(tmp_path)+base+capacity.JOURNAL_HEADROOM
    monkeypatch.setattr(workspace,'BUDGET_BYTES',limit)
    image=np.random.default_rng(81).integers(0,256,(1080,1920,3),np.uint8)
    journal.frame(image,[],'BATTLE_HUD',extra_payload='x'*900000)
    assert pool.load()['bytes']>=capacity.STOP_BYTES and workspace.size(tmp_path)<=limit
    fresh=journal.before_input('plan',('click',10,20));assert not fresh.get('storage_maintenance')
    assert fresh['purpose']=='input' and fresh['successor_pairs']==2 and pool.load()['bytes']>=base
    def unexpected(*args,**kwargs):raise AssertionError('Post-input successor credit was not fully reserved')
    monkeypatch.setattr(capacity.capture_retention,'reserve',unexpected)
    native=Controller();device=runner.MaaDevice(native,target_long_side=0,before_input=journal.before_input,wait=lambda *a,**k:None)
    device.click(10,20);assert native.sent==[('click',10,20)]
    for seed in (82,83):
        image=np.random.default_rng(seed).integers(0,256,(1080,1920,3),np.uint8)
        journal.frame(image,[],'UNKNOWN',extra_payload='x'*900000)
        assert workspace.size(tmp_path)<=limit
    assert pool.load()['bytes']>=capacity.STOP_BYTES


def test_torn_funded_refresh_keeps_freshness_requirement_after_storage_recovery(captured,tmp_path,monkeypatch):
    journal,_,_=captured;calls=[]
    def reserve(*args,**kwargs):
        calls.append(args[1]);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    store=capacity.EvidenceCapacity._store
    class PowerLoss(BaseException):pass
    def interrupted(self,record):
        if record['state']=='ready' and (record.get('owner') or {}).get('fresh_capture_required'):
            raise PowerLoss()
        return store(self,record)
    before={p:p.read_bytes() for p in journal.directory.iterdir()}
    monkeypatch.setattr(capacity.EvidenceCapacity,'_store',interrupted)
    with pytest.raises(PowerLoss):journal.before_input('plan',('click',10,20))
    monkeypatch.setattr(capacity.EvidenceCapacity,'_store',store)
    pool=capacity.EvidenceCapacity(tmp_path);restored=pool.load()
    assert restored['state']=='ready' and restored['owner']['fresh_capture_required']
    assert restored['owner']['purpose']=='refresh' and restored['owner']['successor_pairs']==0
    assert restored['bytes']>=restored['owner']['pair_bound']+capacity.STOP_BYTES
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):
        journal.before_input('click',('click',10,20))
    assert {p:p.read_bytes() for p in before}==before
    assert not any(key in restored for key in ('input_sent','completed','accepted','reward_received'))
