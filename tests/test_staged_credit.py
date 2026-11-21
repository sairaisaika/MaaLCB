"""Read-only evidence credit cannot substitute for two funded input successors."""
import json
from pathlib import Path

import numpy as np
import pytest

from maalimbus import evidence_capacity as capacity,workspace,runner
from test_evidence_capacity import captured,Controller


def fake_other_bytes(monkeypatch,root,headroom):
    actual=workspace.size
    extra=workspace.BUDGET_BYTES-actual(root)-headroom
    monkeypatch.setattr(workspace,'size',lambda p:actual(p)+(extra if Path(p).resolve()==root else 0))


def test_sequential_real_journal_pool_device_fit_where_joint_worst_case_does_not(captured,tmp_path,monkeypatch):
    journal,image,_=captured;journal.capacity_successor_size=(1920,1080)
    pair=7_349_634;input_credit=2*pair+capacity.STOP_BYTES
    headroom=input_credit+capacity.JOURNAL_HEADROOM+2_000_000
    fake_other_bytes(monkeypatch,tmp_path,headroom)
    initial=workspace.size(tmp_path);calls=[]
    assert initial+3*pair+capacity.STOP_BYTES+capacity.JOURNAL_HEADROOM>workspace.BUDGET_BYTES
    def reserve(directory,amount,*,application_root):
        calls.append(amount);workspace.require_space(tmp_path,amount)
        return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    pending=tmp_path/'pending.json';pending.write_text('{"pending":true}')
    original=pending.read_bytes()
    refresh=journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path)
    assert refresh['purpose']=='refresh' and refresh['successor_pairs']==0
    assert pool.load()['bytes']==pair+capacity.STOP_BYTES
    native=Controller();device=runner.MaaDevice(native,target_long_side=0,before_input=journal.before_input,wait=lambda *a,**k:None)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):device.click(10,20)
    assert native.sent==[]
    journal.frame(image,[],'MAP')
    admitted=journal.before_input('plan',('click',10,20))
    assert admitted['purpose']=='input' and admitted['successor_pairs']==2
    assert pool.load()['bytes']>=input_credit and workspace.size(tmp_path)<=workspace.BUDGET_BYTES
    device.click(10,20)
    assert native.sent==[('click',10,20)] and pending.read_bytes()==original
    assert pool.load()['owner']['purpose']=='input' and pool.load()['owner']['successor_pairs']==2


def test_full_size_refresh_does_not_promise_unaffordable_future_input(captured,tmp_path,monkeypatch):
    journal,_,_=captured;journal.capacity_successor_size=(1920,1080)
    pair=7_349_634
    fake_other_bytes(monkeypatch,tmp_path,pair+capacity.STOP_BYTES+capacity.JOURNAL_HEADROOM+2*capacity.SLOT_BYTES+4096)
    def reserve(directory,amount,*,application_root):return workspace.require_space(tmp_path,amount)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    refresh=journal.before_input('plan',('click',10,20))
    assert refresh['purpose']=='refresh' and refresh['successor_pairs']==0
    image=np.random.default_rng(99).integers(0,256,(1080,1920,3),np.uint8)
    journal.frame(image,[],'BATTLE_HUD',extra_payload='x'*900000)
    originals={p:p.read_bytes() for p in journal.directory.glob('frame-*')}
    pending=tmp_path/'pending.json';pending.write_text('{"pending":true}');body=pending.read_bytes()
    native=Controller();device=runner.MaaDevice(native,target_long_side=0,before_input=journal.before_input,wait=lambda *a,**k:None)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Workspace budget exceeded'):device.click(10,20)
    assert native.sent==[] and pending.read_bytes()==body
    assert all(p.read_bytes()==b for p,b in originals.items())
    assert capacity.EvidenceCapacity(tmp_path).load()['owner']['purpose']=='refresh'


def test_completed_refresh_cannot_loop_back_to_another_read_only_phase(captured,tmp_path,monkeypatch):
    journal,image,_=captured;calls=[]
    def initial(*args,**kwargs):
        calls.append(1);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',initial)
    journal.before_input('plan',('click',10,20));journal.frame(image,[],'MAP')
    pool=capacity.EvidenceCapacity(tmp_path);pair=pool.load()['owner']['pair_bound']
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+1)
    def full_input_or_refuse(directory,amount,*,application_root,prefer_extra=0):
        assert amount==2*pair+capacity.STOP_BYTES+capacity.JOURNAL_HEADROOM
        assert prefer_extra==pair
        raise ValueError('Full input credit is unavailable')
    monkeypatch.setattr(capacity.capture_retention,'reserve',full_input_or_refuse)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Full input credit'):
        journal.before_input('plan',('click',10,20))
    assert pool.load()['owner']['purpose']=='refresh' and pool.load()['bytes']==0


