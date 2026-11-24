"""A run that ended before the dungeon was cleared: recorded as lost, claimed only by choice.

The reward dialog rows are the OCR of pi-20261123-232359/frame-0004: a hard run that
ended at 95%, `Floor 5 [HARD] 3/4`, offering its partial rewards for 5 modules.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus.paid_reward_action import lost_claim_allowed, prepare
from maalimbus.reward_cost import floor_count, page_anchors
from maalimbus.reward_task_budget import LOST, STANDING, apply_standing
from maalimbus.run_wiring import payout_state
from maalimbus.storage import RunStore, write_json
from maalimbus.vision import Text

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
DIALOG = [('Exploration Reward', (792, 156, 338, 42), 1.0), ('Weekly', (442, 339, 114, 42), 1.0),
          ('0/3', (660, 345, 84, 67), 1.0), ('OFF', (816, 359, 42, 34), 1.0), ('OFF', (970, 359, 42, 34), 1.0),
          ('OFF', (1122, 359, 44, 34), 1.0), ('100/1000', (1356, 371, 124, 43), 1.0),
          ('Bonuses', (440, 375, 132, 37), 1.0), ('Rewards', (438, 440, 130, 40), 1.0),
          ('Battle Pass XP', (886, 585, 178, 28), 1.0), ('Floor 5', (478, 617, 88, 36), .98),
          ('[HARD]', (480, 645, 82, 37), 1.0), ('Starlight', (654, 625, 176, 53), 1.0), ('x40', (1380, 631, 94, 53), .93),
          ('3/4', (490, 678, 64, 52), .96), ('40', (720, 678, 48, 50), 1.0), ('Manager EXP', (884, 708, 170, 34), 1.0),
          ('X GiveUpRewards', (448, 792, 280, 45), .96), ('To Window', (874, 800, 172, 33), 1.0),
          ('Claim', (1238, 796, 98, 41), 1.0), ('-5', (1428, 792, 46, 45), .88)]


def rows(count='3/4', floor='Floor 5'):
    return [Text(count if text == '3/4' else floor if text == 'Floor 5' else text, box, score)
            for text, box, score in DIALOG]


def dialog(count='3/4', floor='Floor 5', weekly=0, cost=5):
    return dict(scene='RUN_REWARD_DIALOG', size=[1920, 1080],
                reward_cost=dict(currency='enkephalin_modules', cost=cost, weekly=weekly),
                ocr=[dict(text=row.text, box=list(row.box), score=row.score) for row in rows(count, floor)])


def test_the_dialog_of_a_lost_run_is_the_reward_page_and_says_how_far_it_got():
    assert page_anchors(rows(), SIZE) is True
    assert floor_count(rows(), SIZE) == (5, 3, 4)
    assert floor_count(rows('4/4'), SIZE) == (5, 4, 4)
    assert floor_count(rows('2/6', 'Floor 3'), SIZE) == (3, 2, 6) and page_anchors(rows('2/6', 'Floor 3'), SIZE)
    assert floor_count(rows('5/4'), SIZE) is None and floor_count(rows('44'), SIZE) is None


def ledger(tmp_path, floors=4):
    store = RunStore(tmp_path / 'user-run-ledger.json', [SimpleNamespace(slot=2), SimpleNamespace(slot=5)])
    scope = store.start()
    proof = tmp_path / 'proof.json'
    proof.write_text('{}', encoding='utf-8')
    for floor in range(1, floors + 1):
        store.record(scope, f'floor-{floor}', 'floor_clear', proof, floor=floor)
    return store, scope, proof


def test_the_ledger_files_a_claimed_lost_run_without_counting_it(tmp_path):
    store, scope, proof = ledger(tmp_path)
    assert payout_state(store.data['active']) is None
    # Nothing pays a run the ledger knows nothing final about.
    with pytest.raises(ValueError, match='without victory'):
        store.record(scope, 'receipt', 'reward_received', proof)
    assert store.record(scope, 'native-lost-summary', 'run_lost', proof)
    assert store.data['active']['lost'] is True and payout_state(store.data['active']) == 'lost'
    store.record(scope, 'receipt', 'reward_received', proof)
    store.record(scope, 'home', 'entry_returned', proof)
    data = store.data
    assert data['active'] is None and data['completed_runs'] == 0 and data['rotation'] == 0
    assert data['receipts'] == []
    filed, = data['abandoned']
    assert filed['id'] == scope and filed['lost'] and filed['reward'] and filed['floors'] == [1, 2, 3, 4]
    assert 'partial rewards were claimed' in filed['note'] and filed['abandoned_at']
    # The same team starts the next run.
    assert store.team_slot == 2


def test_a_run_is_lost_or_won_never_both(tmp_path):
    store, scope, proof = ledger(tmp_path, floors=5)
    store.record(scope, 'victory', 'final_victory', proof)
    assert payout_state(store.data['active']) == 'won'
    with pytest.raises(ValueError, match='was not lost'):
        store.record(scope, 'native-lost-summary', 'run_lost', proof)
    assert payout_state(dict(id='x', floors=[1, 2, 3, 4, 5], victory=True, lost=True)) == 'won'
    assert payout_state(dict(id='x', floors=[1, 2], victory=False, lost=True)) == 'lost'
    assert payout_state(dict(floors=[1, 2], lost=True)) is None and payout_state(None) is None


def test_the_choice_for_lost_runs_is_saved_beside_the_standing_limit(tmp_path):
    path = tmp_path / 'user-mirror-settings.json'
    assert apply_standing(tmp_path, 'claim', 'claim') == 'saved'
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved[STANDING] == 18 and saved[LOST] is True and lost_claim_allowed(saved)
    # "Do not claim lost runs" keeps the limit for cleared runs.
    assert apply_standing(tmp_path, 'claim', 'off') == 'saved'
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved[STANDING] == 18 and LOST not in saved and not lost_claim_allowed(saved)
    # A pipeline built before the choice existed says `saved`: nothing changes.
    apply_standing(tmp_path, 'claim', 'claim')
    assert apply_standing(tmp_path, 'claim') == 'unchanged'
    assert json.loads(path.read_text(encoding='utf-8'))[LOST] is True
    # Claiming switched off altogether takes the lost-run choice with it.
    apply_standing(tmp_path, 'off', 'claim')
    assert json.loads(path.read_text(encoding='utf-8')) == {}
    with pytest.raises(ValueError):
        apply_standing(tmp_path, 'claim', 'sometimes')


def lost_run(tmp_path, *, chosen=True):
    store, scope, proof = ledger(tmp_path)
    store.record(scope, 'native-lost-summary', 'run_lost', proof)
    apply_standing(tmp_path, 'claim', 'claim' if chosen else 'off')
    return store, scope, proof


def test_a_lost_run_is_claimed_through_the_dialogs_own_claim_when_chosen(tmp_path):
    store, scope, proof = lost_run(tmp_path)
    frame = tmp_path / 'frame-0004.json'
    write_json(frame, dialog())
    assert prepare('claim', dialog(), tmp_path, scope, str(frame)) == [1238, 796, 98, 41]
    tx = json.loads((tmp_path / 'user-reward-claim-transaction.json').read_text(encoding='utf-8'))
    assert tx['scope'] == scope and tx['offer'] == dict(currency='enkephalin_modules', cost=5, weekly=0)


def test_a_lost_run_is_not_claimed_unless_the_user_chose_it(tmp_path):
    store, scope, proof = lost_run(tmp_path, chosen=False)
    with pytest.raises(ValueError, match='lost run was not chosen'):
        prepare('claim', dialog(), tmp_path, scope, 'frame')
    assert not (tmp_path / 'user-reward-claim-transaction.json').exists()


def test_a_lost_run_never_spends_a_weekly_bonus(tmp_path):
    store, scope, proof = lost_run(tmp_path)
    with pytest.raises(ValueError, match='does not spend weekly bonuses'):
        prepare('claim', dialog(weekly=1, cost=6), tmp_path, scope, 'frame')
    assert not (tmp_path / 'user-reward-claim-transaction.json').exists()


def test_the_dialog_and_the_ledger_must_tell_the_same_story(tmp_path):
    # The ledger says lost, the dialog shows a cleared floor 5: not this run's dialog.
    store, scope, proof = lost_run(tmp_path)
    with pytest.raises(ValueError, match='disagrees with the ledger'):
        prepare('claim', dialog(count='4/4'), tmp_path, scope, 'frame')
    # The ledger says won, the dialog shows an unfinished floor.
    won = tmp_path / 'won'
    won.mkdir()
    store, scope, proof = ledger(won, floors=5)
    store.record(scope, 'victory', 'final_victory', proof)
    apply_standing(won, 'claim', 'claim')
    with pytest.raises(ValueError, match='disagrees with the ledger'):
        prepare('claim', dialog(), won, scope, 'frame')
    frame = won / 'frame.json'
    write_json(frame, dialog(count='4/4'))
    assert prepare('claim', dialog(count='4/4'), won, scope, str(frame)) == [1238, 796, 98, 41]


def summary_frame(tmp_path, scene, texts):
    import cv2
    import numpy as np
    record = tmp_path / 'frame-0002.json'
    picture = record.with_suffix('.png')
    assert cv2.imwrite(str(picture), np.zeros((1080, 1920, 3), dtype=np.uint8))
    write_json(record, dict(scene=scene, size=[1920, 1080],
                            image_sha256=hashlib.sha256(picture.read_bytes()).hexdigest(),
                            ocr=[dict(text=text, box=list(box), score=score) for text, box, score in texts]))
    return record


@pytest.mark.parametrize('scene, texts, lost', [
    ('EXPLORATION_COMPLETE', [('Exploration', (210, 108, 160, 30), .99), ('Complete', (210, 140, 130, 30), .99),
                              ('95%', (232, 520, 90, 38), .99)], True),
    ('EXPLORATION_COMPLETE', [('Exploration', (210, 108, 160, 30), .99), ('Complete', (210, 140, 130, 30), .99)], False),
    ('RUN_REWARD_DIALOG', DIALOG, True),
    ('RUN_REWARD_DIALOG', [(('4/4' if text == '3/4' else text), box, score) for text, box, score in DIALOG], False),
    ('MAP', DIALOG, False),
])
def test_the_runner_records_a_lost_run_from_the_summary_or_from_its_dialog(tmp_path, scene, texts, lost):
    from maalimbus import runner
    from maalimbus.native_evidence import observation_frame
    store, scope, proof = ledger(tmp_path)
    record = summary_frame(tmp_path, scene, texts)
    loop = runner.MirrorRunner(runner.FakeDevice(), settings={}, store=store, run_id=scope, directory=tmp_path)
    loop.configure()
    observation, _, _ = observation_frame(tmp_path, dict(frame=record.stem))
    loop._observe_lost_summary(observation)
    assert bool(store.data['active'].get('lost')) is lost
    if lost:
        assert store.data['active']['events']['native-lost-summary']['evidence'] == str(record.resolve())
        # Seen again, it is the same fact.
        loop._observe_lost_summary(observation)
        assert payout_state(store.data['active']) == 'lost'


def test_the_paid_stage_lets_a_lost_run_through_only_by_choice(tmp_path, monkeypatch):
    from maalimbus import reward_task, runner
    store, scope, proof = lost_run(tmp_path, chosen=False)
    loop = runner.MirrorRunner(runner.FakeDevice(), settings=runner.settings({'run_count': 1}), store=store,
                               run_id=scope, directory=tmp_path)
    loop.configure()
    calls = []

    def execute(config, directory, observer, device, journal, *, deadline):
        calls.append(config)
        store.record(scope, 'receipt', 'reward_received', proof)
        store.record(scope, 'home', 'entry_returned', proof)
        return dict(reward_received=True, lost=True, input_attempts=3, reason='lost_run_payout_and_home_verified')

    monkeypatch.setattr(reward_task, 'execute', execute)
    page = dict(scene='RUN_REWARD_DIALOG')
    stopped = loop._paid_reward_handoff(page['scene'], page, None, [])
    assert stopped['stopped'] == 'lost_run_claim_not_chosen' and not calls
    apply_standing(tmp_path, 'claim', 'claim')
    paid = loop._paid_reward_handoff(page['scene'], page, None, [])
    assert len(calls) == 1 and paid['page'] == 'HOME' and not paid.get('done')
    # Home again, but not a clear: nothing is counted and the run count is not reached.
    assert loop.artifacts['verified_clear'] is False and loop.artifacts['clicks_sent'] == 3
    assert loop.store.data['completed_runs'] == 0 and loop.store.data['active'] is None


def test_the_choice_is_a_sub_option_of_claiming_and_reaches_the_pipeline():
    interface = json.loads((ROOT / 'assets/interface.json').read_bytes())
    parent = interface['option']['mirror_reward_claim']
    claim = next(case for case in parent['cases'] if case['name'] == 'claim')
    off = next(case for case in parent['cases'] if case['name'] == 'off')
    # Only asked while claiming is on.
    assert claim['option'] == ['mirror_reward_claim_lost'] and 'option' not in off
    option = interface['option']['mirror_reward_claim_lost']
    assert option['default_case'] == 'claim' and [case['name'] for case in option['cases']] == ['claim', 'off']
    for case in option['cases']:
        assert case['pipeline_override'] == {'MirrorRewardClaimLost': {'attach': {'lost': case['name']}}}
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_bytes())
    assert pipeline['MirrorRewardClaimLost']['attach'] == dict(lost='claim')
    words = json.loads((ROOT / 'assets/i18n/zh_cn.json').read_text(encoding='utf-8'))
    assert '放弃奖励' in words['mirror_reward_claim_lost_description']


def test_give_up_rewards_stays_forbidden_and_no_name_says_otherwise():
    from maalimbus import window
    assert 'run_reward.give_up_button' in window.FORBIDDEN_CONTROLS
    row = window.STEP_ROWS['EXPLORATION_COMPLETE']
    assert row['reason'] == 'a_lost_run_opens_its_reward_dialog' and 'give' not in row['reason']
    plan = window.plan_step('RUN_REWARD_DIALOG', controls={'run_reward.give_up_button': [448, 792, 280, 45]})
    assert plan.get('target') != [448, 792, 280, 45]


def lost_bookkeeping(tmp_path, monkeypatch):
    """A lost run whose claim chain was sent; the frame audit itself has its own tests."""
    import maalimbus.reward_task as task
    from maalimbus.policies import Team
    from maalimbus.storage import ProfileStore
    ProfileStore(tmp_path / 'user-team-profiles.json').save([Team(2, frozenset({'Charge'})), Team(5, frozenset({'Burn'}))])
    store, scope, proof = lost_run(tmp_path)
    home = tmp_path / 'frame-0009.json'
    home.write_text('{"scene": "HOME"}', encoding='utf-8')
    write_json(tmp_path / 'user-reward-claim-transaction.json',
               dict(scope=scope, completed=False, claim_sent=True, confirm_sent=True, receipt_ack_sent=True,
                    pass_ack_sent=True, receipt_proof=str(proof), task_input_reports={}))
    monkeypatch.setattr(task, 'verify', lambda tx, home_path, reports: dict(proofs=['stub']))
    monkeypatch.setattr('maalimbus.shop_outcomes.refresh_scope', lambda *a, **k: None)
    return task, scope, home


def test_bookkeeping_files_the_lost_run_and_closes_the_transaction(tmp_path, monkeypatch):
    task, scope, home = lost_bookkeeping(tmp_path, monkeypatch)
    result = task.finish(tmp_path, scope, home)
    assert result['passed'] and result['lost'] and result['reason'] == 'lost_run_payout_and_home_verified'
    data = json.loads((tmp_path / 'user-run-ledger.json').read_text(encoding='utf-8'))
    assert data['active'] is None and data['completed_runs'] == 0 and data['rotation'] == 0 and data['receipts'] == []
    filed, = data['abandoned']
    assert filed['id'] == scope and filed['lost'] and filed['reward']
    assert set(filed['events']) >= {'native-lost-summary', 'native-reward-task-receipt', 'native-reward-task-home'}
    tx = json.loads((tmp_path / 'user-reward-claim-transaction.json').read_text(encoding='utf-8'))
    assert tx['completed'] and tx['reward_received'] and tx['home_return_proof'] == str(home)
    # Done once: a second call has nothing left to finish.
    with pytest.raises(ValueError, match='missing or already complete'):
        task.finish(tmp_path, scope, home)


def test_a_crash_after_filing_finishes_the_transaction_without_filing_twice(tmp_path, monkeypatch):
    task, scope, home = lost_bookkeeping(tmp_path, monkeypatch)
    original = task.write_json

    def fail_completion(path, data):
        if Path(path).name == 'user-reward-claim-transaction.json' and data.get('completed'):
            raise OSError('injected final write failure')
        return original(path, data)

    monkeypatch.setattr(task, 'write_json', fail_completion)
    with pytest.raises(OSError):
        task.finish(tmp_path, scope, home)
    before = (tmp_path / 'user-run-ledger.json').read_bytes()
    monkeypatch.setattr(task, 'write_json', original)
    result = task.execute(tmp_path, tmp_path, SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    assert result['passed'] and result['lost'] and not result['input_sent']
    assert (tmp_path / 'user-run-ledger.json').read_bytes() == before
    assert json.loads((tmp_path / 'user-reward-claim-transaction.json').read_text(encoding='utf-8'))['completed']


#: The pass popup over the summary of the lost run, pi-20261123-235849/frame-0006.
POPUP = [('Exploration', (234, 138, 238, 48), 1.0), ('Complete', (250, 188, 202, 50), 1.0),
         ('Dungeon Progress', (210, 254, 282, 39), 1.0), ('Pass Level Up', (830, 351, 258, 40), 1.0),
         ('Pass Level', (594, 466, 106, 22), 1.0), ('Battle Pass XP', (782, 470, 242, 40), 1.0),
         ('40', (1592, 456, 76, 74), 1.0), ('228', (554, 488, 180, 129), 1.0), ('Last Reached', (236, 480, 220, 40), 1.0),
         ('Floor 5 [HARD]', (262, 613, 178, 34), .98), ('Confirm', (882, 680, 162, 48), 1.0),
         ('Total Progress', (234, 706, 234, 40), 1.0), ('95%', (296, 760, 132, 89), .99),
         ('Claim', (1680, 861, 86, 36), 1.0), ('Rewards', (1658, 897, 130, 34), 1.0)]


def popup(starlight='40', percent='95%'):
    return dict(scene='EXPLORATION_COMPLETE', size=[1920, 1080],
                ocr=[dict(text=starlight if text == '40' else percent if text == '95%' else text, box=list(box), score=score)
                     for text, box, score in POPUP])


def test_the_pass_popup_over_the_lost_summary_is_the_receipt():
    from maalimbus.paid_reward_action import summary_pass_receipt
    assert summary_pass_receipt(dialog(), popup()) == dict(starlight_offer=40, summary_starlight=40, total_percent=95)
    # Another amount under the popup, a cleared summary, or no summary at all proves nothing.
    assert summary_pass_receipt(dialog(), popup(starlight='65')) is None
    assert summary_pass_receipt(dialog(), popup(percent='100%')) is None
    assert summary_pass_receipt(dialog(), dialog()) is None


def claimed_and_confirmed(tmp_path):
    store, scope, proof = lost_run(tmp_path)
    frame = tmp_path / 'frame-0002.json'
    write_json(frame, dialog())
    prepare('claim', dialog(), tmp_path, scope, str(frame))
    path = tmp_path / 'user-reward-claim-transaction.json'
    tx = json.loads(path.read_text(encoding='utf-8'))
    tx.update(claim_sent=True, confirm_sent=True, pending='confirm')
    write_json(path, tx)
    return store, scope, path


def test_a_lost_run_acknowledges_its_pass_popup_on_that_receipt(tmp_path):
    store, scope, path = claimed_and_confirmed(tmp_path)
    assert prepare('pass', popup(), tmp_path, scope, 'frame-0006') == [882, 680, 162, 48]
    tx = json.loads(path.read_text(encoding='utf-8'))
    assert tx['receipt_kind'] == 'summary_pass_popup' and tx['receipt_ack_sent'] and tx['pass_ack_sent']
    assert tx['receipt_visible_amount'] == 40 and tx['pass_level'] == 228
    assert tx['receipt_proof'] == 'frame-0006' == tx['pass_receipt_proof']
    # Acknowledged once.
    with pytest.raises(ValueError, match='absent or repeated'):
        prepare('pass', popup(), tmp_path, scope, 'frame-0007')


def test_a_popup_that_does_not_match_the_offer_is_not_acknowledged(tmp_path):
    store, scope, path = claimed_and_confirmed(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='absent or repeated'):
        prepare('pass', popup(starlight='65'), tmp_path, scope, 'frame-0006')
    assert path.read_bytes() == before
