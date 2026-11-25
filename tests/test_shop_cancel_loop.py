"""One card opened and cancelled 89 times, and a wait judged by another battle's clock.

Live `pi-20261125-150822`, the fourth run's floor-5 shop (2026-11-25, 20:35-20:53 UTC).
The plan asked for Nightvision Goggles at 184. Its purchase dialog printed the name as
"lightvision" over "Coggles" beside the badge "2018 > 1834": two slips where one was
forgiven, so the dialog was answered with its Cancel, the reservation was retired and the
same card was opened again -- 89 times, until one frame read the first letter. The OCR
rows below are retyped from frame-0552; the frame itself is local evidence.

The same task then ended on `the_submitted_turn_never_showed_a_page`: the first
unreadable frame after the floor-5 battle's loader was judged against a clock that had
been started by a battle 47 minutes earlier.
"""
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import runner  # noqa: E402
from maalimbus.shop_transaction import RETIRE_LIMIT, ShopTransaction  # noqa: E402
from maalimbus.shop_vision import native_purchase_dialog, purchase_balances, purchase_dialog_answer  # noqa: E402
from maalimbus.vision import Text  # noqa: E402

SIZE = (1920, 1080)
ROWS = [('lightvision', [558, 561, 154, 38], .96), ('Coggles', [580, 591, 114, 34], .94),
        ('Purchase E.G.O Gifts', [672, 236, 292, 34], 1.0), ('X Cancel', [710, 702, 156, 42], .91),
        ('Purchase', [1092, 706, 128, 34], 1.0), ('2018', [852, 174, 90, 54], 1.0),
        ('20181834', [1230, 234, 130, 34], 1.0), ('2018', [1230, 236, 53, 34], 1.0),
        ('1834', [1305, 235, 57, 35], 1.0), ('Child within a Flask', [1532, 726, 188, 30], .98),
        ('Broken Spearhead', [1534, 496, 186, 28], 1.0), ('200', [1582, 458, 78, 36], 1.0)]


def dialog(first='lightvision', second='Coggles'):
    rows = [(first, ROWS[0][1], ROWS[0][2]), (second, ROWS[1][1], ROWS[1][2])] + ROWS[2:]
    return [Text(text, tuple(box), score) for text, box, score in rows]


def test_the_live_dialog_is_the_reserved_purchase():
    records = dialog()
    assert native_purchase_dialog(records, SIZE) is not None
    assert purchase_balances(records, SIZE) == (2018, 1834)
    assert purchase_dialog_answer(records, 'Nightvision Goggles', 184, SIZE, coins=2018) == \
        ('purchase', [1092, 706, 128, 34])


def test_the_second_slip_is_forgiven_only_with_the_price_and_never_a_third():
    # Another price is another purchase, however the name reads.
    assert purchase_dialog_answer(dialog(), 'Nightvision Goggles', 185, SIZE, coins=2018)[0] == 'cancel'
    assert purchase_dialog_answer(dialog('Nightvision', 'Goggles'), 'Nightvision Goggles', 185, SIZE,
                                  coins=2018)[0] == 'cancel'
    # Three slips are a different name even at the right price; so is another gift.
    assert purchase_dialog_answer(dialog('lightvision', 'Coggies'), 'Nightvision Goggles', 184, SIZE,
                                  coins=2018)[0] == 'cancel'
    assert purchase_dialog_answer(dialog('Broken', 'Spearhead'), 'Nightvision Goggles', 184, SIZE,
                                  coins=2018)[0] == 'cancel'
    # Without the two balances there is no price proof: one slip, as before.
    unpriced = [row for row in dialog() if row.text not in ('20181834', '1834')]
    assert purchase_dialog_answer(unpriced, 'Nightvision Goggles', 184, SIZE, coins=2018)[0] == 'cancel'


def visit(tmp_path, retired):
    tx = ShopTransaction(tmp_path / 'shop.json')
    tx.data = dict(scope='run', current_visit='5', pending=None, bought=[],
                   visits={'5': dict(retired=retired), '4': dict(retired=[dict(name='Old Card', price=1, why=None)] * 5)})
    return tx


def test_a_card_cancelled_twice_in_a_visit_is_left_on_the_shelf(tmp_path):
    once = dict(name='Nightvision Goggles', price=184, why='gift_plan')
    assert visit(tmp_path, []).held_back('5') == []
    assert visit(tmp_path, [once]).held_back('5') == []                    # the next frame may read
    assert visit(tmp_path, [once] * RETIRE_LIMIT).held_back('5') == ['Nightvision Goggles']
    mixed = [once, dict(name='Red Order', price=188, why=None), once, dict(name=None, price=1, why=None)]
    assert visit(tmp_path, mixed).held_back('5') == ['Nightvision Goggles']
    # Another visit's cancels are not this visit's.
    assert visit(tmp_path, [once]).held_back('4') == ['Old Card']
    assert visit(tmp_path, [once]).held_back('9') == []


def test_a_held_back_card_is_not_bought_and_the_rest_of_the_shelf_still_is():
    from maalimbus.shop_vision import Offer, wanted_offers
    shelf = [Offer(1, 'Nightvision Goggles', (), 184, None, None), Offer(2, 'Red Order', (), 188, None, None)]
    wanted = ['Nightvision Goggles', 'Red Order']
    assert [o.name for o in wanted_offers(shelf, wanted, [])] == wanted
    assert [o.name for o in wanted_offers(shelf, wanted, ['Nightvision Goggles'])] == ['Red Order']


def loop(**state):
    made = runner.MirrorRunner.__new__(runner.MirrorRunner)
    made.settings = runner.settings(dict(submit_seconds=180))
    made.state = dict(dict(page='UNKNOWN', step=1), **state)
    made.notes = []
    made.note = lambda name, **fields: made.notes.append((name, fields))
    return made


@pytest.mark.parametrize('page', ['PRE_BATTLE_TEAM', 'BATTLE_HUD', 'MAP', 'SHOP', 'BATTLE_RESULT'])
def test_a_page_that_reads_ends_the_submit_clock(page):
    made = loop(submit_since=1.0)
    made._a_page_that_reads_ends_the_submit_clock(page)
    assert 'submit_since' not in made.state


@pytest.mark.parametrize('page', ['UNKNOWN', 'LOADING'])
def test_the_unreadable_stretch_and_its_loader_keep_the_clock(page):
    made = loop(submit_since=1.0)
    made._a_page_that_reads_ends_the_submit_clock(page)
    assert made.state['submit_since'] == 1.0


def test_the_next_battle_is_timed_from_its_own_first_unreadable_page(monkeypatch):
    clock = types.SimpleNamespace(now=1000.0)
    monkeypatch.setattr(runner.time, 'monotonic', lambda: clock.now)
    made = loop()
    blockers = ['Deployment_transaction.submit_pending']
    assert made._submit_transition_wait(blockers) is False        # the 20:09 battle starts its clock
    clock.now += 2834.7                                           # ... 47 minutes of pages that read
    made._a_page_that_reads_ends_the_submit_clock('PRE_BATTLE_TEAM')
    assert made._submit_transition_wait(blockers) is False        # the 20:56 battle starts its own
    assert not made.notes
    clock.now += 181
    assert made._submit_transition_wait(blockers) is True         # and its own budget still ends it
    assert made.notes[-1][0] == 'pending_submit_wait_exhausted' and made.notes[-1][1]['waited'] == 181.0
