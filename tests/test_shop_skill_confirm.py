"""The shop's skill replacement buys: Confirm after a proven selection, then a receipt.

Until 2026-11-27 the flow opened the chooser, selected the card and cancelled, so the
option left the interface as a check that never bought. The user asked for it back as a
purchase. What the game shows after Confirm has not been seen yet, so the press is
settled on whichever page follows: the chooser (counts and coins), the shelf (coins), or
nothing changed (no purchase; Cancel next, never a second Confirm).
"""
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from maalimbus import pre_battle_identity
from maalimbus.shop_skill_policy import propose_replacement
from maalimbus.shop_skill_vision import read_replacement_modal
from maalimbus.shop_transaction import ShopTransaction, _frame
from maalimbus.storage import write_json
from maalimbus.vision import Text
from maalimbus.window import plan_step

from test_shop_skill_modal import modal_rows, tier_rows   # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[1]
COUNTS = 'SKILL1x3 SKILL2x2 SKILL3X1'


@pytest.fixture
def selected(tmp_path, modal_rows, monkeypatch):
    """A visit whose chooser for Don Quixote was opened and whose card was selected."""
    def capture(index, rows, scene='UNKNOWN_DIALOG'):
        path = tmp_path / f'frame-{index:04}.json'
        image = bytes([index])
        path.with_suffix('.png').write_bytes(image)
        write_json(path, dict(scene=scene, size=[1280, 720], utc='2026-11-27T06:00:%02d+00:00' % index,
                              ocr=[dict(text=row.text, box=list(row.box), score=row.score) for row in rows],
                              image_sha256=hashlib.sha256(image).hexdigest()))
        return path

    deployment = dict(submitted=True)
    monkeypatch.setattr(pre_battle_identity, 'submitted_identity', lambda value, scope, sinner:
                        dict(role='frontline', identity_id=10301) if value == deployment and sinner == 'Don Quixote' else None)
    rows = modal_rows + tier_rows()
    shelf = _frame(capture(1, [Text('2283', (567, 120, 53, 23), .99)], 'SHOP'))[3]
    tx_path = tmp_path / 'shop.json'
    write_json(tx_path, dict(version=1, scope='scope', current_visit='1', bought=[],
                             visits={'1': dict(entry=shelf, refreshes=0, closed=False)},
                             pending=dict(kind='skill_service', stage='skill_open_intent', scope='scope', visit='1',
                                          coins=2283, before=shelf, shelf=[], click=[710, 330, 135, 18],
                                          skill=dict(sinner='Don Quixote', mode='keep_one_each', reserve_coins=500))))
    tx = ShopTransaction(tx_path)
    chooser = capture(2, rows)
    reading = read_replacement_modal(rows, (1280, 720))
    choice = propose_replacement(reading, 'keep_one_each', 500)
    tx.reserve_skill_selection('scope', '1', chooser, 'keep_one_each', 500, deployment, list(choice.quote.select_box))
    after_selection = capture(3, rows)
    assert tx.reconcile_skill_service('scope', '1', after_selection) == 'chooser'
    return tx, capture, rows, reading, deployment, after_selection


def test_confirm_is_reserved_once_after_a_proven_selection(selected):
    tx, capture, rows, reading, deployment, chooser = selected
    plan = plan_step('UNKNOWN_DIALOG', controls={'shop.skill_confirm': list(reading.confirm_box)})
    assert plan['control_id'] == 'shop.skill_confirm' and plan['target'] == list(reading.confirm_box)
    assert plan['reason'] == 'select_proven_shop_skill_replacement'     # no new reason word
    with pytest.raises(ValueError, match='not proven'):
        tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_each', 500, deployment, list(reading.cancel_box))
    with pytest.raises(ValueError, match='only once'):
        tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_s2', 500, deployment, plan['target'])
    assert tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_each', 500, deployment, plan['target']) == plan['target']
    pending = ShopTransaction(tx.path).data['pending']
    assert (pending['kind'], pending['stage'], pending['price'], pending['skill']['from_tier']) == (
        'skill_replacement', 'skill_confirm_intent', 75, 2)
    with pytest.raises(ValueError):
        tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_each', 500, deployment, plan['target'])


