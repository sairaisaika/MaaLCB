"""Shelf titles as the client really prints them: wrapped onto two lines, or read with a slip.

The rows are the shelf of pi-20261123-212800/frame-0002 (a Super Shop on floor 4 of a
Charge + Tremor team, 2026-11-23). That visit left with 1,706 coins and without
``Material Interference Force Field``, a Charge gift: its title wraps onto a second
line, the reader kept only the first, and an exact comparison then matched nothing.
"""
from types import SimpleNamespace

from maalimbus import gift_fusion
from maalimbus.gift_plan import shop_wanted
from maalimbus.policies import Team
from maalimbus.shop_vision import offers, shelf_tokens, wanted_offers
from maalimbus.vision import Text

SIZE = (1920, 1080)
SHELF = [('OmnamentalHorseshoe', (838, 732, 196, 20), 0.962),
 ('2142', (852, 174, 92, 56), 1.0),
 ('ID Skill Search', (866, 494, 140, 32), 0.989),
 ('107', (894, 688, 72, 36), 1.0),
 ('77', (900, 460, 60, 32), 0.984),
 ('?', (922, 379, 24, 27), 0.783),
 ('3', (958, 645, 18, 24), 0.827),
 ('Super Shop', (998, 172, 130, 34), 0.988),
 ('On Next Floor?', (998, 200, 162, 28), 0.951),
 ('Pendant of Nostalgia', (1066, 728, 196, 26), 0.967),
 ("Replace Faust's Skill", (1068, 496, 198, 28), 0.983),
 (' 101', (1128, 690, 66, 34), 0.88),
 ('2', (1190, 647, 16, 20), 0.521),
 ('22%', (1266, 184, 82, 48), 0.994),
 ("Replace Yi Sang's Skill", (1298, 500, 196, 20), 0.986),
 ('Lowest Star', (1336, 732, 118, 22), 1.0),
 ('129', (1354, 688, 74, 36), 1.0),
 ('45', (1462, 216, 62, 38), 0.999),
 ('Refresh', (1476, 164, 88, 32), 1.0),
 ('MaterlalInterference Force', (1528, 490, 198, 26), 0.974),
 ('Uncapped Defibrilator', (1528, 728, 198, 26), 0.999),
 ('102', (1584, 688, 74, 36), 0.997),
 ('Field', (1608, 514, 36, 16), 0.885),
 ('183', (1612, 460, 44, 32), 1.0),
 ('120', (1678, 218, 66, 34), 0.998),
 ('Heyword', (1686, 156, 96, 32), 0.952),
 ('Refresh', (1694, 180, 84, 22), 1.0)]


def shelf():
    return offers(shelf_tokens([Text(text, box, score) for text, box, score in SHELF]), SIZE)


def test_a_title_wrapped_onto_a_second_line_is_read_whole():
    found = {offer.name: offer for offer in shelf()}
    assert 'MaterlalInterference Force Field' in found
    whole = found['MaterlalInterference Force Field']
    assert whole.price == 183
    # The box covers both lines; the click still comes from the price badge.
    assert whole.name_box == (1528, 490, 198, 40) and whole.click == (1574, 357, 120, 90)
    # One-line titles are what they were.
    prices = {name: offer.price for name, offer in found.items()}
    for name, price in {'Pendant of Nostalgia': 101, 'Lowest Star': 129, 'Uncapped Defibrilator': 102}.items():
        assert prices[name] == price
    assert not [name for name in found if name in ('Field', 'MaterlalInterference Force')]


def test_a_long_title_read_with_one_slip_still_names_the_gift_the_plan_asked_for():
    found = shelf()
    wanted = wanted_offers(found, ['Material Interference Force Field', 'Ornamental Horseshoe', 'Lowest Star'])
    assert [offer.name for offer in wanted] == ['MaterlalInterference Force Field', 'OmnamentalHorseshoe', 'Lowest Star']
    # Bought under the plan's spelling: not bought twice under the shelf's.
    assert wanted_offers(found, ['Material Interference Force Field'], bought=['Material Interference Force Field']) == []
    # A short title is exact or nothing, and two plan names that both fit name nothing.
    short = [SimpleNamespace(name='Awa', index=1, purchased=False)]
    assert wanted_offers(short, ['Awe']) == []
    twins = [SimpleNamespace(name='Pocket Watch : Type X', index=1, purchased=False)]
    assert wanted_offers(twins, ['Pocket Watch : Type L', 'Pocket Watch : Type E']) == []
    spaced = [SimpleNamespace(name='PendantofNostalgia', index=1, purchased=False)]
    assert [offer.name for offer in wanted_offers(spaced, ['Pendant of Nostalgia'])] == ['PendantofNostalgia']


def test_a_team_asks_the_shop_for_the_gifts_its_systems_recipes_are_made_of():
    from pathlib import Path
    recipes = gift_fusion.load(Path(__file__).resolve().parents[1] / 'assets/resource/base' / gift_fusion.FILE)
    catalog = SimpleNamespace(entries={
        'Employee Card': dict(keywords=['Charge']),
        'Wrist Guards': dict(keywords=['Charge']),
        'Awe': dict(keywords=['Bleed']),
    })
    team = Team(2, frozenset({'Charge', 'Tremor'}))
    names = shop_wanted(team, catalog, None, recipes)
    # The catalogue's own names first, as before.
    assert names[:2] == ['Employee Card', 'Wrist Guards']
    # Then recipe gifts the pinned catalogue does not know, for both systems.
    assert {'Material Interference Force Field', 'T-1B Octagonal Bolt', 'UPS System', 'Wobbling Keg',
            'Gemstone Oscillator'} <= set(names)
    # Not another system's, not a recipe's own result (no shelf sells one), no duplicates.
    assert 'Melted Paraffin' not in names and 'Insulator' not in names and 'Epicenter' not in names
    assert len(names) == len(set(names))
    # A blocked gift stays blocked, and a team with no system chases no recipe.
    catalog.entries['UPS System'] = dict(keywords=['Charge'])
    blocked = shop_wanted(Team(2, frozenset({'Charge'}), block=frozenset({'UPS System'})), catalog, None, recipes)
    assert 'UPS System' not in blocked and 'Miniature Telepole' in blocked
    assert shop_wanted(Team(2, frozenset()), catalog, None, recipes) == []
    assert shop_wanted(team, catalog) == ['Employee Card', 'UPS System', 'Wrist Guards']
