"""A payout claimed from the dungeon list has no receipt page and returns to the entry page.

On 2026-11-23 the game was closed on the reward dialog. Entering the Mirror Dungeon again
reopened the dialog ("To List" instead of "To Window"); Claim and Confirm were sent, and
the next page was the pass popup over the entry page. The "Rewards Acquired" page of the
other route never appeared, so the payout chain refused the pass popup and the run stayed
unbooked although the rewards had arrived (pi-20261123-182337). The rows below are
retyped from that run's frames 4 (the dialog) and 9 (the pass popup).
"""
import copy
from pathlib import Path

import pytest

from maalimbus import page_names, pages, reward_task
from maalimbus.paid_reward_action import entry_balance_receipt, prepare
from maalimbus.storage import read_json, write_json


def row(text, box, score=1.0):
    return dict(text=text, box=list(box), score=score)


def dialog():
    return dict(scene='RUN_REWARD_DIALOG', size=[1920, 1080],
                reward_cost=dict(currency='enkephalin_modules', cost=5, weekly=0), ocr=[
        row('Floor 5', (480, 617, 84, 30), .98), row('4/4', (490, 678, 64, 52), .65), row('0/3', (660, 345, 84, 69)),
        row('65', (720, 680, 48, 46)), row('50/1000', (1368, 371, 114, 43)), row('x50', (1380, 631, 94, 51), .98),
        row('EXP 100', (1384, 704, 92, 44), .98), row('0x30', (1392, 579, 84, 48), .88), row('-5', (1436, 798, 36, 37), .86),
        row('★3220', (1630, 136, 148, 64), .85), row('50/1000', (1664, 412, 120, 42)),
        row('Claim', (1242, 796, 94, 41))])


def pass_popup(starlight='3285', cap='100/1000'):
    return dict(scene='PASS_LEVEL_UP', size=[1920, 1080], ocr=[
        row('226', (554, 488, 182, 127)), row('Pass Level', (594, 468, 106, 20)), row('Battle Pass XP', (782, 470, 242, 40)),
        row('00000000', (826, 516, 460, 75), .98), row('Pass Level Up', (830, 353, 258, 40)),
        row('Confirm', (876, 682, 168, 46)), row('Before Entry', (1588, 218, 142, 34)), row('Enter', (1606, 718, 112, 44)),
        row(starlight, (1630, 136, 148, 64)), row(cap, (1652, 412, 132, 42))])


def test_both_balances_grown_by_exactly_the_offer_are_the_receipt():
    assert entry_balance_receipt(dialog(), pass_popup()) == dict(
        starlight_before=3220, cap_before=50, starlight_offer=65, projection_offer=50,
        starlight_after=3285, cap_after=100)


@pytest.mark.parametrize('after', [
    pass_popup('3220', '50/1000'),       # nothing arrived yet (the confirmation page)
    pass_popup('3285', '50/1000'),       # only one of the two changed
    pass_popup('3290', '100/1000'),      # grew, but not by the offer
    pass_popup('3285', '100/100'),       # the cap is not readable as N/1000
])
def test_any_other_difference_proves_nothing(after):
    assert entry_balance_receipt(dialog(), after) is None


def test_a_missing_or_doubtful_number_proves_nothing():
    for index in (3, 5, 9, 10):          # the 65, the x50, the starlight, the cap
        claim = dialog()
        claim['ocr'][index]['score'] = .5
        assert entry_balance_receipt(claim, pass_popup()) is None
    small = pass_popup()
    small['size'] = [1280, 720]
    assert entry_balance_receipt(dialog(), small) is None


def started(tmp_path):
    """A transaction with Claim and Confirm sent, its claim frame saved where it says."""
    write_json(tmp_path / 'user-mirror-settings.json', dict(auto_claim_modules=5))
    write_json(tmp_path / 'user-run-ledger.json',
               dict(active=dict(id='run', floors=[1, 2, 3, 4, 5], victory=True, reward=False)))
    claim = tmp_path / 'frame-0004.json'
    write_json(claim, dialog())
    prepare('claim', dialog(), tmp_path, 'run', str(claim))
    tx = read_json(tmp_path / 'user-reward-claim-transaction.json')
    tx.update(confirm_sent=True, pending='confirm', confirm_proof=str(tmp_path / 'frame-0006.json'))
    write_json(tmp_path / 'user-reward-claim-transaction.json', tx)
    return tmp_path / 'user-reward-claim-transaction.json'


