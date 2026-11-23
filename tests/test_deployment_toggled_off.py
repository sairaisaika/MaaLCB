"""A card click that met a board which had loaded the saved team is retired from the board.

Live ``pi-20261123-121915`` (2026-11-23): the pre-battle page was read as 0/12 with no
badge on any card, the first card of the saved order (card 3) was clicked, and the next
frames read 11/12 with card 3 out and the other eleven in, numbered in the saved order
shifted down by one. The page had not shown the saved team yet; the click removed a
card instead of adding one, and the run stopped with "Unverified deployment input
remains pending". The readings below are those of ``frame-0003``/``frame-0008``.
"""
import pytest

from maalimbus.deployment_transaction import DeploymentTransaction

ORDER = [3, 4, 9, 1, 7, 2, 12, 5, 8, 10, 11, 6]
STATES = ['selected', 'selected', None, 'selected', 'selected', 'backup',
          'selected', 'backup', 'selected', 'backup', 'backup', 'selected']
NUMBERS = [3, 5, None, 1, 7, 11, 4, 8, 2, 9, 10, 6]


def pending(tmp_path):
    tx = DeploymentTransaction(tmp_path / 'deployment.json')
    tx.prepare('run', ORDER, (0, 12), [None] * 12)
    tx.intent('card', (0, 12), 3)
    return tx


def test_the_live_board_retires_the_click_and_asks_for_a_reset(tmp_path):
    tx = pending(tmp_path)
    with pytest.raises(ValueError, match='remains pending'):
        tx.prepare('run', ORDER, (11, 12), NUMBERS)
    tx.reconcile_toggled_off('run', (11, 12), STATES, 'frame-0003.json')
    reread = DeploymentTransaction(tx.path)
    assert reread.data['pending'] is None and reread.data['sequence'] == []
    assert reread.data['abandoned'][-1]['intent']['card'] == 3
    assert reread.data['abandoned'][-1]['proof'] == 'frame-0003.json'
    # The board now contradicts the saved order, so the existing clear-and-repick owns it.
    plan = reread.prepare('run', ORDER, (11, 12), NUMBERS)
    assert plan['reset_required'] is True and plan['order_verified'] is False


@pytest.mark.parametrize('count, states', [
    ((1, 12), [None, None, 'selected'] + [None] * 9),            # the click simply worked
    ((11, 12), STATES[:2] + ['selected'] + STATES[3:]),          # the clicked card is in the team
    ((10, 12), STATES[:3] + [None] + STATES[4:]),                # another card is out as well
    ((11, 11), STATES[:11]),                                     # the capacity changed
    ((0, 12), [None] * 12),                                      # nothing happened yet
])
def test_any_other_board_keeps_the_intent_pending(tmp_path, count, states):
    tx = pending(tmp_path)
    with pytest.raises(ValueError, match='not proven'):
        tx.reconcile_toggled_off('run', count, states)
    assert DeploymentTransaction(tx.path).data['pending']['card'] == 3


def test_another_run_or_a_later_card_is_not_retired_this_way(tmp_path):
    tx = pending(tmp_path)
    with pytest.raises(ValueError, match='not proven'):
        tx.reconcile_toggled_off('other-run', (11, 12), STATES)
    tx.observe((1, 12))                                          # card 3 really joined
    tx.intent('card', (1, 12), 4)
    with pytest.raises(ValueError, match='not proven'):
        tx.reconcile_toggled_off('run', (11, 12), STATES)
