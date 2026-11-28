"""Price and deck-count rules for in-run skill replacement proposals."""
from dataclasses import dataclass

from .shop_skill_vision import ReplacementQuote


#: Whose skills may be replaced: the initial front row only, or every deployed identity
#: (the front row and the backups). Which copies must stay: at least one tier 1, at least
#: one tier 2, both, or none. A mode names both: `front_keep_s2`, `all_keep_s1s2`, ...
#: The settings offer them as a switch, a choice of whose skills and two checkboxes
#: (asked for by the user on 2026-11-28: eight combinations in one dropdown read badly).
WHO = ('front', 'all')
KEEP = ('s1s2', 's2', 's1', 'none')
#: The two modes the settings offered before 2026-11-28, both for the front row.
LEGACY = {'keep_one_each': 'front_keep_s1s2', 'keep_one_s2': 'front_keep_s2'}
SKILL_MODES = ('off',) + tuple(LEGACY) + tuple('%s_keep_%s' % (who, keep) for who in WHO for keep in KEEP)
ROLES = {'front': ('frontline',), 'all': ('frontline', 'backup')}


def mode_of(who, keep_s1, keep_s2):
    """The mode for a choice of whose skills and the two "keep one" boxes."""
    if who not in WHO or type(keep_s1) is not bool or type(keep_s2) is not bool:
        raise ValueError('Unknown shop skill policy')
    keep = {(True, True): 's1s2', (False, True): 's2', (True, False): 's1', (False, False): 'none'}[(keep_s1, keep_s2)]
    return '%s_keep_%s' % (who, keep)


def _parts(mode):
    if mode not in SKILL_MODES or mode == 'off':
        raise ValueError('Invalid skill replacement policy or reserve')
    who, keep = LEGACY.get(mode, mode).split('_keep_')
    return who, keep


def minimums(mode):
    """`(tier 1, tier 2)` copies each identity must keep under `mode`."""
    keep = _parts(mode)[1]
    return int(keep in ('s1s2', 's1')), int(keep in ('s1s2', 's2'))


def eligible(mode, role):
    """Whether an identity deployed in `role` may have a skill replaced under `mode`."""
    if mode == 'off' or mode not in SKILL_MODES:
        return False
    return role in ROLES[_parts(mode)[0]]


def choose_skill_service(offers, coins, reserve_coins, deployment, scope, attempted, blocked, mode='keep_one_each'):
    """Find a named affordable service for an independently observed identity `mode` covers."""
    from .pre_battle_identity import submitted_identity

    if coins is None or coins <= reserve_coins or not deployment or mode == 'off':
        return None
    excluded = {name.casefold() for name in blocked}
    for offer in offers:
        sinner = offer['sinner']
        if offer['name'].casefold() in excluded or sinner in attempted:
            continue
        identity = submitted_identity(deployment, scope, sinner)
        if identity and eligible(mode, identity['role']):
            return offer
    return None


@dataclass(frozen=True)
class SkillReplacement:
    quote: ReplacementQuote
    counts_after: tuple[int, int, int]
    coins_after: int


def propose_replacement(modal, mode, reserve_coins):
    """Propose the cheapest verified S3 gain that preserves the selected copies.

    The caller still owns identity/lineup binding and input authorization. The
    returned balances and counts are predictions for a later independent receipt.
    """
    if mode not in SKILL_MODES or type(reserve_coins) is not int or reserve_coins < 0:
        raise ValueError('Invalid skill replacement policy or reserve')
    if mode == 'off' or modal.balance is None:
        return None

    minimum_s1, minimum_s2 = minimums(mode)
    proposals = []
    for quote in modal.quotes:
        if (quote.to_tier != 3 or quote.from_tier not in (1, 2)
                or not quote.tiers_verified or quote.price is None or quote.price <= 0):
            continue
        coins_after = modal.balance - quote.price
        if coins_after < reserve_coins:
            continue
        s1, s2, s3 = modal.counts
        s1 -= int(quote.from_tier == 1)
        s2 -= int(quote.from_tier == 2)
        if s1 < minimum_s1 or s2 < minimum_s2:
            continue
        proposals.append(SkillReplacement(quote, (s1, s2, s3 + 1), coins_after))
    return min(proposals, key=lambda proposal: proposal.quote.price, default=None)
