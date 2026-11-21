"""Synthetic protocol tests, including training/export/runtime round trip.

These fixtures are not game observations or evidence of model quality on a real
account. They verify that runtime recomputes the required heldout evaluation.
"""
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from maalimbus import shop_value_training as training
from maalimbus.shop_value_shadow import rank_preview


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    from test_shop_value_training import sample_folder, tiny_catalog, ledger_for
    root=tmp_path_factory.mktemp('shop-promotion-protocol')
    catalog=tiny_catalog(root/'catalog.json')
    samples=root/'samples'
    for index in range(20):
        good=index%2==0
        name='Alpha Gift' if good else 'Beta Gift'
        other='Beta Gift' if good else 'Alpha Gift'
        sample_folder(samples,'sample-%d'%index,scope='scope-%02d'%index,
            name=name,price=120,others=((other,200),),benefit=.9 if good else .1)
    out=root/'model'
    report=training.train_and_export(samples,catalog,out,ledger=ledger_for(samples),
                                     epochs=400,min_episodes=1)
    assert report['trained'] and report['participation']=='ranked', report
    return out


@pytest.fixture
def candidate(tmp_path,trained):
    root=tmp_path/'candidate'
    shutil.copytree(trained,root)
    return root


def data(root):
    return (json.loads((root/'weights.json').read_text()),
            json.loads((root/'modelcard.json').read_text()))


def save(root,model,card,*,rebind_dataset=False):
    if rebind_dataset:
        summary=card['verification']
        digest=training._verification_digest(summary['episodes'])
        summary['dataset_sha256']=card['dataset_sha256']=model['dataset_sha256']=digest
    raw=json.dumps(model,sort_keys=True).encode()
    (root/'weights.json').write_bytes(raw)
    card['weights_sha256']=hashlib.sha256(raw).hexdigest()
    (root/'modelcard.json').write_text(json.dumps(card))


def preview(root):
    offers=[SimpleNamespace(name='Beta Gift',price=120),SimpleNamespace(name='Alpha Gift',price=120)]
    ordered,trace=rank_preview(offers,dict(coins=1000,reserve_coins=0,
        keywords=['Poise'],wanted=['Alpha Gift','Beta Gift']),root)
    return offers,ordered,trace


def test_verified_training_export_recomputes_holdout_and_participates(candidate):
    offers,ordered,trace=preview(candidate)
    assert ordered==[offers[1],offers[0]]
    assert trace['neural_value_ranked'] and trace['buy_learning_applied']
    assert trace['participation']=='ranked'
    assert trace['held_out']['pairs']>=training.PROMOTION_MIN_PAIRS
    assert trace['held_out']['pairwise_accuracy']>=training.PROMOTION_MIN_ACCURACY
    assert not trace['purchase_input_authorized']
    assert set(map(id,ordered))==set(map(id,offers))


@pytest.mark.parametrize('fault',['missing_receipt','overlap','incomplete','wrong_partition',
    'missing_review','missing_outcome','duplicate_purchase','constant_targets','nan_target','missing_observation'])
def test_invalid_receipts_demote_without_stopping_rule_pipeline(candidate,fault):
    model,card=data(candidate)
    rows=card['verification']['episodes']
    if fault=='missing_receipt':model.pop('training_split')
    elif fault=='overlap':model['training_split']['held_out_scopes'].append(model['training_split']['trained_scopes'][0])
    elif fault=='incomplete':model['training_split']['held_out_scopes'].pop()
    elif fault=='wrong_partition':
        split=model['training_split']
        split['trained_scopes'][0],split['held_out_scopes'][0]=split['held_out_scopes'][0],split['trained_scopes'][0]
        split['trained_scopes'].sort();split['held_out_scopes'].sort()
    elif fault=='missing_review':rows[0].pop('review_sha256')
    elif fault=='missing_outcome':rows[0]['outcome_sha256']=[]
    elif fault=='duplicate_purchase':rows[1]['hashes']=rows[0]['hashes']
    elif fault=='constant_targets':
        for row in rows:row['target']=.6
    elif fault=='nan_target':rows[0]['target']=float('nan')
    elif fault=='missing_observation':rows[0]['observation']=None
    save(candidate,model,card,rebind_dataset=True)
    offers,ordered,trace=preview(candidate)
    assert ordered==offers and trace['neural_value_shadow_applied']
    assert not trace['neural_value_ranked'] and not trace['buy_learning_applied']
    assert trace['participation']=='shadow' and not trace['purchase_input_authorized']


def test_claimed_accuracy_cannot_promote_a_model_that_orders_backwards(candidate):
    model,card=data(candidate)
    model['parameters']['w2']=[-value for value in model['parameters']['w2']]
    model['parameters']['b2']=-model['parameters']['b2']
    card['curriculum'].update(pairs=99999,pairwise_accuracy=1.0)
    save(candidate,model,card)
    offers,ordered,trace=preview(candidate)
    assert ordered==offers and not trace['neural_value_ranked']
    assert trace['held_out']['pairwise_accuracy']==0.0
    assert trace['held_out']['pairs']<99999


@pytest.mark.parametrize('field',['target','observation','review_sha256'])
def test_editing_review_rows_breaks_the_dataset_bound_to_weights(candidate,field):
    model,card=data(candidate)
    card['verification']['episodes'][0][field]=None
    # Only modelcard changed: its digest no longer describes the bound rows.
    (candidate/'modelcard.json').write_text(json.dumps(card))
    offers,ordered,trace=preview(candidate)
    assert ordered==offers and not trace['neural_value_shadow_applied']
    assert trace['reason']=='invalid_value_candidate_rule_fallback'


def test_shadow_preference_keeps_order_even_if_heldout_evaluation_passes(candidate):
    model,card=data(candidate);card['participation']='shadow'
    save(candidate,model,card)
    offers,ordered,trace=preview(candidate)
    assert trace['promotion']['eligible'] and not trace['neural_value_ranked']
    assert ordered==offers and not trace['buy_learning_applied']


def test_displayed_accuracy_is_recomputed_not_the_editable_claim(candidate):
    from maalimbus.decision_log import lines
    model,card=data(candidate);card['curriculum'].update(pairs=99999,pairwise_accuracy=.01)
    save(candidate,model,card)
    _,_,trace=preview(candidate)
    text=lines('shop_decision_ranking',dict(learning=trace))[-1]
    assert '已参与购买顺序' in text and '99999' not in text and '准确率1.00/' in text


def test_export_capacity_failure_keeps_previous_model_bytes(candidate,monkeypatch):
    from maalimbus import workspace
    model,card=data(candidate)
    before={p.name:p.read_bytes() for p in candidate.iterdir()}
    def full(*a,**kw):raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(workspace,'reserve_output',full)
    with pytest.raises(ValueError,match='budget'):
        training.export_candidate(model['parameters'],card,candidate,vocabulary=model['vocabulary'],
            keyword_vocabulary=model['keyword_vocabulary'],min_episodes=1)
    assert before=={p.name:p.read_bytes() for p in candidate.iterdir()}


def test_diagnostic_executes_scorer_without_exposing_training_scopes_or_writes(candidate):
    from maalimbus.shop_value_shadow import diagnostic
    before={p.name:p.read_bytes() for p in candidate.iterdir()}
    result=diagnostic(candidate)
    assert result['prediction_executed'] and not result['game_input']
    assert result['scope']=='hypothetical_readonly_offer_not_a_live_purchase_quote'
    assert not result['purchase_input_authorized'] and 'scope-' not in json.dumps(result)
    assert before=={p.name:p.read_bytes() for p in candidate.iterdir()}
