"""The reward page is identified by a finished floor count, not by the literal 7/7.

The October runs cleared seven encounters on floor 5 and the page gate was written as
``7/7``. Run ``pi-20261123-133044`` cleared a four-node floor: the dialog printed
``4/4`` (stylised digits, OCR score 0.82), the gate failed, the offer reader gave up
without reading anything, and an authorised 5-module claim stopped with "Fresh
currency/cost/weekly offer differs". The rows are retyped from that frame.
"""
import pytest

from maalimbus.reward_cost import page_anchors
from maalimbus.vision import Text

SIZE = (1920, 1080)


def page(count='4/4', score=.821):
    return [Text('Exploration Reward', (794, 160, 334, 42), .99), Text('Floor 5', (480, 621, 84, 30), .986),
            Text('[HARD]', (480, 645, 82, 37), .999), Text(count, (490, 678, 64, 52), score),
            Text('To Window', (880, 798, 164, 38), .99), Text('Claim', (1238, 796, 98, 41), .99),
            Text('Weekly', (440, 339, 116, 42), 1.0), Text('Bonuses', (440, 375, 132, 39), 1.0)]


@pytest.mark.parametrize('count', ['4/4', '7/7', '6/6', '10/10'])
def test_a_finished_floor_count_identifies_the_page(count):
    assert page_anchors(page(count), SIZE) is True


@pytest.mark.parametrize('count, score', [('3/4', .99), ('6/7', .99), ('4/', .99), ('4/4', .5), ('44', .99)])
def test_an_unfinished_or_unreadable_count_does_not(count, score):
    assert page_anchors(page(count, score), SIZE) is False


def test_the_other_gates_keep_their_stricter_score():
    rows = page()
    rows[5] = Text('Claim', (1238, 796, 98, 41), .85)
    assert page_anchors(rows, SIZE) is False
