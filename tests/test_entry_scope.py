from types import SimpleNamespace
import pytest
from maalimbus.storage import RunStore,read_json
from maalimbus.run_wiring import reconcile,settle_entry_successor


def fixture(tmp_path):
    store=RunStore(tmp_path/'ledger.json',[SimpleNamespace(slot=7)])
    proof=tmp_path/'frame.json';proof.write_text('actual frame fixture')
    return store,proof


def test_multiple_loadout_windows_preserve_preparing_scope(tmp_path):
    store,proof=fixture(tmp_path);scope=store.start()
    for _ in range(3):
        assert reconcile(store,page='DUNGEON_TEAM',proof=proof) is None
        store=RunStore(store.path,[SimpleNamespace(slot=7)])
        assert store.start()==scope
    assert not store.data.get('abandoned')


def test_confirmation_is_durable_and_cannot_be_repeated_or_discarded(tmp_path):
    store,proof=fixture(tmp_path);scope=store.start()
    store.entry_intent(scope,7,proof)
    store=RunStore(store.path,[SimpleNamespace(slot=7)])
    with pytest.raises(ValueError):store.entry_intent(scope,7,proof)
    with pytest.raises(ValueError):reconcile(store,page='DUNGEON_TEAM',proof=proof)
    assert store.data['active']['id']==scope and store.data['active']['phase']=='entry_pending'


@pytest.mark.parametrize('page',['DUNGEON_TEAM','UNKNOWN','LEVEL_WARNING'])
def test_unproven_entry_successor_never_completes_intent(tmp_path,page):
    store,proof=fixture(tmp_path);scope=store.start();store.entry_intent(scope,7,proof)
    with pytest.raises(ValueError):store.entry_observed(scope,page,proof)
    assert store.data['active']['phase']=='entry_pending'


def test_entry_successor_does_not_credit_clear_reward_or_rotation(tmp_path):
    store,proof=fixture(tmp_path);scope=store.start();store.entry_intent(scope,7,proof)
    store.entry_observed(scope,'STAR_GRACES',proof)
    active=read_json(store.path)['active']
    assert active['phase']=='entered' and active['id']==scope
    assert active['floors']==[] and not active['victory'] and not active['reward']
    assert store.data['rotation']==0 and store.data['completed_runs']==0


def test_level_warning_is_a_separate_once_only_confirmation(tmp_path):
    store,proof=fixture(tmp_path);scope=store.start();store.entry_intent(scope,7,proof)
    store.entry_warning_intent(scope,proof)
    with pytest.raises(ValueError):store.entry_warning_intent(scope,proof)
    assert store.data['active']['phase']=='entry_pending'
    store.entry_observed(scope,'STAR_GRACES',proof)
    assert store.data['active']['entry']['warning_sent'] is True


def test_entry_arrival_can_settle_before_stop_page_without_confirm_replay(tmp_path):
    store,before=fixture(tmp_path);scope=store.start();store.entry_intent(scope,7,before)
    after=tmp_path/'successor.json';after.write_text('independent native STAR successor fixture')
    assert settle_entry_successor(store,scope,page='STAR_GRACES',proof=after)
    active=read_json(store.path)['active']
    assert active['phase']=='entered' and active['entry']['confirm_sent']
    assert active['entry']['successor']==str(after.resolve())
    assert not active['floors'] and not active['victory'] and not active['reward']
    state=store.path.read_bytes()
    assert not settle_entry_successor(store,scope,page='STAR_GRACES',proof=after)
    assert store.path.read_bytes()==state


@pytest.mark.parametrize('kind',['changed_before','same_frame','foreign_scope','unknown_page'])
def test_handoff_cannot_clear_an_unproven_or_other_entry(tmp_path,kind):
    store,before=fixture(tmp_path);scope=store.start();store.entry_intent(scope,7,before)
    after=tmp_path/'next.json';after.write_text('independent successor fixture')
    if kind=='changed_before':before.write_text('altered retained bytes')
    state=store.path.read_bytes()
    if kind=='unknown_page':
        assert not settle_entry_successor(store,scope,page='UNKNOWN',proof=after)
    else:
        with pytest.raises(ValueError):
            settle_entry_successor(store,'other' if kind=='foreign_scope' else scope,
                page='STAR_GRACES',proof=before if kind=='same_frame' else after)
    assert store.path.read_bytes()==state
