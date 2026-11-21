"""Shop policy examples: verified actions and delayed outcomes, never fake strength.

Maa owns perception and input. This Agent-side dataset joins its native evidence
by run scope. A purchased badge labels execution, not a beneficial purchase.
"""
import copy,hashlib,json,shutil,os,tempfile
import re
from datetime import datetime
from pathlib import Path
from .storage import read_json,write_json
from .shop_transaction import _verify,_coins,_shelf,purchase_execution_witness
from .shop_review_state import merge_outcome
from .workspace import reserve_output


def refresh_scope(config,scope,*,trigger,journal=None):
    """Collect delayed labels after durable run events, without a game action.

    Read exactly this run's purchase transaction, including after it was archived.
    Optional learning failures cannot undo a settled floor, payout or rotation.
    A later explicit launch retries from the same retained facts; no extra queue
    or duplicated completion authority is introduced.
    """
    result=dict(trigger=trigger,samples=0,automatic_labels_ready=0,
                manual_labels_preserved=0,input_sent=False,neural_policy_applied=False)
    try:
        if not isinstance(scope,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',scope):
            raise ValueError('Invalid purchase outcome scope')
        config=Path(config)
        path=config/f'user-shop-{scope}.json'
        if not path.exists():
            return dict(result,status='absent',reason='no_purchase_transaction')
        from .shop_transaction import ShopTransaction
        transaction=ShopTransaction(path)
        if not transaction.data or transaction.data['scope']!=scope:
            raise ValueError('Purchase outcome transaction scope differs')
        if not transaction.data['bought']:
            return dict(result,status='absent',reason='no_verified_purchases')
        samples=sync(transaction,config.parent/'build/learning-review/shop-purchases',
                     config/'user-run-ledger.json')
        result.update(status='collected',samples=len(samples),
            automatic_labels_ready=sum(s.get('automatic_label',{}).get('status')=='ready' for s in samples),
            manual_labels_preserved=sum(s.get('automatic_label',{}).get('status')=='preserved' for s in samples),
            reason='verified_delayed_labels_collected_training_and_promotion_are_separate')
    except Exception as error:
        result.update(status='pending',reason='delayed_purchase_labels_unavailable',
                      error_type=type(error).__name__,error=str(error)[:500])
    if journal is not None:
        try:
            journal.record('shop_purchase_learning_samples',**result)
        except Exception:
            # The settled run is authoritative even if its optional learning log
            # cannot be written. Return the status to the caller's result too.
            result['journal_unavailable']=True
    return result


def _copy_evidence(origin,target,expected):
    fd,temporary=tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(origin,temporary)
        with open(temporary,'rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=expected:
                raise ValueError('Source evidence changed during copy')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
                raise ValueError('Review evidence appeared during copy; preserved')
            return
        os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def sync(transaction,root,ledger=None):
    data=transaction.data or {};root=Path(root);root.mkdir(parents=True,exist_ok=True)
    run=None;state=None
    if ledger:
        state=read_json(ledger)
        if state.get('version')!=1:raise ValueError('Shop outcome ledger version differs')
        from .shop_value_training import _ledger_runs
        runs=[r for r in _ledger_runs(state) if r.get('id')==data.get('scope')]
        if len(runs)>1:raise ValueError('Ambiguous shop outcome run')
        run=runs[0] if runs else None
    result=[]
    for receipt in data.get('bought',[]):
        before,btexts,bsize=_verify(receipt['before'])
        after,atexts,asize=_verify(receipt['successor'])
        coins=_coins(btexts,bsize);price=receipt['price']
        prior=_shelf(btexts,bsize);following=_shelf(atexts,asize)
        if before['scene']!='SHOP' or after['scene']!='SHOP':
            raise ValueError('Shop policy purchase evidence differs')
        witness=purchase_execution_witness(prior,following,receipt['name'],price,
                                          coins,_coins(atexts,asize))
        visit=data['visits'][receipt['visit']]
        payload=dict(version=1,kind='purchase_outcome',scope=data['scope'],visit=receipt['visit'],
            name=receipt['name'],price=price,coins_before=coins,coins_after=coins-price,
            context=copy.deepcopy(receipt.get('decision_context') or visit.get('learning_context')),
            before=receipt['before'],after=receipt['successor'],question=receipt.get('question'),
            receipt_teacher='native_exact_coin_delta_complete_shelf_and_item_status',
            action_executed=True,gift_causal_strength=None)
        # Preserve content addresses of existing strict-shelf samples. Only the
        # newly supported own-badge witness needs a distinct teacher identity.
        if witness=='own_purchased_badge':
            payload['receipt_teacher']='native_exact_coin_delta_own_purchased_badge'
        key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();folder=root/key
        sample=folder/'sample.json';copies=[]
        if sample.exists() and read_json(sample)!=payload:raise ValueError('Immutable purchase sample changed')
        from .shop_evidence import descriptor,reference_root
        storage=folder/'evidence-storage.json'
        declaration=descriptor(folder,payload,key) if not sample.exists() else None
        canonical=bool(declaration or storage.exists())
        if storage.exists():reference_root(folder,payload)
        for role,proof in [('before',receipt['before']),('after',receipt['successor']),
                           ('question',receipt.get('question')),
                           ('notice',(receipt.get('overlay_acknowledgement') or {}).get('frame'))]:
            if not proof:continue
            _verify(proof)
            for suffix,hashfield in [('.json','json_sha256'),('.png','png_sha256')]:
                origin=Path(proof['path']).with_suffix(suffix);target=folder/(role+suffix)
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=proof[hashfield]:
                    raise ValueError('Shop policy review bytes changed')
                if not target.exists() and not canonical:copies.append((origin,target,proof[hashfield]))
        review=folder/'review.json'
        if review.exists() and not isinstance(read_json(review),dict):
            raise ValueError('Unknown purchase review state preserved')
        outcomes=[]
        if run:
            for event in run.get('events',{}).values():
                if event.get('kind') not in ('floor_clear','final_victory','reward_received','entry_returned'):continue
                path=Path(event['evidence'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=event['sha256']:
                    raise ValueError('Delayed shop outcome proof changed')
                record=read_json(path);png=path.with_suffix('.png')
                if hashlib.sha256(png.read_bytes()).hexdigest()!=record.get('image_sha256'):
                    raise ValueError('Delayed shop outcome image changed')
                # Earlier floors/old history never become consequences of this purchase.
                if not before.get('utc') or not record.get('utc'):continue
                before_time=datetime.fromisoformat(before['utc']);event_time=datetime.fromisoformat(record['utc'])
                if before_time.tzinfo is None or event_time.tzinfo is None:
                    raise ValueError('Timezone-bound shop outcome required')
                if event_time<=before_time:continue
                for origin,expected in [(path,event['sha256']),(png,record['image_sha256'])]:
                    target=folder/('outcome-'+event['sha256']+origin.suffix)
                    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
                        raise ValueError('Delayed outcome review evidence changed')
                    if not target.exists() and not canonical:copies.append((origin,target,expected))
                outcomes.append(dict(kind=event['kind'],floor=event.get('floor'),evidence=event,
                    image_sha256=record['image_sha256']))
        label=dict(version=1,category='purchase_completed_outcome_pending' if not outcomes else
                   'purchase_completed_with_later_run_observations',outcomes=outcomes,
                   objective='observed_run_return_not_causal_gift_strength',human_approved=False,
                   training_eligible=False,reason='context_and_independent_episode_quality_review_required')
        target=folder/'outcome.json'
        previous=read_json(target) if target.exists() else None
        label=merge_outcome(previous,label,observations_available=run is not None)
        trace=('Scope: '+data['scope']+'\nGift: '+receipt['name']+
            '\nVerified spend: '+str(price)+'\nDelayed outcome count: '+str(len(outcomes))+
            '\nPurchase execution is not purchase value.\n')
        trace_path=folder/'trace.log'
        trace_changed=not trace_path.exists() or trace_path.read_text(encoding='utf8')!=trace
        metadata=(len(json.dumps(payload,ensure_ascii=False).encode('utf8'))*2 if not sample.exists() else 0)
        metadata+=len(json.dumps(declaration).encode('utf8'))*2 if declaration else 0
        metadata+=(len(json.dumps(label,ensure_ascii=False).encode('utf8'))*2 if label!=previous else 0)
        metadata+=512 if not review.exists() else 0
        metadata+=len(trace.encode('utf8'))*2 if trace_changed else 0
        if copies or metadata:
            reserve_output(folder,sum(origin.stat().st_size for origin,_,_ in copies)+metadata+65536)
        folder.mkdir(exist_ok=True)
        if declaration:write_json(storage,declaration)
        if not sample.exists():write_json(sample,payload)
        for origin,destination,expected in copies:_copy_evidence(origin,destination,expected)
        if not review.exists():write_json(review,dict(status='pending',notes='',corrected_category=None))
        if label!=previous:write_json(target,label)
        if trace_changed:trace_path.write_text(trace,encoding='utf-8')
        automatic=dict(status='pending',reason='delayed_outcome_ledger_unavailable')
        if state is not None:
            try:
                from .shop_value_training import review_sample
                derived,problem=review_sample(folder,ledger=state)
                automatic=(dict(status='ready',benefit=derived['benefit']) if derived is not None else
                    dict(status='preserved' if problem.startswith('human_') else 'pending',reason=problem))
            except Exception as error:
                # This optional teacher cannot invalidate a proven game action.
                # Keep its failure visible, leave the review and continue rules.
                automatic=dict(status='pending',reason='automatic_review_unavailable',error_type=type(error).__name__)
        label=read_json(target)
        if read_json(review).get('status')!='rejected':
            result.append(dict(sample=str(sample),**label,automatic_label=automatic))
    return result
