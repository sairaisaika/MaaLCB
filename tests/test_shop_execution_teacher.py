"""Live reconciliation and offline teachers must agree on native purchase proof."""
import copy
import json

import pytest

from maalimbus.shop_transaction import _frame, purchase_execution_witness
from maalimbus.shop_outcomes import sync
from maalimbus.shop_value_training import _purchase_rule


def test_real_reader_badge_closes_purchase_and_both_teachers_despite_other_slot_ocr(tmp_path):
    from test_shop_transaction import setup,reserve,frame,shelf,question,row
    tx,before=setup(tmp_path);reserve(tx,before)
    tx.reserve_confirm('scope','floor1:shop1',frame(tmp_path,'dialog',question(),'SHOP_PURCHASE'))
    rows=shelf(names=('Oracle','ScalpeI'),coins=80)
    rows.append(row('Purchased',(870,320,120,40)))
    after=frame(tmp_path,'after',rows)
    assert tx.reconcile_purchase('scope','floor1:shop1',after)
    original=tx.path.read_bytes()
    samples=sync(tx,tmp_path/'review')
    assert len(samples)==1
    folder=next(p.parent for p in (tmp_path/'review').glob('*/sample.json'))
    sample=json.loads((folder/'sample.json').read_text())
    def read(role):
        record,texts,size,_=_frame(folder/(role+'.json'))
        return dict(record=record,texts=texts,size=size)
    assert sample['receipt_teacher']=='native_exact_coin_delta_own_purchased_badge'
    assert _purchase_rule(sample,read('before'),read('after')) is None
    assert sample['gift_causal_strength'] is None
    assert json.loads((folder/'review.json').read_text())['status']=='pending'
    assert tx.path.read_bytes()==original
    assert len(sync(tx,tmp_path/'review'))==1  # Idempotent; no duplicate sample.


@pytest.mark.parametrize('fault',['missing_badge','wrong_price','duplicate_badge','wrong_coins','already_bought'])
def test_teacher_does_not_invent_execution_from_badge_or_spend_alone(fault):
    prior=[dict(name='Oracle',price=20),dict(name='Scalpel',price=20)]
    after=[dict(name='Oracle',price=20,purchased=True),dict(name='Other OCR',price=20)]
    coins=80
    if fault=='missing_badge':after[0].pop('purchased')
    if fault=='wrong_price':after[0]['price']=21
    if fault=='duplicate_badge':after.append(copy.deepcopy(after[0]))
    if fault=='wrong_coins':coins=79
    if fault=='already_bought':prior[0]['purchased']=True
    with pytest.raises(ValueError):purchase_execution_witness(prior,after,'Oracle',20,100,coins)


def test_old_complete_shelf_badge_teacher_keeps_its_content_address_and_review(tmp_path):
    from test_shop_transaction import setup,reserve,frame,shelf,question,row
    tx,before=setup(tmp_path);reserve(tx,before)
    tx.reserve_confirm('scope','floor1:shop1',frame(tmp_path,'dialog',question(),'SHOP_PURCHASE'))
    rows=shelf(coins=80);rows.append(row('Purchased',(870,320,120,40)))
    tx.reconcile_purchase('scope','floor1:shop1',frame(tmp_path,'after',rows))
    sync(tx,tmp_path/'review')
    folder=next(p.parent for p in (tmp_path/'review').glob('*/sample.json'))
    assert json.loads((folder/'sample.json').read_text())['receipt_teacher']==(
        'native_exact_coin_delta_complete_shelf_and_item_status')
    review=folder/'review.json';review.write_text('{"status":"rejected","notes":"human"}')
    before=review.read_bytes()
    sync(tx,tmp_path/'review')
    assert review.read_bytes()==before and len(list((tmp_path/'review').iterdir()))==1


def test_currency_only_live_recovery_is_not_automatically_a_training_example(tmp_path):
    from test_shop_transaction import setup,reserve,frame,shelf,question
    tx,before=setup(tmp_path);reserve(tx,before)
    tx.reserve_confirm('scope','floor1:shop1',frame(tmp_path,'dialog',question(),'SHOP_PURCHASE'))
    # Live recovery records a currency-only receipt; teachers still lack their
    # own Purchased badge or a complete remaining shelf and must not label it.
    tx.reconcile_purchase('scope','floor1:shop1',frame(tmp_path,'after',shelf(names=('Unknown',),coins=80)))
    before=tx.path.read_bytes()
    with pytest.raises(ValueError):sync(tx,tmp_path/'review')
    assert tx.path.read_bytes()==before and not list((tmp_path/'review').glob('*/sample.json'))
