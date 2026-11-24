"""One freshly identified, durable reward control; never credits payout on input."""
import re
from .reward_claim_transaction import RewardClaimTransaction
from .storage import read_json
from .vision import Text, find


def scoped_module_cap(policy, scope):
    """The most modules this run's reward may cost, or None when nothing allows a claim.

    An answer given for this very run stands, a refusal included. For a run nobody
    answered for, the Mirror task's standing setting applies (`auto_claim_modules`).
    """
    if not scope:
        return None
    maximum = policy.get('max_reward_modules')
    if policy.get('reward_budget_scope') == scope:
        if not policy.get('module_budget_pending', True) and type(maximum) is int and maximum > 0:
            return maximum
        return None
    standing = policy.get('auto_claim_modules')
    return standing if type(standing) is int and standing > 0 else None


def lost_claim_allowed(policy):
    """Whether the user chose to claim a lost run's partial rewards (``reward_task_budget``)."""
    return policy.get('auto_claim_lost_runs') is True


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


#: Where the Mirror entry page prints the two balances a payout changes, and where the
#: reward dialog prints what it pays. Measured on pi-20261123-182337: frame-0004 (the
#: dialog reopened from the dungeon list: starlight 3220, cap 50/1000, offering 65 and
#: x50) and frame-0009 (the pass popup over the entry page: 3285 and 100/1000).
ENTRY_STARLIGHT = (r'^[^0-9]{0,2}(\d{1,6})$', (.84, .11, .94, .20))
ENTRY_CAP = (r'^(\d{1,4})/1000$', (.85, .365, .94, .42))
OFFER_STARLIGHT = (r'^(\d{1,5})$', (.36, .61, .42, .68))
OFFER_PROJECTION = (r'^[x×](\d{1,4})$', (.70, .56, .79, .65))


def _number(record, rule):
    texts = [Text(x['text'], tuple(x['box']), x['score']) for x in record.get('ocr', [])]
    hits = find(texts, rule[0], rule[1], record['size'], .8)
    if len(hits) != 1:
        return None
    return int(re.search(rule[0], hits[0].text.strip(), re.I)[1])


def entry_balance_receipt(claim_record, after_record):
    """Proof that a payout arrived where the game shows no "Rewards Acquired" page.

    A dialog reopened from the dungeon list pays straight onto the entry page: after
    Confirm the next thing on screen is the pass popup (or the entry page itself), and
    the receipt page of the other route never appears (pi-20261123-182337). What can be
    read instead is stronger than a caption: the entry page's starlight and weekly cap
    before the claim, the two amounts the dialog offered, and the same two balances
    afterwards. Both must have grown by exactly what was offered. Any number that is
    missing or ambiguous, or a difference that is not the offer, proves nothing.
    """
    if claim_record.get('size') != [1920, 1080] or after_record.get('size') != [1920, 1080]:
        return None
    values = dict(starlight_before=_number(claim_record, ENTRY_STARLIGHT),
                  cap_before=_number(claim_record, ENTRY_CAP),
                  starlight_offer=_number(claim_record, OFFER_STARLIGHT),
                  projection_offer=_number(claim_record, OFFER_PROJECTION),
                  starlight_after=_number(after_record, ENTRY_STARLIGHT),
                  cap_after=_number(after_record, ENTRY_CAP))
    if any(value is None for value in values.values()):
        return None
    if values['starlight_offer'] <= 0 or values['projection_offer'] <= 0:
        return None
    if (values['starlight_after'] - values['starlight_before'] != values['starlight_offer']
            or values['cap_after'] - values['cap_before'] != values['projection_offer']):
        return None
    return values


#: The run summary's own Starlight amount, the big number in its right column
#: (pi-20261123-235849/frame-0006: `40` at [1592,456,76,74]).
SUMMARY_STARLIGHT = (r'^(\d{1,5})$', (.81, .40, .89, .51))


def summary_pass_receipt(claim_record, after_record, outcome=None):
    """Proof that a payout arrived onto the run summary, where the game shows no receipt page.

    First measured for a lost run; the next cleared run (pi-20261124-022413, 100%, offer
    74 and summary 74) paid the same way: Claim, the Confirm, then the pass popup over
    the summary and no "Rewards Acquired" page. ``outcome`` binds the summary to what
    the ledger says: below 100% for ``'lost'``, exactly 100% for ``'won'``; without it
    (the final audit, which has the ledger's verdict from elsewhere) any percentage reads.

    Measured on pi-20261123-235849: a run lost at 95% was claimed (Claim, then the
    "Claim the rewards?" Confirm) and the next page was the pass popup over the run
    summary; no "Rewards Acquired" page came. The pass popup is itself what the payout
    did, and the page under it ties it to this run: it is still the summary below 100%,
    and the Starlight amount the summary prints is the amount the dialog offered.
    """
    if claim_record.get('size') != [1920, 1080] or after_record.get('size') != [1920, 1080]:
        return None
    from .dungeon_progress import exploration_summary
    texts = [Text(x['text'], tuple(x['box']), x['score']) for x in after_record.get('ocr', [])]
    summary = exploration_summary(texts, (1920, 1080)) or {}
    percent = summary.get('total_percent')
    offered, printed = _number(claim_record, OFFER_STARLIGHT), _number(after_record, SUMMARY_STARLIGHT)
    if type(percent) is not int or not 0 <= percent <= 100:
        return None
    if (outcome == 'lost' and percent == 100) or (outcome == 'won' and percent != 100):
        return None
    if offered is None or offered <= 0 or printed != offered:
        return None
    return dict(starlight_offer=offered, summary_starlight=printed, total_percent=percent)


