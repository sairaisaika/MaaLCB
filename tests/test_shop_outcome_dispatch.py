"""Synthetic run/receipt dispatch proves collection without returning to SHOP."""
import copy
from types import SimpleNamespace

import pytest

from maalimbus import shop_outcomes
from maalimbus.storage import read_json,write_json,RunStore,ProfileStore,seed_run_store
from maalimbus.policies import Team
from maalimbus.runner import record_ledger_event


def setup(tmp_path):
    from test_shop_value_training import sample_folder,ledger_for
    from test_shop_review_ownership import transaction_for
    root=tmp_path/'build/learning-review/shop-purchases'
    folder=sample_folder(root,'delayed-dispatch',scope='scope',status='pending',
                         benefit=None,eligible=False,approved_outcome=False)
    config=tmp_path/'config';config.mkdir()
    state=read_json(ledger_for(root))
    active=copy.deepcopy(state['receipts'][0])
    active.update(team=1,floors=[1,2,3,4],victory=False,reward=False,phase='entered')
    seed_run_store(config/'user-run-ledger.json',[1,2])
    data=read_json(config/'user-run-ledger.json');data['active']=active
    write_json(config/'user-run-ledger.json',data)
    transaction=transaction_for(folder).data
    transaction.update(version=1,current_visit='2',pending=None)
    transaction['visits']['2']['refreshes']=0
    write_json(config/'user-shop-scope.json',transaction)
    return config,folder,RunStore(config/'user-run-ledger.json',[Team(1,frozenset()),Team(2,frozenset())])


def journal():
    events=[]
    return SimpleNamespace(record=lambda name,**fields:events.append((name,fields))),events


def test_last_purchase_learns_victory_from_normal_ledger_dispatch_without_another_shop(tmp_path):
    from test_shop_value_training import _write_frame
    config,folder,store=setup(tmp_path)
    assert shop_outcomes.refresh_scope(config,'scope',trigger='earlier_shop')['automatic_labels_ready']==1
    assert read_json(folder/'review.json')['benefit']==.8
    directory=tmp_path/'frames'
    _write_frame(directory/'frame-0001.json',coins=880,offers=[],
                 utc='2026-10-12T14:00:00+00:00',scene='RUN_CLAIM')
    before=(config/'user-shop-scope.json').read_bytes()
    log,events=journal()
    recorded=record_ledger_event(store,'scope',directory,'RUN_CLAIM',{},5,log)
    assert [e.kind for e in recorded]==['floor_clear','final_victory']
    assert read_json(folder/'review.json')['benefit']==1.0
    assert (config/'user-shop-scope.json').read_bytes()==before
    report=[e[1] for e in events if e[0]=='shop_purchase_learning_samples'][0]
    assert report['automatic_labels_ready']==1 and not report['input_sent']
    assert not report['neural_policy_applied']
    events.clear()
    assert record_ledger_event(store,'scope',directory,'RUN_CLAIM',{},5,log)==[]
    assert not events  # An unchanged page does not repeatedly run the teacher.


def test_a_label_failure_cannot_revoke_real_settled_events_and_resume_retries_labels_only(tmp_path,monkeypatch):
    from test_shop_value_training import _write_frame
    config,folder,store=setup(tmp_path);original=shop_outcomes.sync
    def fail(*a,**k):raise OSError('isolated full volume')
    monkeypatch.setattr(shop_outcomes,'sync',fail)
    directory=tmp_path/'frames'
    _write_frame(directory/'frame-0001.json',coins=880,offers=[],
                 utc='2026-10-12T14:00:00+00:00',scene='RUN_CLAIM')
    log,events=journal()
    assert len(record_ledger_event(store,'scope',directory,'RUN_CLAIM',{},5,log))==2
    assert read_json(store.path)['active']['victory']
    assert events[-1][1]['status']=='pending'
    ledger=store.path.read_bytes();transaction=(config/'user-shop-scope.json').read_bytes()
    monkeypatch.setattr(shop_outcomes,'sync',original)
    result=shop_outcomes.refresh_scope(config,'scope',trigger='mirror_resume')
    assert result['automatic_labels_ready']==1 and read_json(folder/'review.json')['benefit']==1
    assert store.path.read_bytes()==ledger and (config/'user-shop-scope.json').read_bytes()==transaction


@pytest.mark.parametrize('scope',['../scope','..\\scope','',None,'a/b'])
def test_scope_cannot_read_another_file_or_create_review_folders(tmp_path,scope):
    config=tmp_path/'config';config.mkdir()
    assert shop_outcomes.refresh_scope(config,scope,trigger='resume')['status']=='pending'
    assert list(tmp_path.iterdir())==[config] and not list(config.iterdir())


