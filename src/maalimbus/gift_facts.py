"""What is known about a gift besides its name: tier, shop cost, keyword.

The facts come from the wiki's own data table (``tools/import_wiki_gift_facts.py``,
``assets/resource/base/gift-facts.json``). Until 2026-11-25 a floor gift was chosen on
its Mounting Trial, on whether the team's system matched and on whether it was already
owned -- never on the gift itself, because the bundled catalogue only carries names,
keywords and icons. A tier IV gift and a tier I gift with the same trial were a coin
toss decided by the alphabet.

A gift the table does not know is worth nothing here. That is the honest value of
"unknown", not a penalty: the trial and ownership terms still rank it.
"""
import difflib
import json
from pathlib import Path

from .gift_vision import normalized

#: What a tier is worth when a floor gift is ranked, in the units of a Mounting Trial's
#: penalty (`floor_gifts.Trial.penalty`). Policy, not a formula. The top stays well
#: under a point of enemy Clash Power (240), so a better gift can outweigh a longer
#: fight but never a lost clash; the steps follow the game's own shop prices, whose
#: medians are about 150, 200, 250 and 400 for tiers I to IV.
TIER_VALUE = {1: 0, 2: 15, 3: 40, 4: 80, 5: 100, 'EX': 100}
#: How close a printed title must be to a known name, and how far ahead of the runner-up,
#: before it is taken for that gift. The same bounds the theme pack names use.
CLOSE, MARGIN = .93, .04


class GiftFacts:
    def __init__(self, root):
        data = json.loads((Path(root) / 'gift-facts.json').read_text(encoding='utf-8'))
        if data.get('version') != 1:
            raise ValueError('Unknown gift facts version')
        self.source = data['source']
        self.by_name = {}
        for row in data['gifts']:
            key = normalized(row['name'])
            if key in self.by_name:
                raise ValueError('Two gift facts share the name %r' % row['name'])
            self.by_name[key] = row

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
        ranks = sorted(((difflib.SequenceMatcher(None, key, known).ratio(), known) for known in self.by_name),
                       reverse=True)[:2]
        if ranks and ranks[0][0] >= CLOSE and not (len(ranks) > 1 and ranks[0][0] - ranks[1][0] < MARGIN):
            return self.by_name[ranks[0][1]]
        return None

    def value(self, name, keywords):
        """What owning this gift is worth to a team built on `keywords`; 0 when unknown.

        A gift filed under a system or damage type only pays off for a team that uses it,
        so another team's gift is worth nothing whatever its tier. A gift filed under no
        keyword works for anyone.
        """
        fact = self.of(name)
        if fact is None:
            return 0
        if fact['keyword'] is not None and fact['keyword'] not in set(keywords or ()):
            return 0
        return TIER_VALUE[fact['tier']]
