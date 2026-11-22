"""A refresh can cost nothing; the button's own price rise is then the proof it registered.

Live ``pi-20261122-004911`` (2026-11-22), floor 4 Super Shop: 2383 coins before the
refresh and after it, while the shelf restocked and the regular refresh price rose
15 -> 30 (keyword 90 -> 105), as it does after a paid refresh (floor 1: 852 -> 837,
15 -> 30). The run stopped with "Fresh refresh currency delta and complete changed
shelf not proven". The rows below are synthetic in that layout; the live frames are
local evidence.
"""
import pytest

from test_shop_transaction import frame, row, shelf
from maalimbus.shop_transaction import ShopTransaction


def after(tmp_path, label, coins, next_price, names=('Voodoo Doll', 'Bone Stake')):
    rows = [r for r in shelf(names, coins) if r['text'] != '15']
    if next_price is not None:
        rows.append(row(str(next_price), (1510, 210, 40, 30)))
    return frame(tmp_path, label, rows)


def reserved(tmp_path):
    before = frame(tmp_path, 'before', shelf())
    tx = ShopTransaction(tmp_path / 'tx.json')
    tx.begin_visit('scope', 'floor4:shop1', before)
    tx.reserve_refresh('scope', 'floor4:shop1', 15, 100, 1, before)
    return tx


def test_a_free_refresh_with_a_risen_price_is_reconciled(tmp_path):
    tx = reserved(tmp_path)
    assert tx.reconcile_refresh('scope', 'floor4:shop1', after(tmp_path, 'free', 100, 30)) is True
    receipt = tx.data['visits']['floor4:shop1']['refresh_receipts'][-1]
    assert receipt['paid'] == 0 and receipt['free'] is True and receipt['next_price'] == 30
    assert tx.data['pending'] is None and tx.refreshes_used('scope', 'floor4:shop1') == 1


def test_a_paid_refresh_is_booked_as_before(tmp_path):
    tx = reserved(tmp_path)
    assert tx.reconcile_refresh('scope', 'floor4:shop1', after(tmp_path, 'paid', 85, 30)) is True
    receipt = tx.data['visits']['floor4:shop1']['refresh_receipts'][-1]
    assert receipt['paid'] == 15 and 'free' not in receipt


@pytest.mark.parametrize('coins, next_price', [(100, 15),     # nothing shows the press registered
                                               (100, None),   # the price is unreadable
                                               (95, 30),      # a delta that is neither 0 nor the price
                                               (115, 30)])    # coins went up
def test_any_other_delta_still_stops(tmp_path, coins, next_price):
    tx = reserved(tmp_path)
    with pytest.raises(ValueError, match='complete changed shelf not proven'):
        tx.reconcile_refresh('scope', 'floor4:shop1', after(tmp_path, 'odd', coins, next_price))
    assert tx.data['pending'] is not None


def test_a_free_refresh_still_needs_a_changed_shelf(tmp_path):
    tx = reserved(tmp_path)
    same = after(tmp_path, 'same', 100, 30, names=('Oracle', 'Scalpel'))
    with pytest.raises(ValueError, match='complete changed shelf not proven'):
        tx.reconcile_refresh('scope', 'floor4:shop1', same)