def prepare(action, record, config, scope, proof):
    if action in ('claim', 'confirm'):
        path = config/'user-mirror-settings.json'
        policy = read_json(path) if path.is_file() else {}
        maximum = scoped_module_cap(policy, scope)
        if maximum is None:
            raise ValueError('Current claim scope/budget is not authorized')
        # The transaction reserves against a budget bound to this run. A standing limit
        # is bound here, in memory, at the moment it is used; the saved file keeps it standing.
        policy = dict(policy, reward_budget_scope=scope, max_reward_modules=maximum,
                      module_budget_pending=False)
    ledger=read_json(config/'user-run-ledger.json').get('active') or {}
    from .run_wiring import payout_state
    outcome=payout_state(ledger)
    if ledger.get('id')!=scope or outcome is None or ledger.get('reward'):
        raise ValueError('Current completed run is not proven')
    if outcome=='lost' and action in ('claim','confirm'):
        saved=read_json(config/'user-mirror-settings.json') if (config/'user-mirror-settings.json').is_file() else {}
        if not lost_claim_allowed(saved):
            raise ValueError('Claiming a lost run was not chosen')
    size=record.get('size')
    if size!=[1920,1080]:raise ValueError('Reward layout unknown')
    texts=[Text(x['text'],tuple(x['box']),x['score']) for x in record.get('ocr',[])]
    tx=RewardClaimTransaction(config/'user-reward-claim-transaction.json')
    if action=='claim':
        if record.get('scene')!='RUN_REWARD_DIALOG':raise ValueError('Current reward page missing')
        offer = verified_offer(record)
        if offer is None:
            raise ValueError('Fresh currency/cost/weekly offer differs')
        if outcome=='lost' and offer['weekly']!=0:
            # A weekly bonus is only ever spent on a run that earned its payout.
            raise ValueError('A lost run does not spend weekly bonuses')
        # The dialog prints the floor the run ended on and how far it got there. It has
        # to tell the ledger's story: a cleared floor 5 for a won run, anything short of
        # it for a lost one. Otherwise this is some other run's dialog.
        from .reward_cost import floor_count
        count=floor_count(texts,size)
        cleared=count is not None and count[0]==5 and count[1]==count[2]
        # A lost run must show its unfinished floor. A won run is refused only when the
        # dialog plainly shows an unfinished one: the offer reader already asked for the
        # count when it read the cost, and a count hidden on this frame denies nothing.
        if (outcome=='lost' and (count is None or cleared)) or (outcome=='won' and count is not None and not cleared):
            raise ValueError('The reward dialog disagrees with the ledger about how the run ended')
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
                or tx.data.get('pass_ack_sent')):
            raise ValueError('Pass receipt absent or repeated')
        receipt={}
        if not tx.data.get('receipt_ack_sent'):
            # No receipt page was acknowledged: only the route that pays onto the entry
            # page may go on, and only on the balances that prove it paid.
            from pathlib import Path
            try:claim_record=read_json(Path(tx.data['claim_proof']))
            except (KeyError,OSError,ValueError):claim_record={}
            balances=entry_balance_receipt(claim_record,record)
            kind='entry_balances'
            if balances is None:
                # The payout landed on the run's own summary; see summary_pass_receipt.
                balances=summary_pass_receipt(claim_record,record,outcome)
                kind='summary_pass_popup'
            if balances is None:
                raise ValueError('Pass receipt absent or repeated')
            receipt=dict(receipt_ack_sent=True,receipt_kind=kind,receipt_proof=str(proof),
                         receipt_visible_amount=balances['starlight_offer'],receipt_balances=balances)
        headings=[(r'^Pass Level Up$',(.40,.30,.61,.39)),
                  (r'^Pass Level$',(.29,.42,.38,.47)),
                  (r'^Battle Pass XP$',(.39,.42,.57,.49))]
        levels=find(texts,r'^\d+$',(.29,.45,.38,.57),size,.9)
        buttons=find(texts,r'^Confirm$',(.43,.60,.58,.70),size,.9)
        if any(len(find(texts,p,band,size,.9))!=1 for p,band in headings) or len(levels)!=1 or len(buttons)!=1:
            raise ValueError('Actual pass receipt incomplete')
        from .storage import write_json
        tx.data.update(receipt,pass_ack_sent=True,pass_receipt_proof=str(proof),
                       pending='pass_ack',pass_level=int(levels[0].text))
        write_json(tx.path,tx.data)
    else:
        raise ValueError('Unknown paid reward action')
    return list(buttons[0].box)