def test_absent_transaction_is_zero_write_and_foreign_transaction_is_preserved(tmp_path):
    config,_,_=setup(tmp_path)
    assert shop_outcomes.refresh_scope(config,'missing',trigger='resume')['status']=='absent'
    path=config/'user-shop-scope.json';data=read_json(path);data['scope']='foreign';write_json(path,data)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert shop_outcomes.refresh_scope(config,'scope',trigger='resume')['status']=='pending'
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('interrupted_labels',[False,True])
def test_payout_archival_triggers_labels_and_a_completed_resume_never_rotates_again(tmp_path,monkeypatch,interrupted_labels):
    import maalimbus.reward_task as task
    from test_shop_value_training import _write_frame
    config,folder,store=setup(tmp_path)
    home=tmp_path/'home.json'
    _write_frame(home,coins=880,offers=[],utc='2026-10-12T15:00:00+00:00',scene='HOME')
    data=read_json(store.path);data['active'].update(floors=[1,2,3,4,5],victory=True)
    write_json(store.path,data)
    ProfileStore(config/'user-team-profiles.json').save([Team(1,frozenset()),Team(2,frozenset())])
    write_json(config/'user-reward-claim-transaction.json',dict(scope='scope',completed=False,
        receipt_proof=str(home),task_input_reports={}))
    # This test starts after the separately tested receipt audit. No fake live
    # claim is made: verify is explicitly isolated, while real bookkeeping runs.
    monkeypatch.setattr(task,'verify',lambda *a:dict(proofs=['isolated-audit']))
    original=shop_outcomes.sync
    if interrupted_labels:
        def fail(*a,**kw):raise OSError('isolated label failure after payout')
        monkeypatch.setattr(shop_outcomes,'sync',fail)
    log,events=journal()
    result=task.finish(config,'scope',home,journal=log)
    assert result['passed']
    assert result['purchase_learning']['status']==('pending' if interrupted_labels else 'collected')
    archived=read_json(store.path)
    assert archived['active'] is None and archived['rotation']==1 and archived['completed_runs']==1
    before=store.path.read_bytes()
    transaction=(config/'user-reward-claim-transaction.json').read_bytes()
    monkeypatch.setattr(shop_outcomes,'sync',original)
    # A completed transaction may recover labels but cannot repeat payout input.
    result=task.execute(config,tmp_path,SimpleNamespace(),SimpleNamespace(),log)
    assert not result['input_sent'] and store.path.read_bytes()==before
    assert (config/'user-reward-claim-transaction.json').read_bytes()==transaction
    report=[fields for name,fields in events if name=='shop_purchase_learning_samples'][-1]
    assert report['trigger']=='completed_payout_resume' and report['automatic_labels_ready']==1
    assert {o['kind'] for o in read_json(folder/'outcome.json')['outcomes']} >= {'reward_received','entry_returned'}


@pytest.mark.parametrize('observe_only',[False,True])
def test_mirror_resume_leaves_review_collection_to_offline_maintenance(tmp_path,monkeypatch,observe_only):
    from maalimbus.runner import MirrorRunner
    config,folder,store=setup(tmp_path)
    runner=MirrorRunner.__new__(MirrorRunner)
    runner.store=store;runner.run_id='scope';runner.journal=None
    runner.settings=SimpleNamespace(observe_only=observe_only,steps=1)
    runner.state={'step':0};runner.summary=lambda:dict(input_sent=False)
    runner._retire_foreign_pending=lambda:None;runner._start_stall_watch=lambda:None
    original=shop_outcomes.sync;calls=[]
    def counted(*a,**kw):calls.append(True);return original(*a,**kw)
    monkeypatch.setattr(shop_outcomes,'sync',counted)
    before=(config/'user-run-ledger.json').read_bytes()
    assert runner._walk(steps=1,round_limit=0)==dict(input_sent=False)
    assert runner._walk(steps=1,round_limit=0)==dict(input_sent=False)
    assert not calls
    assert (config/'user-run-ledger.json').read_bytes()==before
    assert read_json(folder/'review.json')['status']=='pending'


def test_no_event_never_dispatches_the_optional_teacher(tmp_path,monkeypatch):
    config,_,store=setup(tmp_path)
    monkeypatch.setattr(shop_outcomes,'refresh_scope',lambda *a,**k:pytest.fail('no event'))
    assert record_ledger_event(store,'scope',tmp_path/'no-frames','SHOP',{},4)==[]
