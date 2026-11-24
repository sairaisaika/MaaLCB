"""A gift whose own effect mentions the shop is still a free gift.

Live `pi-20261123-200100/frame-0783` (floor 3): the free three-gift page offered Ruptured
Blood Sac, Sunshower and Prestige Card. Prestige Card's effect reads "Shop E.G.O Gift
Purchase Cost -30%", the page check took the words "Shop" and "Purchase" for a price,
and the run stopped with `three_free_gift_trial_or_cost_present`. The rows are retyped
from that frame.
"""
from pathlib import Path

import pytest

from maalimbus.floor_gifts import observe_three_free
from maalimbus.gift_vision import GiftCatalog
from maalimbus.reward_vision import gift_cards
from maalimbus.vision import Text

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
PRICED = 'three_free_gift_trial_or_cost_present'


def page(third_title='Prestige Card', extra=()):
    rows = [('Ruptured Blood Sac', (444, 270, 232, 27), .97), ('On ally Clash Win: activate the', (446, 450, 266, 26), .98),
            ("enemy'sBleedonce and", (446, 478, 238, 28), .99), ('reduceBleedCount by 1 (3', (446, 508, 258, 26), .97),
            ('times per turn)', (448, 536, 128, 21), .99), ('Acquire E.G.O Gift', (580, 230, 148, 28), 1.0),
            ('Skill with 2+ Atk Welght:', (838, 504, 218, 30), .96), ('When activating Sloth', (842, 450, 196, 26), 1.0),
            ('Absolute Resonance or using a', (842, 476, 274, 30), 1.0),
            ('All allies gain +2 Skill Power at', (842, 563, 264, 26), .99), ('Combat Start.', (844, 591, 124, 22), 1.0),
            ('Sunshower', (886, 268, 138, 33), 1.0), ('II', (934, 327, 26, 30), .74),
            ('Acquire E.G.O Gift', (974, 226, 152, 30), .97),
            ('Shop E.G.O Gift Purchase Cost', (1240, 450, 272, 26), 1.0), ('-30%', (1242, 476, 54, 30), 1.0),
            (third_title, (1268, 266, 172, 33), .99), ('III', (1330, 325, 28, 34), .76),
            ('Refuse Gift', (1348, 851, 152, 34), 1.0), ('Acquire E.G.O Gift', (1374, 228, 152, 28), 1.0),
            ('Select', (1652, 849, 108, 40), 1.0), *extra]
    return [Text(text, box, score) for text, box, score in rows]


def reason(records):
    """Why the page was refused, or None when the page is read as the free layout."""
    catalog = GiftCatalog(ROOT / 'assets/resource/base')
    try:
        observe_three_free(records, SIZE, catalog, gift_cards(records, SIZE), None, None)
    except ValueError as error:
        return str(error)
    return None


def test_the_live_page_is_not_refused_as_priced():
    assert reason(page()) != PRICED


@pytest.mark.parametrize('line', [
    ('Cost 10 Modules', (1240, 520, 200, 26), 1.0),       # a number on the cost word, inside a card
    ('Max HP +10%', (446, 570, 150, 26), 1.0),            # a trial line inside a card
    ('Mounting Trials', (800, 120, 320, 40), 1.0),        # a trial heading outside every card
    ('Shop', (1700, 300, 80, 30), 1.0),                   # a shop word outside every description
])
def test_a_price_or_trial_line_still_refuses_the_free_layout(line):
    assert reason(page(extra=(line,))) == PRICED


def test_the_exemption_needs_a_title_the_catalogue_knows():
    assert reason(page(third_title='Unlisted Thing')) == PRICED
