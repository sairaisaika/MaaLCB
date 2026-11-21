"""Recompute a shop candidate's heldout ranking; never authorize an input.

The dataset digest binds observations, targets and review-byte hashes; the weight
digest binds its scope split. Modelcard flags/claimed accuracy alone are not a
promotion receipt. Old candidates may continue predicting in shadow.
"""
import math
import re

from .shop_value_training import (PROMOTION_MIN_ACCURACY, PROMOTION_MIN_PAIRS,
    encode_observation, forward, pairwise_accuracy, split_by_scope)


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def evaluate(model, verification):
    result = dict(eligible=False, reason='promotion_receipt_missing',
                  pairs=0, pairwise_accuracy=None, purchase_input_authorized=False)
    split = model.get('training_split')
    if not isinstance(split, dict):
        return result
    try:
        if (split.get('schema_version') != 1 or type(split.get('split_seed')) is not int or
                split['split_seed'] != 7 or type(split.get('test_fraction')) not in (int,float) or
                split['test_fraction'] != 0.3):
            raise ValueError('promotion_split_schema_invalid')
        train, test = split.get('trained_scopes'), split.get('held_out_scopes')
        if (not isinstance(train, list) or not isinstance(test, list) or not train or not test or
                any(not isinstance(s,str) or not s for s in train+test) or
                len(set(train+test)) != len(train)+len(test)):
            raise ValueError('promotion_scopes_not_independent')
        entries = verification.get('episodes')
        if (not isinstance(entries,list) or not entries or len(entries)>10000 or
                len(entries) != verification.get('verified_rows')):
            raise ValueError('promotion_row_manifest_invalid')
        by_scope, seen_samples, seen_purchases = {}, set(), set()
        for entry in entries:
            if not isinstance(entry,dict):
                raise ValueError('promotion_row_invalid')
            scope, sample, target = entry.get('scope'), entry.get('sample'), entry.get('target')
            if (not isinstance(scope,str) or not scope or not _digest(sample) or
                    sample != entry.get('content_address') or sample in seen_samples or
                    not _digest(entry.get('review_sha256')) or
                    type(target) not in (int,float) or not math.isfinite(target) or not 0<=target<=1):
                raise ValueError('promotion_review_row_not_bound')
            hashes = entry.get('hashes')
            if not isinstance(hashes,dict):
                raise ValueError('promotion_purchase_hashes_missing')
            proof = []
            for role in ('before','after'):
                values = hashes.get(role)
                if (not isinstance(values,dict) or
                        any(not _digest(values.get(k)) for k in ('json_sha256','png_sha256'))):
                    raise ValueError('promotion_purchase_hashes_missing')
                proof.extend(values[k] for k in ('json_sha256','png_sha256'))
            if tuple(proof) in seen_purchases:
                raise ValueError('promotion_purchase_reused')
            outcomes = entry.get('outcome_sha256')
            if not isinstance(outcomes,list) or not outcomes or any(not _digest(x) for x in outcomes):
                raise ValueError('promotion_delayed_outcome_missing')
            observation = entry.get('observation')
            if not isinstance(observation,dict) or observation.get('action') != 'buy':
                raise ValueError('promotion_observation_missing')
            values = encode_observation(observation,vocabulary=model['vocabulary'],
                keyword_vocabulary=model['keyword_vocabulary'])['values']
            by_scope.setdefault(scope,[]).append(dict(values=values,target=float(target)))
            seen_samples.add(sample);seen_purchases.add(tuple(proof))
        if (set(by_scope) != set(train+test) or
                len(by_scope) != verification.get('verified_episodes')):
            raise ValueError('promotion_split_does_not_cover_dataset')
        expected_train, expected_test = split_by_scope([dict(scope=s) for s in by_scope],
            test_fraction=split['test_fraction'],seed=split['split_seed'])
        if (train != [e['scope'] for e in expected_train] or
                test != [e['scope'] for e in expected_test]):
            raise ValueError('promotion_split_differs_from_training_protocol')
        rows = [row for scope in test for row in by_scope[scope]]
        metrics = pairwise_accuracy([forward(model['parameters'],r['values']) for r in rows],
                                    [r['target'] for r in rows])
        labels = sorted({r['target'] for rows in by_scope.values() for r in rows})
        reason = ('promotion_constant_outcome_targets' if len(labels)<2 else
                  'promotion_insufficient_heldout_pairs' if metrics['pairs']<PROMOTION_MIN_PAIRS else
                  'promotion_accuracy_below_threshold')
        result.update(metrics,held_out_rows=len(rows),trained_scopes=train,held_out_scopes=test,
                      label_values=labels,reason=reason)
        if (len(labels)>1 and metrics['pairs']>=PROMOTION_MIN_PAIRS and
                metrics['pairwise_accuracy'] is not None and
                metrics['pairwise_accuracy']>=PROMOTION_MIN_ACCURACY):
            result.update(eligible=True,reason='promotion_recomputed_from_bound_holdout')
        return result
    except (ValueError,TypeError,KeyError,AttributeError):
        return dict(result,reason='promotion_receipt_invalid')
