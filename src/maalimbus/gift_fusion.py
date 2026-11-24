"""What a Mirror Dungeon shop's "Fuse Gifts" can do for a run, as plain decisions.

The shop fuses two or more owned E.G.O Gifts into one. There are two kinds:

* a **recipe**: a fixed set of gifts yields one fixed gift that no shop, encounter or
  other fusion gives (``assets/resource/base/gift-fusion-recipes.json``, imported by
  ``tools/import_wiki_fusion_recipes.py`` with the wiki revision it came from);
* anything else is a **random** fusion: the player names a keyword first, and the
  result is a random non-recipe gift that has that keyword with a chance that grows
  with the number of gifts put in.

The numbers below are the ones the wiki page "Mirror Dungeon" states in its section
"Gift Fusion Details" (revision 202689, read 2026-11-24). They are the wiki's reading
of the game, not something this project measured; ``tests/test_gift_fusion.py`` pins
them so a change is a decision, not an accident.

This module decides and explains. It sends no input and reads no screen: the fusion
pages get their own reader once they have been observed live.
"""
import difflib
import json
import re

FILE = 'gift-fusion-recipes.json'
#: The seven status systems a team is built around (the keyword half of the table).
SYSTEMS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge')
#: Keywords the fusion page lets the player ask for; the damage types have no recipes.
KEYWORDS = SYSTEMS + ('Slash', 'Pierce', 'Blunt')

#: Fusion points per gift tier.
POINTS = {1: 3, 2: 6, 3: 10, 4: 15, 5: 30}
#: Lowest point sum for a result tier, best first; below the last one the result is tier I.
TIER_FROM = ((25, 4), (17, 3), (11, 2))
SUPER_SHOP_TIER_FROM = ((22, 4), (15, 3), (10, 2))
#: Chance that a random fusion of N gifts has the keyword asked for.
KEYWORD_CHANCE = {2: .60, 3: .90}
KEYWORD_CHANCE_MANY = .99
#: The same with "Wishmaking", which costs Starlight on every attempt.
WISH_CHANCE = {2: .90, 3: .99}
WISH_CHANCE_MANY = .9999
WISH_STARLIGHT = 5


def fold(name):
    """A gift name as OCR and data files can agree on it."""
    return re.sub(r'[^\w]', '', str(name).casefold())


def result_tier(tiers, *, super_shop=False):
    """The tier a fusion of gifts with these tiers yields."""
    tiers = list(tiers)
    if len(tiers) < 2 or any(tier not in POINTS for tier in tiers):
        raise ValueError('A fusion needs two or more gifts of a known tier')
    points = sum(POINTS[tier] for tier in tiers)
    for least, tier in (SUPER_SHOP_TIER_FROM if super_shop else TIER_FROM):
        if points >= least:
            return tier
    return 1


def keyword_chance(count, *, wish=False):
    """How likely a random fusion of ``count`` gifts has the keyword asked for."""
    if count < 2:
        raise ValueError('A fusion needs two or more gifts')
    table, many = (WISH_CHANCE, WISH_CHANCE_MANY) if wish else (KEYWORD_CHANCE, KEYWORD_CHANCE_MANY)
    return table.get(count, many)


