"""Explicit native rewards-task budget, bound only to a verified active run."""
from pathlib import Path
from .storage import read_json,write_json


def apply(config,selection):
    if selection=='saved':return False
    if type(selection) is not int or selection not in (0,5,6):
        raise ValueError('Unknown rewards-task module budget')
    config=Path(config)
    active=read_json(config/'user-run-ledger.json').get('active') or {}
    scope=active.get('id')
    if (not isinstance(scope,str) or not scope or active.get('floors')!=[1,2,3,4,5]
            or active.get('victory') is not True or active.get('reward') is not False):
        raise ValueError('Budget requires the current verified, unpaid five-floor run')
    path=config/'user-mirror-settings.json'
    policy=read_json(path)
    if not isinstance(policy,dict):raise ValueError('Invalid saved resource policy')
    txpath=config/'user-reward-claim-transaction.json'
    if txpath.exists():
        tx=read_json(txpath)
        if (tx.get('pending') is not None or
                tx.get('scope')==scope and tx.get('claim_sent')):
            raise ValueError('Do not change a budget after a claim intent or unresolved transaction')
        if tx.get('scope')!=scope and tx.get('completed') is not True:
            raise ValueError('Previous reward transaction is incomplete')
    proposed=dict(policy,reward_budget_scope=scope,max_reward_modules=selection,
                  module_budget_pending=selection==0)
    if proposed==policy:return False
    write_json(path,proposed)
    return True


#: The standing limit the Mirror task's own setting writes: the most modules a reward
#: offer may cost for the task to claim it by itself, for whichever run finishes next.
STANDING = 'auto_claim_modules'
#: What the setting offers: claim, or stop on the reward page. "saved" is what a pipeline
#: built before the setting existed carries.
STANDING_CHOICES = ('claim', 'off')


def apply_standing(config,selection):
    """Save the Mirror task's "claim after a clear" choice; return what was done.

    A run's rewards cost 5 modules, or 6 or 18 when the player has switched weekly
    bonuses on in the game; that switch is the player's, so "claim" allows whichever of
    the measured offers the dialog shows (the user, 2026-11-23: the only question is
    whether to claim). "off" removes the standing limit, so a clear stops on the reward
    page. `saved` keeps what is stored. A claim that has already been
    reserved or sent keeps the limit it was reserved under: the choice is not written
    while that transaction is open, so the task can still finish it.
    """
    if selection=='saved':return 'kept'
    if selection not in STANDING_CHOICES:
        raise ValueError('Unknown automatic reward claim choice')
    from .paid_reward_action import MEASURED_OFFERS
    limit=max(cost for cost,_weekly in MEASURED_OFFERS) if selection=='claim' else 0
    config=Path(config)
    path=config/'user-mirror-settings.json'
    policy=read_json(path) if path.exists() else {}
    if not isinstance(policy,dict):raise ValueError('Invalid saved resource policy')
    txpath=config/'user-reward-claim-transaction.json'
    if txpath.exists() and read_json(txpath).get('pending') is not None:
        return 'kept_while_a_claim_is_open'
    proposed=dict(policy)
    if limit:proposed[STANDING]=limit
    else:proposed.pop(STANDING,None)
    if proposed==policy:return 'unchanged'
    write_json(path,proposed)
    return 'saved'
