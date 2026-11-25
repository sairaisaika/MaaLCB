"""Enemy power trials are priced in the order the game's formulas give them.

Clash Power counts in the clash only. Base Power and Final Power count in the clash and
in the damage of every coin, so a point of either can never be the cheaper trial. The
table had Base Power at 180 against Clash Power's 240, and "Final Power +N" was outside
the grammar, so a card carrying it was never chosen and the pick fell on what was left.
On 2026-11-25 (`pi-20261124-215839`, 04:23) a page offered Grey Coat, Perversion
("Clash Power +1, Max HP +7.5%"), Phlebotomy Pack ("Base Power +1, Max HP +2.5%") and
the owned Golden Urn ("Final Power +1, Max HP +5%"); the run took Phlebotomy Pack.
"""
from types import SimpleNamespace

import pytest

from maalimbus.floor_gifts import Offer, Trial, UnpricedTrial, parse_trial, rank
from maalimbus.vision import Text

TEAM = SimpleNamespace(allow=frozenset(), block=frozenset(), keywords=frozenset())


def trial(text, level=1):
    return parse_trial(level, [Text(text, (100, 100, 300, 24), .99)])


def offer(title, text, owned=False):
    return Offer(title, title, frozenset(), (0, 0, 10, 10), trial(text), owned)


def test_final_power_is_read_and_costs_what_base_power_costs():
    final = trial('Final Power +1, Max HP +5%')
    assert final.components == (('final_power', 1), ('hp', 5))
    assert final.penalty == trial('Base Power +1, Max HP +5%').penalty
    assert trial('Final Power +2').penalty - trial('Final Power +1').penalty == 250


@pytest.mark.parametrize('text', ['Defense Skill Final Power +1', 'Plus Coin Power +1, Minus Coin Power -1',
                                  'Final Power', 'Final Power +1 for Defense Skills'])
def test_narrower_or_incomplete_power_effects_stay_unpriced(text):
    with pytest.raises(UnpricedTrial):
        trial(text)


def test_a_point_of_clash_power_is_never_dearer_than_a_point_that_also_deals_damage():
    clash, base, final = (trial(f'{name} Power +1').penalty for name in ('Clash', 'Base', 'Final'))
    assert clash < base == final
    # Three Offense Levels are one point of clash plus their own damage share.
    assert trial('Offense Level +3').penalty > clash


def test_the_live_page_now_takes_the_clash_only_trial():
    offers = [offer('Golden Urn', 'Final Power +1, Max HP +5%', owned=True),
              offer('Grey Coat', 'Defense Level +4, Max HP +5%'),
              offer('Perversion', 'Clash Power +1, Max HP +7.5%'),
              offer('Phlebotomy Pack', 'Base Power +1, Max HP +2.5%')]
    assert [row['title'] for row in rank(offers, TEAM, set())] == [
        'Grey Coat', 'Perversion', 'Phlebotomy Pack', 'Golden Urn']
    assert Trial(1, 'final_power', 1).penalty == 280