def test_the_pass_popup_is_acknowledged_on_the_balance_receipt(tmp_path):
    path = started(tmp_path)
    assert prepare('pass', pass_popup(), tmp_path, 'run', 'frame-0009') == [876, 682, 168, 46]
    tx = read_json(path)
    assert tx['receipt_kind'] == 'entry_balances' and tx['receipt_ack_sent'] and tx['pass_ack_sent']
    assert tx['receipt_proof'] == tx['pass_receipt_proof'] == 'frame-0009'
    assert tx['receipt_visible_amount'] == 65 and tx['pass_level'] == 226
    assert tx['receipt_balances']['cap_after'] == 100 and not tx['reward_received']
    with pytest.raises(ValueError, match='absent or repeated'):
        prepare('pass', pass_popup(), tmp_path, 'run', 'again')


def test_without_the_balances_the_pass_popup_is_still_refused(tmp_path):
    path = started(tmp_path)
    before = read_json(path)
    with pytest.raises(ValueError, match='absent or repeated'):
        prepare('pass', pass_popup('3220', '50/1000'), tmp_path, 'run', 'frame-0009')
    assert read_json(path) == before
    # Nor without a confirmation that was sent.
    write_json(path, dict(before, confirm_sent=False))
    with pytest.raises(ValueError, match='absent or repeated'):
        prepare('pass', pass_popup(), tmp_path, 'run', 'frame-0009')


def test_the_entry_page_is_the_return_page_only_for_that_finished_route(tmp_path):
    path = started(tmp_path)
    entry = dict(scene='MIRROR_ENTRY', size=[1920, 1080], ocr=[])
    assert reward_task.entry_return(tmp_path, 'run', entry) is False            # the pass is not acknowledged
    prepare('pass', pass_popup(), tmp_path, 'run', 'frame-0009')
    assert reward_task.entry_return(tmp_path, 'run', entry) is True
    # pi-20261123-184215/frame-0005: after the pass popup the game asks whether to enter.
    assert reward_task.entry_return(tmp_path, 'run', dict(entry, scene='ENTRY_CONFIRM')) is True
    assert reward_task.entry_return(tmp_path, 'another-run', entry) is False
    assert reward_task.entry_return(tmp_path, '', entry) is False
    assert reward_task.entry_return(tmp_path, 'run', dict(entry, scene='HOME')) is False
    write_json(path, dict(read_json(path), completed=True))
    assert reward_task.entry_return(tmp_path, 'run', entry) is False            # a new run may start here again
    assert reward_task.entry_return(tmp_path / 'absent', 'run', entry) is False


