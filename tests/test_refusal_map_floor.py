"""A refused owned gift is proven by the map even when the map's floor digit does not read.

The fourth run of 2026-11-24 refused an owned single free gift on floor 4 and confirmed
the refusal. The map came back with a node scrolled under its caption: "Exploring Floor 4"
read as "ExploringFlapr", so the page was the map and its floor was unread (4 of that
task's 41 map reads were). The refusal had landed; the run stopped with
`floor_gift_refusal_successor_not_proven`. The pack line under the caption still read,
and it is the pack this run took for floor 4. A first fix that read the map again was
dropped: the caption was still unreadable three minutes later.
"""
import pytest

from maalimbus.floor_gift_transaction import FloorGiftTransaction, refusal_map_floor
from maalimbus.theme_transaction import ThemeTransaction

SCOPE = 'run-four'


class Catalog:
    """Resolves a spelling the page can print to the pack it means."""
    NAMES = {'TheUnchanging': 'The Unchanging', 'The Unchanging': 'The Unchanging',
             'Addicting Lust': 'Addicting Lust'}

    def identity(self, text):
        return self.NAMES.get(text)


def themes(tmp_path, selected, **more):
    record = ThemeTransaction(tmp_path / 'theme.json')
    record.data = dict(dict(scope=SCOPE, pending=None, selected=selected), **more)
    return record


def taken(floor, name, proven=True):
    return dict(floor=floor, name=name, proof='pick.json', **(dict(map_proof='map.json') if proven else {}))


def test_the_pack_line_names_the_floor_this_run_took_it_for(tmp_path):
    record = themes(tmp_path, [taken(4, 'The Unchanging')])
    assert record.held_floor(SCOPE, 'The Unchanging', Catalog()) == 4
    assert record.held_floor(SCOPE, 'TheUnchanging', Catalog()) == 4      # the header drops a space
    assert record.held_floor(SCOPE, 'Addicting Lust', Catalog()) is None   # the floor before
    assert record.held_floor(SCOPE, 'Something Unlisted', Catalog()) is None
    assert record.held_floor(SCOPE, None, Catalog()) is None


def test_nothing_is_named_for_another_run_an_unproven_drag_or_two_floors(tmp_path):
    assert themes(tmp_path, [taken(4, 'The Unchanging')]).held_floor('another-run', 'The Unchanging', Catalog()) is None
    assert themes(tmp_path, [taken(4, 'The Unchanging', proven=False)]).held_floor(SCOPE, 'The Unchanging', Catalog()) is None
    dragging = themes(tmp_path, [taken(4, 'The Unchanging')], pending=dict(floor=5, name='x', proof='y'))
    assert dragging.held_floor(SCOPE, 'The Unchanging', Catalog()) is None
    twice = themes(tmp_path, [taken(3, 'The Unchanging'), taken(4, 'The Unchanging')])
    assert twice.held_floor(SCOPE, 'The Unchanging', Catalog()) is None
    assert themes(tmp_path, []).held_floor(SCOPE, 'The Unchanging', Catalog()) is None


class Shelf:
    """One offered gift, as far as a signature needs it."""

    def __init__(self, title):
        self.title = title

    def identity(self):
        return dict(title=self.title, owned=True)


def refusing(tmp_path, confirmed=True):
    tx = FloorGiftTransaction(tmp_path / 'gift.json')
    offers = [Shelf('Golden Urn')]
    tx.data = dict(scope=SCOPE, offer=tx.signature(offers), commit_sent=False, selected=[], completed=False,
                   receipts=[], pending=dict(kind='refuse_owned', title='Golden Urn', proof='frame-2169.json'))
    assert tx.observe_refusal('UNKNOWN_DIALOG', 'frame-2170.json', confirm_question=True) is False
    if confirmed:
        tx.refusal_confirm_intent(SCOPE, 'frame-2170.json')
    return tx, offers


def test_the_floor_from_the_pack_completes_the_refusal_and_no_floor_still_does_not(tmp_path):
    tx, _ = refusing(tmp_path)
    with pytest.raises(ValueError, match='floor_gift_refusal_successor_not_proven'):
        tx.observe_refusal('MAP', 'frame-2173.json', map_floor=None)
    floor = themes(tmp_path, [taken(4, 'The Unchanging')]).held_floor(SCOPE, 'The Unchanging', Catalog())
    assert tx.observe_refusal('MAP', 'frame-2173.json', map_floor=floor) is True
    assert tx.data['completed'] and tx.data['pending'] is None


def test_a_later_gift_page_of_the_same_run_closes_a_confirmed_refusal(tmp_path):
    tx, offers = refusing(tmp_path)
    later = [Shelf('Layered Bandages')]
    # The same offer coming back proves nothing; neither does another run's page.
    assert tx.reconcile_outlived_refusal(SCOPE, offers, 'next.json') is None
    assert tx.reconcile_outlived_refusal('another-run', later, 'next.json') is None
    assert tx.data['pending']['kind'] == 'refuse_owned'
    assert tx.reconcile_outlived_refusal(SCOPE, later, 'next.json') == dict(title='Golden Urn', successor='next.json')
    assert tx.data['completed'] and tx.data['pending'] is None
    assert tx.data['refusal']['proven_by'] == 'a_later_gift_page_of_the_same_run'
    # `prepare` refused the next page while a pending half was left; none is.
    assert FloorGiftTransaction(tx.path).data['pending'] is None


def test_a_refusal_whose_confirm_was_never_sent_is_not_closed(tmp_path):
    tx, _ = refusing(tmp_path, confirmed=False)
    assert tx.reconcile_outlived_refusal(SCOPE, [Shelf('Layered Bandages')], 'next.json') is None
    assert tx.data['pending']['kind'] == 'refuse_owned'


def test_the_runner_asks_the_pack_only_for_a_map_whose_digit_did_not_read(tmp_path):
    record = themes(tmp_path, [taken(4, 'The Unchanging')])

    def never():
        raise AssertionError('the catalogue was loaded')
    assert refusal_map_floor('MAP', dict(floor=3, pack='The Unchanging'), record, SCOPE, never) == (3, None)
    assert refusal_map_floor('REWARD_CARD', dict(floor=None), record, SCOPE, never) == (None, None)
    assert refusal_map_floor('MAP', dict(floor=None, pack='The Unchanging'), None, SCOPE, never) == (None, None)
    assert refusal_map_floor('MAP', dict(floor=None, pack='The Unchanging'), record, SCOPE, Catalog) == (4, 'pack')
    assert refusal_map_floor('MAP', dict(floor=None, pack='Addicting Lust'), record, SCOPE, Catalog) == (None, 'pack')
