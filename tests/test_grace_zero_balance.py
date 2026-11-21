"""A purchase that spends all starlight leaves a lone zero, which OCR reads only weakly.

The records below are the ones the live run produced on 2026-11-21 (run directory
``packaged-mirror-20261121-131525``): the counter read ``*50`` and ``*30`` beside two
clean detector reads while money was left, and only ``0`` at .60 or ``*0`` at .47 once
cards 2, 4 and 5 had spent the whole 60. No image is read here; the texts are retyped.
"""
import pytest

from maalimbus.grace_transaction import GraceTransaction
from maalimbus.grace_vision import (ZERO_FLOOR, available_starlight, zero_only_corroborated,
                                    zero_successor)
from maalimbus.vision import Text

SIZE = (1920, 1080)
LABEL = Text('Available', (1372, 55, 76, 28), .99)
COINS = Text('0', (1692, 55, 16, 26), .57)   # the other currency, outside the counter's place


def frame(*counter):
    return [Text('Grace of the Sisyphean Star', (202, 45, 406, 34), 1.0),
            Text('Owned', (1082, 55, 66, 28), 1.0), Text('3220', (1192, 49, 104, 42), 1.0),
            LABEL, *counter, COINS]


THIRTY = frame(Text('*30', (1478, 53, 56, 32), .76), Text('30', (1505, 40, 92, 50), 1.0),
               Text('30', (1510, 45, 80, 40), 1.0))
ZERO_GLUED = frame(Text('*0', (1478, 53, 56, 32), .47))
ZERO_CLEAN = frame(Text('0', (1476, 53, 30, 32), .60))


def test_a_lone_zero_is_not_read_unless_the_books_expect_zero():
    for records in (ZERO_GLUED, ZERO_CLEAN):
        assert available_starlight(records, SIZE) is None
        assert available_starlight(records, SIZE, expect_zero=True) == 0
        assert zero_only_corroborated(records, SIZE) is True


def test_a_balance_that_reads_properly_is_never_turned_into_zero():
    assert available_starlight(THIRTY, SIZE) == 30
    assert available_starlight(THIRTY, SIZE, expect_zero=True) == 30
    assert zero_only_corroborated(THIRTY, SIZE) is False


@pytest.mark.parametrize('counter', [
    (Text('*3', (1478, 53, 56, 32), .47),),                                       # a weak other digit
    (Text('*0', (1478, 53, 56, 32), .47), Text('30', (1505, 45, 60, 36), .55)),   # a weak contrary read
    (Text('*10', (1478, 53, 56, 32), .47),),                                      # zero only as a last digit
    (Text('*00', (1478, 53, 56, 32), .47),),                                      # not a lone zero
    (Text('*0', (1478, 53, 56, 32), ZERO_FLOOR - .01),),                          # below the floor
    (),                                                                          # nothing in the counter's place
])
def test_anything_but_an_unopposed_lone_zero_stays_unread(counter):
    records = frame(*counter)
    assert available_starlight(records, SIZE, expect_zero=True) is None
    assert zero_only_corroborated(records, SIZE) is False


def test_the_zero_of_the_other_currency_is_not_the_starlight_counter():
    assert available_starlight(frame(), SIZE, expect_zero=True) is None


def test_without_the_label_nothing_is_read():
    records = [record for record in ZERO_GLUED if record is not LABEL]
    assert available_starlight(records, SIZE, expect_zero=True) is None


def test_the_books_expect_zero_only_when_a_purchase_spends_everything(tmp_path):
    transaction = GraceTransaction(tmp_path / 'transaction.json')
    assert transaction.is_zero_expected() is False
    transaction.begin('run-a', [2, 4, 5], 100, 'entry.png')
    assert transaction.is_zero_expected() is False          # nothing bought: an unread balance stays unread
    transaction.intent(2, 10, 60, 'before-2.png')
    assert transaction.is_zero_expected() is False          # 60 - 10 leaves 50
    transaction.observe(50, 'after-2.png')
    transaction.intent(4, 20, 50, 'before-4.png')
    transaction.observe(30, 'after-4.png')
    assert transaction.is_zero_expected() is False
    transaction.intent(5, 30, 30, 'before-5.png')
    assert transaction.is_zero_expected() is True           # 30 - 30: the counter must now show zero
    with pytest.raises(ValueError, match='not proven'):
        transaction.observe(None, 'unread.png')
    transaction.observe(available_starlight(ZERO_GLUED, SIZE, expect_zero=transaction.is_zero_expected()),
                        'after-5.png')
    booked = GraceTransaction(tmp_path / 'transaction.json')
    assert booked.data['selected'] == [2, 4, 5] and booked.data['spent'] == 60 and booked.data['available'] == 0
    assert booked.is_zero_expected() is True                # later visits to the page still read zero
    assert booked.validate('run-a', [2, 4, 5], 100, 0)['selected'] == [2, 4, 5]


def test_a_weak_zero_cannot_book_a_purchase_that_should_leave_money(tmp_path):
    transaction = GraceTransaction(tmp_path / 'transaction.json')
    transaction.begin('run-a', [2, 4], 100, 'entry.png')
    transaction.intent(2, 10, 60, 'before.png')
    read = available_starlight(ZERO_GLUED, SIZE, expect_zero=transaction.is_zero_expected())
    assert read is None
    with pytest.raises(ValueError, match='not proven'):
        transaction.observe(read, 'after.png')
    assert GraceTransaction(tmp_path / 'transaction.json').data['pending']['card'] == 2


def observation(records, scene='STAR_GRACES'):
    return dict(scene=scene, size=list(SIZE),
                ocr=[dict(text=r.text, box=list(r.box), score=r.score) for r in records])


def test_a_zero_successor_needs_two_observations_that_agree():
    taken = []

    def observe():
        taken.append(1)
        return observation(ZERO_CLEAN)
    proof = zero_successor(observation(ZERO_GLUED), observe)
    assert proof['zero'] and proof['first'] and proof['second'] and proof['on_page'] and len(taken) == 1
    assert proof['settled']['ocr'][4]['text'] == '0'     # the second observation is the one recorded


@pytest.mark.parametrize('first, second, on_page', [
    (ZERO_GLUED, THIRTY, True),                 # the second look reads a real balance
    (THIRTY, ZERO_GLUED, True),                 # the first look read a real balance
    (ZERO_GLUED, frame(), True),                # the second look reads nothing
])
def test_one_weak_zero_alone_proves_nothing(first, second, on_page):
    proof = zero_successor(observation(first), lambda: observation(second))
    assert not proof['zero'] and proof['on_page'] is on_page


def test_a_second_observation_on_another_page_is_not_a_zero():
    proof = zero_successor(observation(ZERO_GLUED), lambda: observation(ZERO_GLUED, scene='STAR_CONFIRM'))
    assert not proof['zero'] and not proof['on_page'] and not proof['second']
