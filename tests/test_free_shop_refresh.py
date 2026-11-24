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


def test_a_paid_refresh_whose_price_rose_need_not_keep_the_number_of_gifts(tmp_path):
    # pi-20261123-212043, floor 4: 2172 -> 2142 coins for a 30-coin refresh, the button's
    # price 30 -> 45, and a shelf with one gift fewer than before. The count check refused it.
    tx = reserved(tmp_path)
    fewer = after(tmp_path, 'fewer', 85, 30, names=('Voodoo Doll',))
    assert tx.reconcile_refresh('scope', 'floor4:shop1', fewer) is True
    assert tx.data['pending'] is None


def test_without_a_risen_price_the_number_of_gifts_still_has_to_match(tmp_path):
    tx = reserved(tmp_path)
    fewer = after(tmp_path, 'fewer', 85, None, names=('Voodoo Doll',))
    with pytest.raises(ValueError, match='complete changed shelf not proven'):
        tx.reconcile_refresh('scope', 'floor4:shop1', fewer)


@pytest.mark.parametrize('title', ["Replace Don Oulxote's Ski", "Replace Hong Lu's Skil", "Replace Faust's Skill",
                                   "Replaoe Yi Sang's Skill", 'ID Skill Search', 'ID Skil Search'])
def test_a_row_that_starts_with_replace_is_a_service_however_it_ends(title):
    from maalimbus.shop_skill_vision import looks_like_skill_service
    assert looks_like_skill_service(title) is True


@pytest.mark.parametrize('title', ['Pendant of Nostalgia', 'Replica Blade', 'Replace', 'Replace Me', 'Clockwork Spring',
                                   'Milepost of Survival'])
def test_a_gift_is_not_taken_for_a_service(title):
    from maalimbus.shop_skill_vision import looks_like_skill_service
    assert looks_like_skill_service(title) is False

