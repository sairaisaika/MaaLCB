"""One freshly identified, durable reward control; never credits payout on input."""
import re
from .reward_claim_transaction import RewardClaimTransaction
from .storage import read_json
from .vision import Text, find


def scoped_module_cap(policy, scope):
    maximum = policy.get('max_reward_modules')
    if (scope and policy.get('reward_budget_scope') == scope
            and not policy.get('module_budget_pending', True)
            and type(maximum) is int and maximum > 0):
        return maximum
    return None


#: The offers the game has actually shown on a retained frame, as (cost, weekly bonuses).
#: 6/1 and 5/0 come from the October claims; 18/3 from `pi-20261120-193352/frame-0269`,
#: a hard clear with all three weekly bonuses switched on. A pair nobody has measured
#: (12/2, say) stays refused: the list is evidence, not arithmetic.
MEASURED_OFFERS = ((6, 1), (5, 0), (18, 3))


def measured_offer(offer):
    return (isinstance(offer,dict) and offer.get('currency') == 'enkephalin_modules'
            and set(offer) == {'currency','cost','weekly'}
            and type(offer.get('cost')) is int and type(offer.get('weekly')) is int
            and (offer['cost'], offer['weekly']) in MEASURED_OFFERS)


def verified_offer(record):
    """Accept the typed output of the measured native offer reader."""
    if record.get('scene') != 'RUN_REWARD_DIALOG' or record.get('size') != [1920,1080]:
        return None
    offer = record.get('reward_cost')
    return dict(offer) if measured_offer(offer) else None


def prepare(action, record, config, scope, proof):
    if action in ('claim', 'confirm'):
        path = config/'user-mirror-settings.json'
        policy = read_json(path) if path.is_file() else {}
        maximum = scoped_module_cap(policy, scope)
        if maximum is None:
            raise ValueError('Current claim scope/budget is not authorized')
    ledger=read_json(config/'user-run-ledger.json').get('active') or {}
    if ledger.get('id')!=scope or ledger.get('floors')!=[1,2,3,4,5] or not ledger.get('victory') or ledger.get('reward'):
        raise ValueError('Current completed run is not proven')
    size=record.get('size')
    if size!=[1920,1080]:raise ValueError('Reward layout unknown')
    texts=[Text(x['text'],tuple(x['box']),x['score']) for x in record.get('ocr',[])]
    tx=RewardClaimTransaction(config/'user-reward-claim-transaction.json')
    if action=='claim':
        if record.get('scene')!='RUN_REWARD_DIALOG':raise ValueError('Current reward page missing')
        offer = verified_offer(record)
        if offer is None:
            raise ValueError('Fresh currency/cost/weekly offer differs')
        buttons=find(texts,r'^Claim$',(.62,.72,.71,.79),size,.9)
        if len(buttons)!=1:raise ValueError('Claim control missing')
        # Net Amount is a computed run-summary value, obscured by this modal; it
        # cannot stand in for a current wallet balance.
        balances=dict(modules=None,module_visibility='not_displayed_on_reward_page',
                      starlight=None,starlight_visibility='not_displayed_on_reward_page')
        tx.reserve(scope,policy,offer,balances,proof)
        tx.claim_intent(scope,offer,proof)
    elif action=='confirm':
        transaction = tx.data or {}
        reserved = transaction.get('reserved_modules')
        if (type(reserved) is not int or not 0 < reserved <= maximum
                or reserved != (transaction.get('offer') or {}).get('cost')):
            raise ValueError('Reserved payout exceeds or lacks current module authorization')
        scene=record.get('scene')
        if scene=='RUN_REWARD_CONFIRM':
            question=find(texts,r'^Claim the rewards\?$',(.35,.42,.65,.56),size,.9)
            proven=(len(question)==1 and tx.data is not None
                    and tx.data.get('offer',{}).get('weekly')==0)
        elif scene=='RUN_REWARD_BONUS':
            lines=find(texts,r'.+',(.32,.44,.68,.53),size,.9)
            joined=' '.join(t.text for t in sorted(lines,key=lambda t:(t.box[1],t.box[0])))
            normalized=re.sub(r"['’]",'',joined)
            proven=normalized=='Spend your Weekly Bonuses, to claim the bonus rewards?'
            # The question does not say how many bonuses it spends; the reserved offer
            # does, and it was read from the dialog this question follows.
            proven=proven and tx.data is not None and tx.data.get('offer',{}).get('weekly') in (1,3)
        else:raise ValueError('Exact reward confirmation missing')
        cancel=find(texts,r'^(?:[x×✕]\s*)?Cancel$',(.34,.64,.46,.73),size,.9)
        buttons=find(texts,r'^Confirm$',(.56,.64,.66,.73),size,.9)
        if not proven or len(cancel)!=1 or len(buttons)!=1:
            raise ValueError('Reward confirmation question/buttons incomplete')
        tx.confirm_intent(scope,proof,question_proven=True)
    elif action=='receipt':
        if (not tx.data or tx.data.get('scope')!=scope or not tx.data.get('confirm_sent')
                or tx.data.get('receipt_ack_sent')):
            raise ValueError('Reward receipt intent absent or repeated')
        heading=find(texts,r'^Rewards Acquired$',(.39,.30,.61,.39),size,.9)
        amount=find(texts,r'^[1-9]\d{0,5}$',(.47,.48,.54,.56),size,.9)
        buttons=find(texts,r'^Confirm$',(.43,.60,.58,.70),size,.9)
        if len(heading)!=1 or len(amount)!=1 or len(buttons)!=1:
            raise ValueError('Actual acquired-reward receipt incomplete')
        from .storage import write_json
        tx.data.update(receipt_ack_sent=True,receipt_proof=str(proof),
                       pending='receipt_ack',receipt_visible_amount=int(amount[0].text))
        write_json(tx.path,tx.data)
    elif action=='pass':
        if (not tx.data or tx.data.get('scope')!=scope or not tx.data.get('confirm_sent')
                or not tx.data.get('receipt_ack_sent')
                or tx.data.get('pass_ack_sent')):
            raise ValueError('Pass receipt absent or repeated')
        headings=[(r'^Pass Level Up$',(.40,.30,.61,.39)),
                  (r'^Pass Level$',(.29,.42,.38,.47)),
                  (r'^Battle Pass XP$',(.39,.42,.57,.49))]
        levels=find(texts,r'^\d+$',(.29,.45,.38,.57),size,.9)
        buttons=find(texts,r'^Confirm$',(.43,.60,.58,.70),size,.9)
        if any(len(find(texts,p,band,size,.9))!=1 for p,band in headings) or len(levels)!=1 or len(buttons)!=1:
            raise ValueError('Actual pass receipt incomplete')
        from .storage import write_json
        tx.data.update(pass_ack_sent=True,pass_receipt_proof=str(proof),
                       pending='pass_ack',pass_level=int(levels[0].text))
        write_json(tx.path,tx.data)
    else:
        raise ValueError('Unknown paid reward action')
    return list(buttons[0].box)
