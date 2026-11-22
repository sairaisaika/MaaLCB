"""A Super Shop refresh restocks the gifts; its services are not part of the proof.

The rows are retyped from the live run ``pi-20261121-200305`` (2026-11-21): before the
refresh the shelf read 6 rows because both ``Replace ... Skill`` services dropped out
with an unreadable ``??``; after it the shelf read 7 because one ``??`` came back as
``77``. The 15-coin delta was exact. The live frames themselves are local evidence.
"""
from pathlib import Path

import pytest

from maalimbus.shop_transaction import refreshed_gifts

ROOT = Path(__file__).resolve().parents[1]

BEFORE = [dict(name='ID Skill Search', price=77), dict(name='Sticky Muck', price=156),
          dict(name='High-tensility Shoes', price=148), dict(name='Headless Portrait', price=151),
          dict(name='Rusted Muzzle', price=164), dict(name='Overused Whetstone', price=148)]
AFTER = [dict(name='ID Skill Search', price=77), dict(name="Replace Outis's Skill", price=77),
         dict(name='Headless Portralt', price=151), dict(name='Broken Revolver', price=158),
         dict(name='Dimensional Recycle Bin', price=148), dict(name='Blood, Sweat, and Tears', price=200),
         dict(name='Lithograph', price=165)]


def names(rows):
    return [row['name'] for row in rows]


def test_services_are_left_out_and_gifts_kept_in_order():
    assert names(refreshed_gifts(BEFORE)) == ['Sticky Muck', 'High-tensility Shoes', 'Headless Portrait',
                                              'Rusted Muzzle', 'Overused Whetstone']
    assert names(refreshed_gifts(AFTER)) == ['Headless Portralt', 'Broken Revolver', 'Dimensional Recycle Bin',
                                             'Blood, Sweat, and Tears', 'Lithograph']


def test_the_live_refresh_now_compares_like_with_like():
    before, after = refreshed_gifts(BEFORE), refreshed_gifts(AFTER)
    assert len(before) == len(after) == 5                      # 6 against 7 with the services counted
    assert sorted((r['name'], r['price']) for r in before) != sorted((r['name'], r['price']) for r in after)


@pytest.mark.parametrize('title', ["Replace Gregor's Skill", 'Replace Rodions Skill', 'ID Skill Search',
                                   'id skill search'])
def test_every_service_spelling_is_dropped(title):
    assert refreshed_gifts([dict(name=title, price=77)]) == []


def test_a_plain_shop_shelf_is_unchanged_and_empty_input_is_empty():
    plain = [dict(name='Sticky Muck', price=156), dict(name='Lithograph', price=165)]
    assert refreshed_gifts(plain) == plain
    assert refreshed_gifts(None) == [] and refreshed_gifts([]) == []


RUN = 'dist/MaaLimbus/evidence/runtime/pi-20261121-200305'


@pytest.mark.needs_local(RUN + '/frame-0043.json', RUN + '/frame-0045.json')
def test_the_live_super_shop_frames_read_five_gifts_each():
    import json

    from maalimbus import shop_transaction as st
    from maalimbus.vision import Text

    def gifts(frame):
        record = json.loads((ROOT / RUN / (frame + '.json')).read_text(encoding='utf-8'))
        texts = [Text(t['text'], tuple(t['box']), t['score']) for t in record['ocr']]
        size = tuple(record['size'])
        return st._coins(texts, size), refreshed_gifts(st._shelf(texts, size))
    coins_before, before = gifts('frame-0043')
    coins_after, after = gifts('frame-0045')
    assert (coins_before, coins_after) == (852, 837)           # exactly the 15-coin refresh
    assert len(before) == len(after) == 5 and names(before) != names(after)
