"""A pack's decorative heading above its title must not hide the title.

Live ``pi-20261122-033932`` (2026-11-22) stopped on the floor 5 pack choice with
``theme_candidates_profile_or_floor_not_proven``: all three cards read as unnamed.
The middle card prints "Masquerade" above its catalog title "Line 4 - Section #4",
and the joined band matched nothing. The same layout hid "Timekilling Time" under
its "TIMEKILLING TIME" logo on floor 4 of ``pi-20261122-004911``. The rows below
are retyped from those frames (``frame-0142`` and ``frame-0104``); the frames
themselves are local evidence.
"""
import json
from pathlib import Path

import numpy as np

from maalimbus.policies import Team
from maalimbus.theme_vision import ThemeCatalog, _named_cards, recommend_pack
from maalimbus.vision import Text

ROOT = Path(__file__).resolve().parents[1]
CARDS = [(526, 276, 255, 495), (832, 283, 255, 495), (1148, 284, 255, 495)]
IMAGE = np.zeros((1080, 1920, 3), np.uint8)


def catalog():
    """The tracked name list and aliases only: naming a card needs no game artwork."""
    data = json.loads((ROOT / 'assets/resource/base/theme-catalog.json').read_text(encoding='utf-8'))
    cat = ThemeCatalog.__new__(ThemeCatalog)
    cat.root = ROOT / 'assets/resource/base'
    cat.names = tuple(entry['name'] for entry in data['names'])
    cat.aliases = dict(data.get('aliases') or {})
    cat._merge_near_duplicates()
    cat.glyphs = {}
    return cat


def texts(rows):
    return [Text(text, tuple(box), score) for text, box, score in rows]


FLOOR_FIVE = texts([
    ('Wake of Dawnbreak', (532, 682, 218, 26), .999), ('Walpurgis', (548, 623, 122, 28), 1.0),
    ('The Wetge in the', (552, 655, 188, 33), .964), ('Line 4-', (844, 671, 96, 27), .978),
    ('Masquerade', (846, 627, 238, 40), .996), ('Section #4', (928, 671, 150, 27), .996),
    ('MADNESS', (1148, 585, 260, 109), .999), ('LINE', (1156, 591, 92, 52), .998),
    ('Line', (1234, 673, 68, 27), 1.0)])
FLOOR_FOUR = texts([
    ('Timekilling', (524, 663, 172, 39), 1.0), ('TIMKILING', (526, 587, 234, 42), .986),
    ('TME', (594, 621, 96, 44), .825), ('Time', (684, 667, 78, 29), 1.0),
    ('Abnormal Seismic', (860, 661, 196, 25), .999), ('Zone', (932, 686, 56, 20), 1.0),
    ('Crawling', (1164, 671, 130, 27), 1.0), ('Abyss', (1298, 671, 92, 27), 1.0)])


def names(records):
    return [card.name for card in _named_cards(IMAGE, records, catalog(), CARDS)]


def test_the_title_under_a_decorative_heading_is_read():
    # "The Wedge in the Wake of Dawnbreak" is not in the catalog and "Line 1" lost its
    # digit to OCR twice: those two stay unnamed rather than guessed.
    assert names(FLOOR_FIVE) == [None, 'Line 4 Section#4', None]
    assert names(FLOOR_FOUR) == ['Timekilling Time', 'Abnormal Seismi Zone', 'Crawling Abyss']


def test_the_floor_five_choice_is_the_named_pack():
    team = Team(slot=2, keywords=frozenset())
    choice, ranking = recommend_pack(_named_cards(IMAGE, FLOOR_FIVE, catalog(), CARDS), team)
    assert choice['name'] == 'Line 4 Section#4' and [r['name'] for r in ranking] == ['Line 4 Section#4']


def test_a_heading_alone_still_names_nothing():
    heading_only = [t for t in FLOOR_FIVE if t.text in ('Masquerade', 'MADNESS', 'LINE')]
    assert names(heading_only) == [None, None, None]