def test_the_audit_takes_the_balance_receipt_in_place_of_the_receipt_page(tmp_path, monkeypatch):
    from maalimbus import reward_receipt_audit as audit
    records = dict(
        claim=dialog(),
        confirm=dict(scene='RUN_REWARD_CONFIRM', size=[1920, 1080], ocr=[
            row('Claim the rewards?', (816, 502, 284, 34)), row('× Cancel', (702, 724, 140, 36), .92),
            row('Confirm', (1116, 720, 112, 40))]),
        receipt_or_pass=pass_popup(),
        home=dict(scene='MIRROR_ENTRY', size=[1920, 1080], ocr=[
            row('Before Entry', (1588, 218, 142, 34)), row('Enter', (1606, 718, 112, 44))]))
    frames = {'c.json': records['claim'], 'f.json': records['confirm'], 'p.json': records['receipt_or_pass'],
              'h.json': records['home']}
    monkeypatch.setattr(audit, 'load_frame', lambda path: (
        frames[Path(path).name], dict(frame=str(path), png_sha256=Path(path).name)))

    def report(action, record, frame, caption):
        target = next(item['box'] for item in record['ocr'] if item['text'] == caption)
        return dict(run_ledger=dict(run='run'), clicks_sent=1, steps=[dict(
            label='paid_reward_' + action, action='click', observation=dict(image_sha256=frame), target=target,
            click_point=[target[0] + 5, target[1] + 5], delay_ms=500)])
    reports = dict(claim=report('claim', records['claim'], 'c.json', 'Claim'),
                   confirm=report('confirm', records['confirm'], 'f.json', 'Confirm'),
                   **{'pass': report('pass', records['receipt_or_pass'], 'p.json', 'Confirm')})
    tx = dict(scope='run', claim_sent=True, confirm_sent=True, receipt_ack_sent=True, pass_ack_sent=True,
              receipt_kind='entry_balances', receipt_visible_amount=65, pass_level=226,
              claim_proof='c.json', confirm_proof='f.json', receipt_proof='p.json', pass_receipt_proof='p.json',
              offer=dict(currency='enkephalin_modules', cost=5, weekly=0), reserved_modules=5)
    proof = audit.verify(tx, 'h.json', reports)
    assert proof['payout_received'] and proof['actual_amount'] == 65 and proof['actual_pass_level'] == 226
    assert [item['png_sha256'] for item in proof['proofs']] == ['c.json', 'f.json', 'p.json', 'h.json']
    question = dict(scene='ENTRY_CONFIRM', size=[1920, 1080], ocr=[
        row('X Cancel', (708, 704, 152, 42), .93), row('Will you enter Mirror of Sisyphe?', (716, 498, 486, 40)),
        row('Enter', (1124, 704, 90, 42))])
    frames['h.json'] = question
    assert audit.verify(tx, 'h.json', reports)['home_return'] is True
    frames['h.json'] = dict(question, ocr=question['ocr'][:2])          # the question without its Enter
    with pytest.raises(ValueError):
        audit.verify(tx, 'h.json', reports)
    # The lobby is not this route's return page, and the route is not a way round the receipt page.
    frames['h.json'] = dict(scene='HOME', size=[1920, 1080], ocr=[])
    with pytest.raises(ValueError, match='entry-page successor'):
        audit.verify(tx, 'h.json', reports)
    frames['h.json'] = records['home']
    with pytest.raises(ValueError):
        audit.verify(dict(tx, receipt_kind=None), 'h.json', reports)
    stale = copy.deepcopy(records['receipt_or_pass'])
    stale['ocr'][-2]['text'] = '3220'
    frames['p.json'] = stale
    with pytest.raises(ValueError, match='do not prove'):
        audit.verify(tx, 'h.json', reports)


def test_every_registered_page_has_a_name_a_player_would_use():
    missing = sorted(set(pages.PAGES) - set(page_names.NAMES))
    assert not missing, 'pages without a name in the task log: %s' % missing
    assert page_names.name('SHOP') == '商店（SHOP）' and page_names.name('NEW_PAGE') == 'NEW_PAGE'
    assert page_names.name(None) == '未识别的画面'


def test_the_task_log_names_each_recognised_page_without_repeating_itself():
    memory, lines = {}, []
    steps = [('MIRROR_ENTRY', dict(input_sent=True)), ('RUN_REWARD_DIALOG', dict(waiting=True))]
    steps += [('BATTLE_HUD', dict(waiting=True))] * 12 + [('BATTLE_HUD', dict(input_sent=True))]
    steps += [('SHOP', dict(stopped='shop_stopped'))]
    for number, (page, flags) in enumerate(steps, 1):
        line = page_names.step_line(memory, number, page, **flags)
        if line:
            lines.append(line)
    assert lines == ['第 1 步 · 画面：镜牢入口（MIRROR_ENTRY） · 已操作',
                     '第 2 步 · 画面：通关奖励（领取／放弃）（RUN_REWARD_DIALOG） · 观察等待',
                     '第 3 步 · 画面：战斗中（BATTLE_HUD） · 观察等待',
                     '第 12 步 · 画面：战斗中（BATTLE_HUD） · 观察等待（同一画面已连续 10 步）',
                     '第 15 步 · 画面：战斗中（BATTLE_HUD） · 已操作',
                     '第 16 步 · 画面：商店（SHOP） · 在此停止']


def test_the_loop_and_the_payout_both_write_what_they_recognised():
    root = Path(__file__).resolve().parents[1]
    runner = (root / 'src/maalimbus/runner.py').read_text(encoding='utf-8')
    assert runner.index("self.journal.record('step_finished'") < runner.index('step_line(memory')
    assert 'reward_task.entry_return(config, self.run_id, record)' in runner
    payout = (root / 'src/maalimbus/reward_task.py').read_text(encoding='utf-8')
    assert "record.get('scene')=='HOME' or entry_return(config,scope,record)" in payout