def test_a_confirm_that_bought_is_booked_on_the_chooser_or_on_the_shelf(selected, tmp_path):
    tx, capture, rows, reading, deployment, chooser = selected
    tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_each', 500, deployment, list(reading.confirm_box))
    saved = tx.path.read_bytes()
    bought = capture(4, [replace(row, text={'2283': '2208', COUNTS: 'SKILL1x3 SKILL2x1 SKILL3X2'}.get(row.text, row.text))
                         for row in rows])
    receipt = tx.reconcile_skill_replacement('scope', '1', bought)
    assert (receipt['counts_after'], receipt['coins_after'], receipt['price']) == ([3, 1, 2], 2208, 75)
    assert tx.data['pending'] is None and tx.data['coins_proven'] == 2208 and tx.held_coins() == (2208,)
    # The same Confirm settled on the shelf instead: the coin counter alone.
    tx.path.write_bytes(saved)
    tx = ShopTransaction(tx.path)
    receipt = tx.reconcile_skill_replacement('scope', '1', capture(5, [Text('2208', (567, 120, 53, 23), .99)], 'SHOP'))
    assert receipt['settled_on'] == 'shelf' and receipt['coins_after'] == 2208 and receipt['counts_after'] is None
    assert tx.data['visits']['1']['skill_receipts'][-1] == receipt


def test_a_confirm_that_changed_nothing_is_cancelled_and_never_pressed_again(selected):
    tx, capture, rows, reading, deployment, chooser = selected
    tx.reserve_skill_confirm('scope', '1', chooser, 'keep_one_each', 500, deployment, list(reading.confirm_box))
    saved = tx.path.read_bytes()
    same = capture(4, rows)
    assert tx.reconcile_skill_replacement('scope', '1', same) == dict(unspent=True, settled_on='chooser')
    pending = tx.data['pending']
    assert pending['kind'] == 'skill_service' and pending['confirm_unspent'] and pending['selection']
    # The next chooser is read as the open intent's own, and only Cancel may follow.
    with pytest.raises(ValueError, match='independent'):
        tx.reconcile_skill_service('scope', '1', same)
    later = capture(5, rows)
    assert tx.reconcile_skill_service('scope', '1', later) == 'chooser'
    with pytest.raises(ValueError, match='only once'):
        tx.reserve_skill_confirm('scope', '1', later, 'keep_one_each', 500, deployment, list(reading.confirm_box))
    tx.reserve_skill_service_cancel('scope', '1', later, list(reading.cancel_box))
    assert tx.reconcile_skill_service('scope', '1', capture(6, [Text('2283', (567, 120, 53, 23), .99)], 'SHOP')) == 'shelf'
    assert tx.data['pending'] is None
    # A shelf that shows the same coins after Confirm also means nothing was bought.
    tx.path.write_bytes(saved)
    tx = ShopTransaction(tx.path)
    assert tx.reconcile_skill_replacement('scope', '1', capture(7, [Text('2283', (567, 120, 53, 23), .99)], 'SHOP')) == dict(
        unspent=True, settled_on='shelf')
    assert tx.data['pending'] is None
    # Any other coin count keeps the press pending.
    tx.path.write_bytes(saved)
    tx = ShopTransaction(tx.path)
    with pytest.raises(ValueError, match='preserve pending'):
        tx.reconcile_skill_replacement('scope', '1', capture(8, [Text('2100', (567, 120, 53, 23), .99)], 'SHOP'))
    assert tx.path.read_bytes() == saved


def test_the_option_is_back_in_the_mirror_task_as_a_purchase():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    task = next(task for task in pi['task'] if task['name'] == 'mirror_loop')
    assert 'mirror_shop_skill_mode' in task['option']
    option = pi['option']['mirror_shop_skill_mode']
    assert option['default_case'] == 'off'
    # A switch since 2026-11-28; whose skills and which copies to keep sit under "on"
    # (tests/test_shop_skill_choice.py).
    assert [case['name'] for case in option['cases']] == ['off', 'on']
    text = json.loads((ROOT / 'assets/i18n/zh_cn.json').read_text(encoding='utf-8'))
    assert 'Confirm' in text['mirror_shop_skill_mode_description'] and '核验' not in text['mirror_shop_skill_mode']
    source = (ROOT / 'src/maalimbus/runner.py').read_text(encoding='utf-8')
    assert "plan_controls['shop.skill_confirm']=list(replacement.confirm_box)" in source
    assert "shop_tx.reserve_skill_confirm(" in source
