from types import SimpleNamespace

import pytest

from maalimbus.storage import RunStore, write_json


def test_mirror_hands_authorized_claim_to_receipt_executor_and_refreshes_rotation(tmp_path, monkeypatch):
    from maalimbus import reward_task, runner

    scope = 'current'
    ledger = tmp_path/'user-run-ledger.json'
    active = dict(id=scope, floors=[1,2,3,4,5], victory=True, reward=False)
    current = dict(active=active, rotation=0, completed_runs=0)
    write_json(ledger,current)
    store = SimpleNamespace(path=ledger, data=current, team_slot=2)
    loop = runner.MirrorRunner(runner.FakeDevice(), settings=runner.settings({'run_count':1}),
                               store=store, run_id=scope, directory=tmp_path)
    loop.configure()
    approvals = []

    def execute(config, directory, observer, device, journal, *, deadline):
        approvals.append((config, device))
        assert config==tmp_path and directory==tmp_path
        write_json(ledger,dict(active=None, rotation=1, completed_runs=1))
        return dict(reward_received=True, input_attempts=4, reason='mirror_payout_and_home_verified')

    monkeypatch.setattr(reward_task,'execute',execute)
    page = dict(scene='RUN_REWARD_DIALOG')
    write_json(tmp_path/'user-mirror-settings.json',
               dict(reward_budget_scope='old', max_reward_modules=6, module_budget_pending=False))
    denied = loop._paid_reward_handoff(page['scene'], page, None, [])
    assert denied['stopped']=='reward_module_budget_pending' and not approvals
    detail = loop.summary()['stop_detail']
    assert detail['pending_kind']=='reward' and detail['reward_action']=='claim'
    assert detail['reward_quote'] is None and detail['input_status']=='not_sent'
    write_json(tmp_path/'user-mirror-settings.json',
               dict(reward_budget_scope=scope, max_reward_modules=5, module_budget_pending=False))
    accepted = loop._paid_reward_handoff(page['scene'], page, None, [])
    assert len(approvals)==1 and accepted['done'] and accepted['page']=='HOME'
    assert loop.artifacts['clicks_sent']==4 and loop.artifacts['verified_clear']
    assert loop.store.data['rotation']==1 and loop._verified_runs()==1


@pytest.mark.parametrize('confirmation_scope', ('previous', 'current'))
def test_receipt_handoff_depends_on_confirmation_in_the_current_run(tmp_path, monkeypatch,
                                                               confirmation_scope):
    from maalimbus import reward_task, runner

    ledger = tmp_path/'user-run-ledger.json'
    active = dict(id='current', floors=[1,2,3,4,5], victory=True, reward=False)
    store = SimpleNamespace(path=ledger, data=dict(active=active))
    transaction = tmp_path/'user-reward-claim-transaction.json'
    write_json(transaction, dict(scope=confirmation_scope, confirm_sent=True))
    original = transaction.read_bytes()
    loop = runner.MirrorRunner(runner.FakeDevice(), settings={}, store=store, run_id='current',
                               directory=tmp_path)
    loop.configure()
    calls = []

    def execute(*args, **kwargs):
        calls.append(args)
        return dict(reward_received=False, reason='retained_receipt_test')

    monkeypatch.setattr(reward_task,'execute',execute)
    page = dict(scene='RUN_REWARD_RECEIPT')
    result = loop._paid_reward_handoff(page['scene'], page, None, [])
    assert result['stopped']==('retained_receipt_test' if confirmation_scope=='current'
                               else 'reward_receipt_without_current_confirmation')
    assert bool(calls)==(confirmation_scope=='current')
    assert transaction.read_bytes()==original and loop.artifacts['clicks_sent']==0


@pytest.mark.parametrize('percent', (99, 100))
def test_summary_settles_only_current_hash_bound_complete_page(tmp_path, percent):
    import hashlib
    import cv2
    import numpy as np
    from maalimbus import runner
    from maalimbus.native_evidence import observation_frame

    store = RunStore(tmp_path/'user-run-ledger.json', [SimpleNamespace(slot=2)])
    scope = store.start()
    before = tmp_path/'frame-0001.json'
    picture = before.with_suffix('.png')
    assert cv2.imwrite(str(picture), np.zeros((1080,1920,3), dtype=np.uint8))
    write_json(before, dict(scene='RUN_CLAIM', size=[1920,1080],
                            image_sha256=hashlib.sha256(picture.read_bytes()).hexdigest(),
                            ocr=[dict(text=text, box=box, score=.99) for text, box in (
                                ('Exploration', [210,108,160,30]),
                                ('Complete', [210,140,130,30]),
                                (f'{percent}%', [232,520,90,38]))]))
    for floor in range(1,5):
        store.record(scope,f'floor-{floor}','floor_clear',before,floor=floor)
    loop = runner.MirrorRunner(runner.FakeDevice(), settings={}, store=store,
                               run_id=scope, directory=tmp_path)
    loop.configure()
    observation, _, _ = observation_frame(tmp_path, dict(frame=before.stem))
    loop._observe_clear_summary(observation)
    assert store.data['active']['victory'] is (percent==100)
    if percent==100:
        assert store.data['active']['events']['final_victory-run']['evidence']==str(before.resolve())


