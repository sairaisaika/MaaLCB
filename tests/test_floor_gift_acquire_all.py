"""A page that hands over every card: no trial, and the counter asks for all of them.

Live pi-20261127-195850 frame-0016 after the floor-1 theme pack: three cards under
"Acquire E.G.O Gift", no "Mounting Trials", counter 0/3. The run stopped on it with
floor_gift_enemy_trial_not_unique. The OCR below is that frame's, card text included.
"""
import pytest

from maalimbus import floor_gifts
from maalimbus.vision import Text

SIZE = (1920, 1080)
ROWS = [
    ((580, 228, 150, 28), 'Acquire E.G.O Gift'), ((974, 226, 152, 30), 'Acquire E.G.O Gift'),
    ((1372, 228, 154, 28), 'Acquire E.G.O Gift'), ((426, 271, 270, 28), 'Ornamental Horseshoe'),
    ((882, 266, 150, 33), 'Green Spirit'), ((1274, 270, 160, 27), "Devil's Share"),
    ((444, 446, 238, 32), 'Tum Start: apply 2 Poise'), ((842, 450, 260, 26), 'After hitting a non-Staggered'),
    ((1238, 448, 274, 30), 'Turn End: apply 1 + Haste next'), ((842, 591, 202, 28), 'of4 #Tremor Potency'),
    ((1240, 649, 222, 26), 'If the ally has Lust Affinity'), ((1766, 845, 48, 42), '0/3'),
    ((1350, 851, 150, 34), 'Refuse Gift'), ((1624, 853, 90, 30), 'Select'),
]
BOXES = [(386, 220, 360, 600), (782, 220, 360, 600), (1178, 220, 360, 600)]


class Catalog:
    entries = {}

    def text_identity(self, text):
        return None


def records(extra=()):
    return [Text(text, box, .99) for box, text in list(ROWS) + list(extra)]


def test_every_card_is_an_offer_with_no_trial_and_the_counter_counts_the_picks(monkeypatch):
    monkeypatch.setattr(floor_gifts, 'gift_cards', lambda texts, size: BOXES)
    monkeypatch.setattr(floor_gifts, 'identity_of', lambda catalog, title: title)
    offers, state = floor_gifts.observe(records(), SIZE, Catalog())
    assert [offer.title for offer in offers] == ['Ornamental Horseshoe', 'Green Spirit', "Devil's Share"]
    assert all(offer.trial.penalty == 0 and not offer.unpriced for offer in offers)
    assert state == dict(chosen=0, required=3, evidence='acquire_all')
    # A trial anywhere on the page sends it back to the floor gift reader.
    with pytest.raises(ValueError):
        floor_gifts.observe(records([((600, 640, 200, 28), 'Mounting Trials')]), SIZE, Catalog())
    with pytest.raises(ValueError, match='trial_not_unique'):
        floor_gifts.observe_acquire_all(records([((600, 700, 200, 28), 'Enemy Level +2')]), SIZE, Catalog(),
                                        BOXES, dict(chosen=0, required=3))