class Recipes:
    """The recipe table, with the questions a shop visit asks of it."""

    def __init__(self, data):
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('recipes'), list):
            raise ValueError('Unsupported %s' % FILE)
        source = data.get('source') or {}
        if not source.get('revid') or not source.get('license'):
            raise ValueError('%s must say which wiki revision and licence it came from' % FILE)
        self.source = source
        self.rows = []
        for row in data['recipes']:
            names = row.get('ingredients')
            if (row.get('kind') not in ('keyword', 'theme', 'super_shop') or not isinstance(row.get('result'), str)
                    or not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names)):
                raise ValueError('Malformed recipe: %r' % (row,))
            if row['kind'] == 'keyword' and row.get('group') not in SYSTEMS:
                raise ValueError('Unknown keyword group: %r' % (row,))
            if len(names) + sum(slot['count'] for slot in row.get('any_of', ())) < 2:
                raise ValueError('A recipe needs two or more gifts: %r' % (row,))
            self.rows.append(row)
        self.names = sorted({name for row in self.rows for name in self._all_names(row)})
        self._folded = {fold(name): name for name in self.names}
        if len(self._folded) != len(self.names):
            raise ValueError('Two recipe gifts differ only in punctuation')
        self.results = {row['result'] for row in self.rows}

    @staticmethod
    def _all_names(row):
        yield from row['ingredients']
        yield row['result']
        for slot in row.get('any_of', ()):
            yield from slot['names']

    def identify(self, text):
        """The recipe gift a printed title names, or ``None``.

        Exact after folding, or one clear near match: a title OCR read with a wrong
        glyph still names its gift, two candidates do not.
        """
        target = fold(text)
        if target in self._folded:
            return self._folded[target]
        if len(target) < 6:
            return None
        scored = sorted(((difflib.SequenceMatcher(None, target, key).ratio(), name)
                         for key, name in self._folded.items()), reverse=True)
        if scored[0][0] >= .9 and (len(scored) < 2 or scored[0][0] - scored[1][0] >= .05):
            return scored[0][1]
        return None

    def _owned(self, owned):
        return {self._folded[fold(name)] for name in owned if fold(name) in self._folded}

    def _missing(self, row, owned):
        """``(missing fixed names, missing wildcard slots)`` for this recipe."""
        fixed = [name for name in row['ingredients'] if name not in owned]
        slots = 0
        spare = owned - set(row['ingredients'])
        for slot in row.get('any_of', ()):
            have = [name for name in slot['names'] if name in spare]
            spare -= set(have[:slot['count']])
            slots += max(0, slot['count'] - len(have))
        return fixed, slots

    def _picked(self, row, owned):
        """The owned gifts this recipe would consume, in table order."""
        picked = list(row['ingredients'])
        spare = owned - set(picked)
        for slot in row.get('any_of', ()):
            have = [name for name in slot['names'] if name in spare][:slot['count']]
            spare -= set(have)
            picked += have
        return picked

    def wanted(self, systems):
        """The recipes a team built around ``systems`` works towards.

        A keyword recipe belongs to its system. A theme recipe belongs to the floor's
        theme pack and is wanted by any team: its result is tied to the pack, not to
        a system, and the table does not say which system it serves.
        """
        chosen = {str(system).strip().casefold() for system in systems or ()}
        return [row for row in self.rows
                if row['kind'] != 'keyword' or not chosen or row['group'].casefold() in chosen]

    def ready(self, owned, systems=(), *, super_shop=False):
        """Recipes that can be fused now, the ones that finish a chain first.

        A recipe is ready when every gift it needs is owned and its result is not.
        The recipe with more than three gifts is only offered in a super shop.
        """
        owned = self._owned(owned)
        found = []
        for row in self.wanted(systems):
            if row['result'] in owned or (row['kind'] == 'super_shop' and not super_shop):
                continue
            fixed, slots = self._missing(row, owned)
            if not fixed and not slots:
                found.append(dict(recipe=row, gifts=self._picked(row, owned), result=row['result']))
        # Two ready recipes can ask for the same gift (an umbrella and glasses make a
        # letter, and with a branch they make the letter's successor directly). The
        # recipe that uses more gifts goes first and the other is dropped: the longer
        # one reaches the end of the chain in one fusion.
        found.sort(key=lambda plan: (-len(plan['gifts']), self.rows.index(plan['recipe'])))
        used, plans = set(), []
        for plan in found:
            if used & set(plan['gifts']):
                continue
            used |= set(plan['gifts'])
            plans.append(plan)
        return plans

    def shopping(self, owned, systems=()):
        """Gifts worth buying because they complete a recipe, nearest recipe first.

        Returns rows ``dict(name, result, missing)``: ``missing`` is how many gifts the
        recipe still lacks including this one. A keyword recipe of the team's system
        counts from nothing; a theme recipe counts once one of its gifts is owned,
        because its other gifts only appear in that theme's floors.
        """
        owned = self._owned(owned)
        rows = {}
        for row in self.wanted(systems):
            if row['result'] in owned:
                continue
            fixed, slots = self._missing(row, owned)
            if row['kind'] != 'keyword' and len(fixed) == len(row['ingredients']):
                continue
            for name in fixed:
                entry = dict(name=name, result=row['result'], missing=len(fixed) + slots)
                if name not in rows or entry['missing'] < rows[name]['missing']:
                    rows[name] = entry
        return sorted(rows.values(), key=lambda entry: (entry['missing'], entry['name']))

    def reserved(self, owned, systems=()):
        """Owned gifts a random fusion must leave alone.

        Every owned recipe result (nothing else gives it back) and every owned
        ingredient of a wanted recipe whose result is still missing.
        """
        owned = self._owned(owned)
        kept = owned & self.results
        for row in self.wanted(systems):
            if row['result'] not in owned:
                kept |= set(self._picked(row, owned)) & owned
        return kept


def load(path):
    with open(path, encoding='utf-8') as handle:
        return Recipes(json.load(handle))


def random_fusion(gifts, systems, recipes, *, size=3, super_shop=False):
    """Which off-keyword gifts to trade for one gift of the team's keyword, or ``None``.

    ``gifts`` maps an owned gift's name to ``dict(keywords=[...], tier=1..5 or None)``.
    Only a gift whose keyword is known, is one the fusion page offers, and is none of
    the team's is given away: a keywordless gift usually helps any team, and a gift
    this project cannot classify is not its to spend. Recipe results and ingredients
    of a recipe still in reach stay (``Recipes.reserved``).

    The lowest tiers go first. Three gifts is the default because the wiki's numbers
    make the third gift the step from 60% to 90% for the keyword, and the fourth only
    adds nine points more.
    """
    wanted = [system for system in systems or () if system in KEYWORDS]
    if not wanted or size < 2:
        return None
    kept = recipes.reserved(gifts, systems) if recipes is not None else set()
    kept_folded = {fold(name) for name in kept}
    spare = []
    for name, fact in gifts.items():
        keywords = [keyword for keyword in fact.get('keywords') or () if keyword in KEYWORDS]
        if not keywords or set(keywords) & set(wanted) or fold(name) in kept_folded:
            continue
        spare.append((fact.get('tier') or 99, name))
    if len(spare) < size:
        return None
    chosen = [name for _, name in sorted(spare)[:size]]
    tiers = [gifts[name].get('tier') for name in chosen]
    return dict(keyword=wanted[0], gifts=chosen, chance=keyword_chance(size),
                tier=result_tier(tiers, super_shop=super_shop) if all(tiers) else None,
                reason='trading_gifts_of_other_keywords_for_one_of_the_team_keyword')