def test_second_storage_maintenance_keeps_the_full_funded_reservation(captured,tmp_path,monkeypatch):
    journal,image,_=captured
    journal.capacity_successor_size=(1920,1080)
    pool=capacity.EvidenceCapacity(tmp_path)
    target=2*7_349_634+capacity.STOP_BYTES
    calls=[]

    def reserve(directory,amount,*,application_root):
        calls.append(amount)
        workspace.require_space(tmp_path,amount)
        return dict(storage_maintenance=len(calls)<=2)

    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    first=journal.before_input('plan',('click',10,20))
    assert first['purpose']=='refresh' and first['reserved_bytes']<target
    journal.frame(image,[],'MAP')
    second=journal.before_input('plan',('click',10,20))
    assert second['purpose']=='refresh' and second['successor_pairs']==0
    assert second['reserved_bytes']==target
    native=Controller()
    device=runner.MaaDevice(native,target_long_side=0,before_input=journal.before_input,wait=lambda *a,**k:None)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):
        device.click(10,20)
    assert native.sent==[]
    journal.frame(image,[],'MAP')
    assert pool.load()['bytes']>=target-pool.load()['owner']['pair_bound']
    device.click(10,20)
    assert native.sent==[('click',10,20)] and calls[-1]<capacity.JOURNAL_HEADROOM+7_349_634


@pytest.mark.parametrize('fault',['unknown_purpose','false_successors','nonobject_owner'])
def test_invalid_phase_owner_never_grants_input_or_changes_slots(captured,tmp_path,monkeypatch,fault):
    journal,_,_=captured
    monkeypatch.setattr(capacity.capture_retention,'reserve',lambda *a,**k:dict(storage_maintenance=True))
    journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path);current=pool.load()
    owner=dict(current['owner'])
    if fault=='unknown_purpose':owner['purpose']='assumed'
    elif fault=='false_successors':owner['successor_pairs']=2
    else:owner=['not an owner']
    pool._resize(current['bytes'],owner=owner)
    before={p:p.read_bytes() for p in (*pool.slots,pool.credit)}
    with pytest.raises(capacity.EvidenceCapacityUnavailable):journal.before_input('click',('click',10,20))
    assert all(p.read_bytes()==body for p,body in before.items())


def test_refresh_purpose_keeps_stale_guard_if_redundant_flag_is_missing(captured,tmp_path,monkeypatch):
    journal,_,_=captured
    monkeypatch.setattr(capacity.capture_retention,'reserve',lambda *a,**k:dict(storage_maintenance=True))
    journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path);current=pool.load()
    owner=dict(current['owner']);owner.pop('fresh_capture_required');pool._resize(current['bytes'],owner=owner)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):journal.before_input('click',('click',10,20))


def test_native_cache_producer_uses_the_same_refresh_phase_predicate(captured,tmp_path,monkeypatch):
    journal,image,_=captured
    monkeypatch.setattr(capacity.capture_retention,'reserve',lambda *a,**k:dict(storage_maintenance=True))
    journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path);current=pool.load()
    owner=dict(current['owner']);owner.pop('fresh_capture_required');pool._resize(current['bytes'],owner=owner)
    old='frame-%04d'%journal.index
    assert journal.needs_fresh_capture(old)
    journal.frame(image,[],'MAP')
    assert not journal.needs_fresh_capture('frame-%04d'%journal.index)


def test_legacy_refresh_owner_still_requires_fresh_record_and_full_input_credit(captured,tmp_path,monkeypatch):
    journal,image,_=captured;calls=[]
    def reserve(*args,**kwargs):
        calls.append(1);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    journal.before_input('plan',('click',10,20));pool=capacity.EvidenceCapacity(tmp_path);current=pool.load()
    owner=dict(current['owner']);owner.pop('purpose');pool._resize(current['bytes'],owner=owner)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):journal.before_input('click',('click',10,20))
    journal.frame(image,[],'MAP');final=journal.before_input('click',('click',10,20))
    assert final['purpose']=='input' and final['successor_pairs']==2
    assert pool.load()['bytes']>=2*pool.load()['owner']['pair_bound']+capacity.STOP_BYTES
