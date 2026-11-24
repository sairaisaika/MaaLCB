"""The one-gift page: a gift's own effect text is not a trial.

Live `pi-20261124-002332/frame-0683` (floor 3): the page offered First-aid Kit, free, with
Refuse Gift and Select. Its effect reads "HP heals 25% of Max HP.", the page check took
"Max HP" for a mounting trial and the run stopped with
`single_free_gift_trial_or_cost_present`. The rows are retyped from that frame. The same
defect on the three-gift page was fixed the day before; see
`test_gift_effect_text_is_not_a_price.py`.
"""
from types import SimpleNamespace

import pytest

from maalimbus.floor_gifts import single_free_page_is_priced
from maalimbus.vision import Text

SIZE = (1920, 1080)
ROWS = [('Acquire E.G.O Gift', (978, 230, 146, 22), .96), ('First-aid Kit', (884, 270, 146, 27), 1.0),
        ('III', (934, 327, 24, 30), .76), ('Turn Start: one ally under 50%', (844, 448, 264, 28), 1.0),
        ('HP heals 25% of Max HP.', (844, 478, 220, 26), .99), ('(Once per Encounter; does not', (844, 508, 274, 26), 1.0),
        ('activate if the ally is dead)', (840, 536, 230, 25), .99), ('Select', (1652, 847, 108, 44), 1.0),
        ('Refuse Gift', (1348, 851, 152, 34), 1.0)]


def catalog(*names):
    return SimpleNamespace(text_identity=lambda text: text if text in names else None)


def page(extra=(), title='First-aid Kit'):
    return [Text(title if text == 'First-aid Kit' else text, box, score) for text, box, score in ROWS] + [
        Text(text, box, .99) for text, box in extra]


def test_the_live_page_is_a_free_gift():
    assert single_free_page_is_priced(page(), SIZE, catalog('First-aid Kit')) is False


@pytest.mark.parametrize('line, box', [
    ('Max HP +10%', (844, 478, 220, 26)),                 # a trial word with a number, even in the card
    ('Mounting Trials', (880, 640, 180, 26)),             # the trial heading under the card
    ('Enemy Level', (860, 680, 150, 26)),
    ('Cost 10 Modules', (1300, 700, 200, 26)),            # a price elsewhere on the page
    ('Max HP', (1300, 478, 100, 26)),                     # the noun outside the card's own text
])
def test_a_trial_or_a_price_still_refuses_the_page(line, box):
    assert single_free_page_is_priced(page(extra=[(line, box)]), SIZE, catalog('First-aid Kit')) is True


def test_the_exemption_needs_a_title_the_catalogue_knows():
    # A title nobody can vouch for keeps the old, stricter reading.
    assert single_free_page_is_priced(page(title='Frst Kt'), SIZE, catalog('First-aid Kit')) is True
    assert single_free_page_is_priced(page(), SIZE, None) is True
    # A page without the effect line was never refused.
    plain = [row for row in page() if 'Max HP' not in row.text]
    assert single_free_page_is_priced(plain, SIZE, None) is False
