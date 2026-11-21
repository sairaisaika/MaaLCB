"""Preview an audited offline value candidate without authorizing purchase input."""
import hashlib,math
from pathlib import Path
from .storage import read_json


def rank_preview(offers,context,root):
    trace=dict(neural_value_shadow_applied=False,buy_learning_applied=False,
               reason='purchase_value_model_missing_rule_fallback')
    root=Path(root);weights=root/'weights.json';card=root/'modelcard.json'
    if not weights.is_file() or not card.is_file():return list(offers),trace
    try:
        metadata=read_json(card);model=read_json(weights)
        sha=hashlib.sha256(weights.read_bytes()).hexdigest()
        if (metadata.get('weights_sha256')!=sha or metadata.get('synthetic') is not False
                or metadata.get('production_enabled') is not False
                or metadata.get('evidence_verified') is not True
                or type(metadata.get('reviewed_episodes')) is not int
                or metadata['reviewed_episodes']<1 or model.get('schema_version')!=1
                or model.get('production_enabled') is not False):
            raise ValueError('Shop value candidate provenance not verified')
        # The offline encoder is shared; it never supplies input or a policy cap.
        from .shop_value_training import encode_observation,feature_names,forward
        from .shop_value_training import _verification_digest,VERIFICATION_SCHEMA,VERIFICATION_SOURCE
        verification=metadata.get('verification') or {}
        digest=_verification_digest(verification.get('episodes') or [])
        if (verification.get('schema_version')!=VERIFICATION_SCHEMA or verification.get('source')!=VERIFICATION_SOURCE
                or verification.get('verified') is not True
                or verification.get('verified_episodes')!=metadata['reviewed_episodes']
                or digest!=verification.get('dataset_sha256') or digest!=metadata.get('dataset_sha256')
                or digest!=model.get('dataset_sha256')):
            raise ValueError('Shop value dataset manifest differs')
        vocabulary=model['vocabulary'];keywords=model['keyword_vocabulary']
        if any(not isinstance(items,list) or any(not isinstance(v,str) or not v for v in items)
               or len(set(items))!=len(items) for items in (vocabulary,keywords)):
            raise ValueError('Shop value vocabulary differs')
        expected=list(feature_names(vocabulary,keywords))
        if expected!=model['feature_names'] or not 1<=len(expected)<=512:
            raise ValueError('Shop value feature schema differs')
        p=model['parameters'];hidden=model['hidden'];width=len(expected)
        if (type(hidden) is not int or not 1<=hidden<=32 or len(p['w1'])!=hidden
                or len(p['b1'])!=hidden or len(p['w2'])!=hidden
                or any(len(row)!=width for row in p['w1'])):
            raise ValueError('Shop value network shape differs')
        values=[p['b2'],*p['b1'],*p['w2'],*[x for row in p['w1'] for x in row]]
        if any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>100 for x in values):
            raise ValueError('Shop value network contains invalid weights')
        from .shop_value_promotion import evaluate
        promotion=evaluate(model,verification)
        scores=[]
        for index,offer in enumerate(offers):
            observation=dict(context,action='buy',offer_name=offer.name,price=offer.price)
            vector=encode_observation(observation,vocabulary=vocabulary,keyword_vocabulary=keywords)['values']
            score=forward(p,vector)
            scores.append(dict(name=offer.name,price=offer.price,index=index,predicted_review_value=score))
        ranked=metadata.get('participation')=='ranked' and promotion['eligible']
        if ranked:
            order=sorted(range(len(offers)),key=lambda index:(-scores[index]['predicted_review_value'],index))
            ordered=[offers[index] for index in order]
        else:
            ordered=list(offers)
        return ordered,dict(trace,neural_value_shadow_applied=True,neural_value_ranked=ranked,
            buy_learning_applied=ranked,purchase_input_authorized=False,
            participation='ranked' if ranked else 'shadow',
            requested_participation=metadata.get('participation'),
            reviewed_episodes=metadata.get('reviewed_episodes'),
            held_out=promotion,promotion=promotion,model_sha256=sha,scores=scores,
            reason=('candidate_promoted_by_its_own_held_out_ordering_within_the_plans_offers' if ranked
                    else promotion['reason'] if metadata.get('participation')=='ranked'
                    else 'candidate_shadow_only_not_a_promoted_purchase_policy'))
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
        return list(offers),dict(trace,reason='invalid_value_candidate_rule_fallback',diagnostic=str(error))


def diagnostic(root):
    """Run the installed scorer on one hypothetical offer, without any device.

    This certifies neither a live quote nor learned purchasing quality. Keep raw
    dataset scope IDs/review content out of the self-test's diagnostic output.
    """
    from types import SimpleNamespace
    _,trace=rank_preview([SimpleNamespace(name='Prestige Card',price=100)],
                         dict(coins=1000,reserve_coins=0),root)
    return dict(scope='hypothetical_readonly_offer_not_a_live_purchase_quote',
        game_input=False,purchase_input_authorized=False,
        prediction_executed=bool(trace.get('scores')),
        neural_value_ranked=trace.get('neural_value_ranked',False),
        model_sha256=trace.get('model_sha256'),reason=trace['reason'],
        scores=trace.get('scores',[]),
        held_out_pairs=(trace.get('promotion') or {}).get('pairs'),
        held_out_accuracy=(trace.get('promotion') or {}).get('pairwise_accuracy'))
