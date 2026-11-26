"""A coin counter read just under the floor is believed when the record expects its number.

Live `pi-20261126-030355`, the first shop of the fifth run: Bio-venom Vial was bought for
259 out of 714 and its notice acknowledged. The shelf came back printing "455" -- the
right number -- at a score of .898 where .9 is required, on every read of that still
page, and the run stopped with "Unique high-confidence shop currency not proven" on a
purchase whose card already carried its Purchased badge.

A faint read is not evidence of a number. It is a second witness to one the reservation
and its price, or the last proven count, have already given.
"""
import pytest

from maalimbus.shop_transaction import COUNTER_FAINT, ShopTransaction, _coins, faint_counter
from maalimbus.vision import Text

SIZE = (1920, 1080)
COUNTER = (852, 174, 78, 56)       # where frame-0257 printed "455"


def page(text='455', score=.897708, box=COUNTER, extra=()):
    return [Text(text, box, score), Text('Shop', (334, 154, 98, 54), 1.0),
            Text('45', (1462, 216, 62, 38), 1.0), Text('259', (1100, 700, 60, 30), 1.0)] + list(extra)


def test_the_live_counter_is_believed_for_the_number_the_purchase_leaves():
    assert faint_counter(page(), SIZE, (714, 455)) == 455
    assert _coins(page(), SIZE, (714, 455)) == 455
    with pytest.raises(ValueError, match='shop currency not proven'):
        _coins(page(), SIZE)                      # nothing expected: the floor stands


@pytest.mark.parametrize('texts, expected', [
    (page(), (714,)),                              # a number nobody expected
    (page(), ()),
    (page(), (None, '455')),                       # not numbers at all
    (page(score=COUNTER_FAINT - .01), (455,)),     # too faint to be a witness
    (page(text='4S5'), (455,)),                    # not a number
    (page(box=(1100, 700, 60, 30)), (455,)),       # not where the counter is
    (page(extra=[Text('455', (860, 180, 70, 50), .88)]), (455,)),   # two faint tokens
])
def test_a_faint_read_vouches_for_nothing_else(texts, expected):
    assert faint_counter(texts, SIZE, expected) is None
    with pytest.raises(ValueError, match='shop currency not proven'):
        _coins(texts, SIZE, expected)


def test_a_counter_read_at_full_confidence_needs_no_expectation_and_is_not_overruled():
    assert _coins(page(score=.95), SIZE) == 455
    assert _coins(page(score=.95), SIZE, (714,)) == 455
    # A confident counter next to a faint one is the old rule's business, not this one's.
    both = page(score=.95, extra=[Text('714', (860, 180, 70, 50), .88)])
    assert _coins(both, SIZE, (714,)) == 455


def record(tmp_path, **data):
    tx = ShopTransaction(tmp_path / 'shop.json')
    tx.data = dict(dict(version=1, scope='run', current_visit='1', visits={'1': {}}, bought=[], pending=None), **data)
    return tx


def test_the_record_says_which_numbers_the_counter_may_print(tmp_path):
    assert record(tmp_path).held_coins() == ()
    assert record(tmp_path, coins_proven=455).held_coins() == (455,)
    buying = record(tmp_path, coins_proven=714, pending=dict(kind='purchase', coins=714, price=259))
    assert buying.held_coins() == (714, 455)      # untouched, or paid
    opening = record(tmp_path, coins_proven=714, pending=dict(kind='skill_service', coins=714))
    assert opening.held_coins() == (714,)
    assert ShopTransaction(tmp_path / 'absent.json').held_coins() == ()


def test_the_shop_decision_goes_on_with_the_number_the_record_expects():
    from maalimbus.runner import shop_state
    frame = dict(scene='SHOP', size=list(SIZE), ocr=[
        dict(text='455', box=list(COUNTER), score=.897708),
        dict(text='Perversion', box=[1310, 500, 110, 26], score=.99),
        dict(text='157', box=[1340, 462, 60, 30], score=.99)])
    assert shop_state(frame, ['Perversion'])['currency'] is None
    assert shop_state(frame, ['Perversion'])['reason'] == 'shop_currency_not_read'
    assert shop_state(frame, ['Perversion'], known_coins=(455,))['currency'] == 455
    assert shop_state(frame, ['Perversion'], known_coins=(714,))['currency'] is None


def shelf_frame(tmp_path, score):
    """A shelf page written to disk the way a step records one: the counter at `score`."""
    import hashlib
    import json
    import numpy as np
    import cv2
    image = tmp_path / 'frame-0002.png'
    cv2.imwrite(str(image), np.zeros((1080, 1920, 3), np.uint8))
    frame = tmp_path / 'frame-0002.json'
    frame.write_text(json.dumps(dict(
        scene='SHOP', size=list(SIZE), image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        ocr=[dict(text='455', box=list(COUNTER), score=score),
             dict(text='Perversion', box=[1310, 500, 110, 26], score=.99),
             dict(text='157', box=[1340, 462, 60, 30], score=.99)])), encoding='utf-8')
    return frame


def test_an_open_visit_is_entered_again_on_its_own_count_and_a_new_one_is_not(tmp_path):
    frame = shelf_frame(tmp_path, .897708)
    visit = dict(entry=dict(png_sha256='0' * 64), refreshes=0, closed=False, overlay_acknowledgements=[])
    # The step after a reconciled purchase: same visit, the record holds 455.
    again = record(tmp_path, coins_proven=455, visits={'1': dict(visit)})
    assert again.begin_visit('run', '1', str(frame)) is False
    # The record holding another number does not vouch for this one.
    other = record(tmp_path, coins_proven=714, visits={'1': dict(visit)})
    with pytest.raises(ValueError, match='shop currency not proven'):
        other.begin_visit('run', '1', str(frame))
    # A new visit has no count of its own yet, whatever the last one ended on.
    closed = record(tmp_path, coins_proven=455, visits={'1': dict(visit, closed=True)})
    with pytest.raises(ValueError, match='shop currency not proven'):
        closed.begin_visit('run', '2', str(frame))
