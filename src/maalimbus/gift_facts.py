"""What is known about a gift besides its name: tier, shop cost, keyword.

The facts come from the wiki's own data table (``tools/import_wiki_gift_facts.py``,
``assets/resource/base/gift-facts.json``). Until 2026-11-25 a floor gift was chosen on
its Mounting Trial, on whether the team's system matched and on whether it was already
owned -- never on the gift itself, because the bundled catalogue only carries names,
keywords and icons. A tier IV gift and a tier I gift with the same trial were a coin
toss decided by the alphabet.

A gift the table does not know is worth nothing here. That is the honest value of
"unknown", not a penalty: the trial and ownership terms still rank it.

Since version 2 of the table the same facts answer a second question, for the shop and
for any team: *whose* gift is this. The bundled catalogue is a pinned import of 332
names; the wiki's table has 477 obtainable gifts, and a gift the catalogue lacks was
"keywordless" to the shop whatever the game files it under (live 2026-11-23: a Charge
team left a Charge gift on the shelf). `relation` reads the game's own filing, and
`worth` is the one valuation both the floor reward and the shop order by.
"""
import difflib
import functools
import json
from pathlib import Path

from .gift_vision import normalized

#: What a tier is worth when a floor gift is ranked, in the units of a Mounting Trial's
#: penalty (`floor_gifts.Trial.penalty`). Policy, not a formula. The top stays well
#: under a point of enemy Clash Power (240), so a better gift can outweigh a longer
#: fight but never a lost clash; the steps follow the game's own shop prices, whose
#: medians are about 150, 200, 250 and 400 for tiers I to IV.
TIER_VALUE = {1: 0, 2: 15, 3: 40, 4: 80, 5: 100, 'EX': 100}


@functools.lru_cache(maxsize=4)
def load(root):
    """The table under `root`, read once per process: it is a bundled, read-only file."""
    return GiftFacts(root)


#: Every answer `GiftFacts.relation` can give, and the ones in which a gift pays off.
RELATIONS = ('own', 'foreign', 'material', 'drawback', 'restricted', 'universal', 'unknown')
PAYS = frozenset(('own', 'universal'))
#: How close a printed title must be to a known name, and how far ahead of the runner-up,
#: before it is taken for that gift. The same bounds the theme pack names use.
CLOSE, MARGIN = .93, .04


class GiftFacts:
    def __init__(self, root):
        data = json.loads((Path(root) / 'gift-facts.json').read_text(encoding='utf-8'))
        if data.get('version') != 2:
            raise ValueError('Unknown gift facts version')
        self.source = data['source']
        self.by_name = {}
        for row in data['gifts']:
            key = normalized(row['name'])
            if key in self.by_name:
                raise ValueError('Two gift facts share the name %r' % row['name'])
            self.by_name[key] = row
        self._near = {}

    def of(self, name):
        """The facts of the gift this name means, or None.

        A title read off the screen, or one of the bundled catalogue's older spellings,
        can be a letter away from the name the wiki prints; a unique close match is
        that gift, and anything less is unknown.
        """
        key = normalized(name or '')
        if not key:
            return None
        if key in self.by_name:
            return self.by_name[key]
        if key not in self._near:
            # Remembered: the shop asks about the same few hundred names at every step.
            self._near[key] = self._close(key)
        return self._near[key]

    def _close(self, key):
        ranks = sorted(((difflib.SequenceMatcher(None, key, known).ratio(), known) for known in self.by_name),
                       reverse=True)[:2]
        if ranks and ranks[0][0] >= CLOSE and not (len(ranks) > 1 and ranks[0][0] - ranks[1][0] < MARGIN):
            return self.by_name[ranks[0][1]]
        return None

    def relation(self, name, keywords):
        """How the gift this name means stands to a team built on `keywords`.

        One of `RELATIONS`, decided by what the game itself says about the gift:

        * ``own`` -- filed under one of the team's keywords (a system or a damage type);
        * ``foreign`` -- filed under a keyword the team does not use. Such a gift pays
          off through that system's stacks or that damage type's skills, which this
          team does not bring; what else its text mentions does not change that;
        * ``material`` -- a Vestige: no effect, sold or fused;
        * ``drawback`` -- a liability until it changes after six wins;
        * ``restricted`` -- filed under no keyword and written for named Identities or
          a faction, which this program cannot prove are deployed;
        * ``universal`` -- filed under no keyword and written for any ally: power,
          healing, resources, the shop's own prices;
        * ``unknown`` -- the table has no such gift.

        A keywordless gift that mentions a system (five of 126 in revision 203751) does
        so as a bonus on top of an effect that needs nothing, so it stays universal.
        """
        fact = self.of(name)
        if fact is None:
            return 'unknown'
        if fact['keyword'] is not None:
            return 'own' if fact['keyword'] in set(keywords or ()) else 'foreign'
        for term in ('material', 'drawback'):
            if term in fact['terms']:
                return term
        return 'restricted' if fact['restricted'] else 'universal'

    def worth(self, name, keywords):
        """`dict(value, relation, tier)`: the tier's value when the gift works for the team."""
        fact, relation = self.of(name), self.relation(name, keywords)
        return dict(relation=relation, tier=None if fact is None else fact['tier'],
                    value=TIER_VALUE[fact['tier']] if relation in PAYS else 0)

    def value(self, name, keywords):
        """What owning this gift is worth to a team built on `keywords`; 0 when unknown."""
        return self.worth(name, keywords)['value']

    def filed_under(self, keywords):
        """The names the game files under any of `keywords`, best tier first, then by name."""
        wanted = set(keywords or ())
        rows = [row for row in self.by_name.values() if row['keyword'] in wanted]
        return [row['name'] for row in sorted(rows, key=lambda row: (-TIER_VALUE[row['tier']], row['name']))]

    def universal(self):
        """The names of the gifts that work for any team, best tier first, then by name."""
        rows = [row for row in self.by_name.values() if self.relation(row['name'], ()) == 'universal']
        return [row['name'] for row in sorted(rows, key=lambda row: (-TIER_VALUE[row['tier']], row['name']))]
