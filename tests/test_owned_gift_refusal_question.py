"""Refuse Gift asks a question first; that question is the Refuse press's proven successor.

Live ``pi-20261121-234709`` (2026-11-22): after a floor battle the single free gift
was the already-owned Phlebotomy Pack, the run pressed Refuse Gift and the game asked
"Continue without choosing an E.G.O Gift?" (``frame-0507``). The successor check
demanded the map or the reward card straight after the Refuse press, so the run
stopped with ``floor_gift_refusal_successor_not_proven`` one step before the existing
``confirm_proven_owned_gift_refusal`` would have answered it. The OCR rows below are
retyped from that frame; the frame itself is local evidence.
"""
from types import SimpleNamespace

import pytest

from maalimbus.floor_gift_transaction import FloorGiftTransaction, refusal_confirm_target
from maalimbus.window import plan_step

QUESTION = dict(size=[1920, 1080], ocr=[
    dict(text='Continue without choosing an E.G.O Gift?', box=[686, 502, 544, 28], score=.99),
    dict(text='X Cancel', box=[706, 720, 138, 36], score=.99),
    dict(text='Confirm', box=[1068, 718, 158, 38], score=.99),
    dict(text='Refuse Gift', box=[1348, 851, 152, 36], score=.99),
    dict(text='Select', box=[1652, 847, 108, 42], score=.99)])


def pending(tmp_path):
    tx = FloorGiftTransaction(tmp_path / 'gift.json')
    tx.data = dict(scope='run', pending=dict(kind='refuse_owned', title='Phlebotomy Pack',
                                             proof='frame-0506.json'),
                   commit_sent=False, selected=[], completed=False, receipts=[])
    return tx


def test_the_live_question_names_its_confirm():
    assert refusal_confirm_target(QUESTION) == [1068, 718, 158, 38]


def test_the_question_keeps_the_refusal_pending_for_its_confirm(tmp_path):
    tx = pending(tmp_path)
    assert tx.observe_refusal('UNKNOWN_DIALOG', 'frame-0507.json', confirm_question=True) is False
    reread = FloorGiftTransaction(tx.path).data
    assert reread['pending']['kind'] == 'refuse_owned' and not reread['completed']
    assert reread['pending']['question_proof'] == 'frame-0507.json'
    # The Confirm is booked once, and only the map or the reward card completes it.
    tx = FloorGiftTransaction(tx.path)
    tx.refusal_confirm_intent('run', 'frame-0507.json')
    with pytest.raises(ValueError, match='successor_not_proven'):
        tx.observe_refusal('UNKNOWN_DIALOG', 'frame-0508.json', confirm_question=True)
    assert tx.observe_refusal('MAP', 'frame-0509.json', map_floor=3) is True
    assert tx.data['completed'] and tx.data['pending'] is None


@pytest.mark.parametrize('page,question', [('UNKNOWN_DIALOG', False), ('UNKNOWN', True),
                                           ('GIFT_WARNING', True)])
def test_anything_but_the_exact_question_still_stops(tmp_path, page, question):
    tx = pending(tmp_path)
    with pytest.raises(ValueError, match='successor_not_proven'):
        tx.observe_refusal(page, 'frame.json', confirm_question=question)
    assert tx.data['pending']['kind'] == 'refuse_owned' and 'question_proof' not in tx.data['pending']


def test_the_refuse_plan_names_the_question_page():
    box = [1348, 851, 152, 36]
    plan = plan_step('GIFT_PICK', controls={'gift_pick.refuse_button': box},
                     gift=dict(refuse_owned=True, refuse_target=box))
    assert plan['target'] == box and 'UNKNOWN_DIALOG' in plan['expect']
