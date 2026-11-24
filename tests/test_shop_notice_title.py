"""The gift notice after a purchase names a card of the shelf the purchase was made from.

Live `pi-20261123-194800`: "Milepost of Survival" was bought for 182 on floor 2, and the
notice printed its name in the display typeface as "milepost of Suruiual" (frame 78).
The comparison asked for the same glyphs, found two that differed, and stopped the run
on a purchase that had gone through. The shelf below is the one that transaction held.
"""
import pytest

from maalimbus.shop_transaction import _notice_names

SHELF = ["Replace Meursault's Skill", 'Decamillennial Stewpot', 'Pendant of Nostalgla', 'Milepost of Survival',
         'UPS System', 'Omamental Horseshoe']


def pending(name='Milepost of Survival', shelf=SHELF):
    return dict(name=name, shelf=[dict(name=title, price=100) for title in shelf])


def test_the_display_typeface_reading_names_the_card_that_was_bought():
    assert _notice_names('milepost of Suruiual', pending()) is True
    assert _notice_names('Milepost of Survival', pending()) is True
    assert _notice_names('MILEPOST OF SURVIVAL', pending()) is True


@pytest.mark.parametrize('read', [title for title in SHELF if title != 'Milepost of Survival'])
def test_another_card_of_the_same_shelf_is_a_different_gift(read):
    assert _notice_names(read, pending()) is False


@pytest.mark.parametrize('read', ['milepost', 'Suruiual', 'Pendant of Nostalgia', 'E.G.O Gift GET!', 'x'])
def test_a_reading_that_is_not_clearly_the_bought_card_is_refused(read):
    assert _notice_names(read, pending()) is False


def test_two_cards_that_read_alike_cannot_be_told_apart_by_a_slipped_reading():
    twins = pending('Milepost of Survival', SHELF + ['Milepost of Surmisal'])
    assert _notice_names('milepost of Suruiual', twins) is False       # too close to both: not proven
    assert _notice_names('Milepost of Survival', twins) is True        # an exact reading still is


def test_a_transaction_without_a_saved_shelf_still_needs_a_close_reading():
    assert _notice_names('milepost of Suruiual', dict(name='Milepost of Survival')) is True
    assert _notice_names('Decamillennial Stewpot', dict(name='Milepost of Survival')) is False


def test_the_first_line_of_a_wrapped_name_names_the_card_when_only_it_opens_that_way():
    # pi-20261124-010147/frame-0892: the notice wrapped the name, "milepost of" at .97 over
    # "Suruiual" at .85; the reader kept the first line, and the purchase stopped the run.
    live = ['ID Skill Search', 'Phlebotomy Pack', 'Milepost of Survival', 'Broken Spearhead', 'Shard of Apocalypse',
            'Fragment of Allurement']
    assert _notice_names('milepost of', pending(shelf=live)) is True
    # One word is not an opening, and neither is the whole of another card.
    assert _notice_names('milepost', pending(shelf=live)) is False
    assert _notice_names('Shard of', pending(shelf=live)) is False
    # Two cards that open alike: the opening names neither.
    twins = ['Fragment of Allurement', 'Fragment of Desire', 'Awe']
    assert _notice_names('Fragment of', pending('Fragment of Allurement', twins)) is False
    # An opening too short to carry a name.
    assert _notice_names('Red of', pending('Red of Something Long', ['Red of Something Long', 'Awe'])) is False
