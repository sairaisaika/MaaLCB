"""Native review references preserve hashes, labels and legacy copied datasets."""
import json
from pathlib import Path

import pytest

from maalimbus.shop_outcomes import sync
from maalimbus.shop_value_training import review_sample


def sample(tmp_path):
    from test_shop_value_training import sample_folder,ledger_for
    from test_shop_review_ownership import transaction_for
    origin=tmp_path/'source-fixture'
    old=sample_folder(origin,'canonical',scope='scope',status='pending',
                      benefit=None,eligible=False,approved_outcome=False)
    tx=transaction_for(old);ledger=ledger_for(origin)
    queue=tmp_path/'build/learning-review/shop-purchases'
    assert len(sync(tx,queue,ledger))==1
    folder=next(p.parent for p in queue.glob('*/sample.json'))
    return tx,ledger,queue,folder


def test_new_canonical_samples_reverify_without_any_image_mirrors(tmp_path):
    tx,ledger,queue,folder=sample(tmp_path)
    assert (folder/'evidence-storage.json').is_file()
    assert not list(folder.glob('*.png'))
    result,problem=review_sample(folder,ledger=ledger)
    assert problem is None and result['benefit']==.8
    original={p:p.read_bytes() for p in folder.iterdir()}
    assert len(sync(tx,queue,ledger))==1
    assert original=={p:p.read_bytes() for p in folder.iterdir()}


@pytest.mark.parametrize('fault',['descriptor','missing_original','changed_original','wrong_role','partial_mirror'])
def test_canonical_reference_failures_are_excluded_without_label_or_state_repair(tmp_path,fault):
    _,ledger,_,folder=sample(tmp_path)
    payload=json.loads((folder/'sample.json').read_text())
    native=Path(payload['before']['path'])
    if fault=='descriptor':
        p=folder/'evidence-storage.json';d=json.loads(p.read_text());d['sample']='foreign';p.write_text(json.dumps(d))
    elif fault=='missing_original':native.with_suffix('.png').unlink()
    elif fault=='changed_original':native.with_suffix('.png').write_bytes(b'changed')
    elif fault=='wrong_role':
        p=folder/'evidence-storage.json';d=json.loads(p.read_text());d['roles']['before']=d['roles']['after'];p.write_text(json.dumps(d))
    else:(folder/'before.json').write_bytes(native.read_bytes())
    before={p:p.read_bytes() for p in folder.iterdir()}
    value,problem=review_sample(folder,ledger=ledger)
    assert value is None and problem
    assert before=={p:p.read_bytes() for p in folder.iterdir()}


def test_explicit_reference_storage_keeps_human_rejection_and_benefit(tmp_path):
    tx,ledger,queue,folder=sample(tmp_path)
    p=folder/'review.json';p.write_text('{"status":"rejected","notes":"human","benefit":0.1}')
    before=p.read_bytes()
    assert sync(tx,queue,ledger)==[]
    assert p.read_bytes()==before


def test_copy_dataset_without_explicit_descriptor_never_falls_back_to_original(tmp_path):
    from test_shop_value_training import sample_folder,ledger_for
    folder=sample_folder(tmp_path/'samples','legacy')
    (folder/'before.png').unlink()
    value,reason=review_sample(folder,ledger=ledger_for(tmp_path/'samples'))
    assert value is None and reason
