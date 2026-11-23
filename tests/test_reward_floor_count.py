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


def page(count='4/4', score=.821, leave=('To Window', (880, 798, 164, 38))):
    return [Text('Exploration Reward', (794, 160, 334, 42), .99), Text('Floor 5', (480, 621, 84, 30), .986),
            Text('[HARD]', (480, 645, 82, 37), .999), Text(count, (490, 678, 64, 52), score),
            Text(leave[0], leave[1], .99), Text('Claim', (1238, 796, 98, 41), .99),
            Text('Weekly', (440, 339, 116, 42), 1.0), Text('Bonuses', (440, 375, 132, 39), 1.0)]


@pytest.mark.parametrize('count', ['4/4', '7/7', '6/6', '10/10'])
def test_a_finished_floor_count_identifies_the_page(count):
    assert page_anchors(page(count), SIZE) is True


def test_the_dialog_reopened_from_the_dungeon_list_is_the_same_page():
    # pi-20261123-180315/frame-0032: the game was restarted on the reward dialog; entering
    # the Mirror Dungeon again reopened it with 'To List' in place of 'To Window' and the
    # same 4/4 at score 0.65. Both gates refused it and an authorised claim stopped.
    rows = page(score=.65, leave=('To List', (904, 798, 112, 35)))
    assert page_anchors(rows, SIZE) is True
    assert page_anchors(page(leave=('To Lobby', (904, 798, 112, 35))), SIZE) is False


@pytest.mark.parametrize('count, score', [('3/4', .99), ('6/7', .99), ('4/', .99), ('4/4', .4), ('44', .99)])
def test_an_unfinished_or_unreadable_count_does_not(count, score):
    assert page_anchors(page(count, score), SIZE) is False


def test_the_other_gates_keep_their_stricter_score():
    rows = page()
    rows[5] = Text('Claim', (1238, 796, 98, 41), .85)
    assert page_anchors(rows, SIZE) is False


class Detail:
    def __init__(self, results):
        self.hit = bool(results)
        self.filtered_results = results


class Hit:
    def __init__(self, score=None, text=None):
        self.score, self.text = score, text


class Native:
    """Template scores per (crop, box x); OCR texts per box x. Nothing below 0.95 is a hit."""

    def __init__(self, templates, texts):
        self.templates, self.texts = templates, texts

    def run_recognition_direct(self, kind, param, image):
        box = tuple(param.roi)
        if getattr(param, 'template', None):
            score = self.templates.get((param.template[0], box[0]))
            return Detail([Hit(score=score)] if score is not None and score >= .95 else [])
        text = self.texts.get(box[0])
        return Detail([Hit(score=.99, text=text)] if text else [])


LIVE = {('reward/module-currency.png', 1370): .946, ('reward/module-currency-two-digit.png', 1370): .974,
        ('reward/module-currency-two-digit.png', 1364): .819, ('reward/module-currency.png', 1364): .80,
        ('reward/deduction-sign.png', 1429): .976}
TEXTS = {1448: '5', 1444: '5', 650: '0/3'}


def observe(templates, texts=TEXTS):
    pytest.importorskip('maa')
    import numpy as np
    from maalimbus.reward_cost import observe_native
    return observe_native(Native(templates, texts), np.zeros((1080, 1920, 3), np.uint8), page())


def test_the_live_five_module_offer_is_read_with_the_other_crop_of_the_same_icon():
    offer, evidence = observe(LIVE)
    assert offer == dict(currency='enkephalin_modules', cost=5, weekly=0)
    currency = next(row for row in evidence if row['purpose'] == 'currency')
    assert currency['layout'] == 'one_digit' and currency['template'] == 'reward/module-currency-two-digit.png'
    assert currency['results'] == [dict(score=.974)]


def test_no_crop_reaching_the_threshold_is_still_no_offer():
    weak = {**LIVE, ('reward/module-currency-two-digit.png', 1370): .94}
    offer, evidence = observe(weak)
    assert offer is None
    assert next(row for row in evidence if row['purpose'] == 'currency')['results'] == []


def test_a_missing_sign_or_disagreeing_digits_still_refuse():
    assert observe({k: v for k, v in LIVE.items() if 'deduction' not in k[0]})[0] is None
    assert observe(LIVE, {**TEXTS, 1444: '6'})[0] is None
