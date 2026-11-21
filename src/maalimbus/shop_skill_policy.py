"""Price and deck-count rules for in-run skill replacement proposals."""
from dataclasses import dataclass

from .shop_skill_vision import ReplacementQuote


SKILL_MODES = ('off', 'keep_one_each', 'keep_one_s2')
_MINIMUM_COPIES = {'keep_one_each': (1, 1), 'keep_one_s2': (0, 1)}


def choose_skill_service(offers, coins, reserve_coins, deployment, scope, attempted, blocked):
    """Find a named affordable service for an independently observed frontliner."""
    from .pre_battle_identity import submitted_identity

    if coins is None or coins <= reserve_coins or not deployment:
        return None
    excluded = {name.casefold() for name in blocked}
    for offer in offers:
        sinner = offer['sinner']
        if offer['name'].casefold() in excluded or sinner in attempted:
            continue
        identity = submitted_identity(deployment, scope, sinner)
        if identity and identity['role'] == 'frontline':
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

    minimum_s1, minimum_s2 = _MINIMUM_COPIES[mode]
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
