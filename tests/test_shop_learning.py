"""Synthetic receipt chains exercise the production learner; no live game claim."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from test_shop_transaction import shelf,frame,setup
from maalimbus.shop_transaction import ShopTransaction
from maalimbus.shop_learning import sync_receipts,refresh_decision
from maalimbus.runner import shop_state,settings
from maalimbus.storage import read_json,write_json


def refresh(tmp_path,root,scope,names=('Scalpel','Polarization')):
    tmp_path.mkdir(exist_ok=True)
    before=frame(tmp_path,'before',shelf(('Prejudice','Grey Coat')))
    tx=ShopTransaction(tmp_path/'tx.json')
    tx.begin_visit(scope,'1',before,dict(keywords=['Rupture'],wanted=['Oracle'],reserve_coins=0))
    tx.reserve_refresh(scope,'1',15,100,2,before)
    after=frame(tmp_path,'after',shelf(names,85))
    tx.reconcile_refresh(scope,'1',after)
    return tx,sync_receipts(tx,root,['Oracle'],['Rupture'])


def test_three_actual_receipt_visits_reduce_refreshes_without_raising_caps(tmp_path):
    root=tmp_path/'review'
    for i in range(3):tx,samples=refresh(tmp_path/str(i),root,'scope'+str(i))
    decision,trace=refresh_decision(samples)
    assert not decision and trace['refresh_learning_applied']
    assert len(samples)==3 and all(s['useful_yield']==0 for s in samples)
    assert len(list(root.glob('*/review.json')))==3
    assert sync_receipts(tx,root,['Oracle'],['Rupture'])==samples
    first=next(root.glob('*/review.json'));write_json(first,dict(status='rejected'))
    assert refresh_decision(sync_receipts(tx,root,['Oracle'],['Rupture']))[0]


def test_changed_native_proof_cannot_teach_the_learner(tmp_path):
    tx,samples=refresh(tmp_path/'one',tmp_path/'review','scope')
    Path(samples[0]['after']['path']).with_suffix('.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):
        sync_receipts(tx,tmp_path/'review',['Oracle'],['Rupture'])


def test_useful_stock_is_measured_and_buy_strength_remains_unknown(tmp_path):
    tx,samples=refresh(tmp_path/'one',tmp_path/'review','scope',('Oracle','Polarization'))
    assert samples[0]['useful_yield']==1 and samples[0]['gift_causal_strength'] is None
    assert refresh_decision(samples)[0]
    assert sync_receipts(tx,tmp_path/'review',['Oracle'],['Poise'])==[]


def test_project_refresh_review_reuses_native_proofs_and_preserves_human_review(tmp_path):
    root=tmp_path/'build/learning-review/shop'
    tx,samples=refresh(tmp_path/'native',root,'scope',('Oracle','Polarization'))
    folder=next(root.glob('*/sample.json')).parent
    assert not list(folder.glob('*.png')) and not (folder/'before.json').exists()
    marker=read_json(folder/'evidence-storage.json')
    assert marker['kind']=='canonical_refresh_evidence_v1'
    assert marker['roles']['before']==samples[0]['before']
    write_json(folder/'review.json',dict(status='rejected',notes='human decision'))
    original={p:p.read_bytes() for p in folder.iterdir()}
    assert sync_receipts(tx,root,['Oracle'],['Rupture'])==[]
    assert original=={p:p.read_bytes() for p in folder.iterdir()}


@pytest.mark.parametrize('fault',['descriptor','original','mirror'])
def test_refresh_reference_corruption_refuses_without_repair(tmp_path,fault):
    root=tmp_path/'build/learning-review/shop'
    tx,samples=refresh(tmp_path/'native',root,'scope')
    folder=next(root.glob('*/sample.json')).parent
    if fault=='descriptor':
        marker=read_json(folder/'evidence-storage.json');marker['kind']='canonical_purchase_evidence_v1'
        write_json(folder/'evidence-storage.json',marker)
    elif fault=='original':Path(samples[0]['after']['path']).with_suffix('.png').write_bytes(b'changed')
    else:(folder/'before.png').write_bytes(b'changed')
    before={p:p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(ValueError):sync_receipts(tx,root,['Oracle'],['Rupture'])
    assert before=={p:p.read_bytes() for p in folder.iterdir()}


def test_refresh_queue_rejects_purchase_family(tmp_path):
    from maalimbus.shop_evidence import descriptor
    with pytest.raises(ValueError,match='family'):
        descriptor(tmp_path/'build/learning-review/shop/key',dict(kind='purchase_outcome'),'key')


def test_player_reserve_applies_to_purchase_and_refresh_before_any_write(tmp_path):
    tx,before=setup(tmp_path);unchanged=tx.path.read_bytes()
    with pytest.raises(ValueError):tx.reserve_purchase('scope','floor1:shop1',dict(name='Oracle',price=20),100,before,reserve_coins=81)
    with pytest.raises(ValueError):tx.reserve_refresh('scope','floor1:shop1',15,100,2,before,reserve_coins=86)
    assert tx.path.read_bytes()==unchanged and tx.data['pending'] is None
    record=read_json(before)
    result=shop_state(record,['Oracle'],reserve_coins=90,policy='learned')
    assert result['buy'] is None and result['refresh'] is None


@pytest.mark.parametrize('value',[True,2.5,-1,6])
def test_invalid_refresh_settings_refuse(value):
    with pytest.raises(ValueError):settings(dict(shop_refreshes=value))
