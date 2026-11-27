"""The game's own two dictionaries, in the game's own order.

The program used to carry its keyword list in alphabetical order with two entries the
game does not have. The user pointed at the two places where the game prints its
vocabulary (2026-11-27), and they are the authority:

* the shop's **Keyword Refresh** dialog: the ten keywords an E.G.O Gift can be filed
  under, two rows of five -- seven systems, then three damage types;
* the Identity list's **filter panel**: Skill Attack Type (three), Skill Affinity
  (seven), Keyword (the seven systems), plus Rarity and Uptie Tier.

The seven systems are the same words in both. What an Identity can be filtered by and
what a gift can be filed under therefore meet in the systems and the damage types, and
nowhere else: an affinity describes skills and gifts, never a team's keyword.

``Keywordless`` is not a word of the game. It is this program's switch for "also buy
gifts that work for any team" (``gift_facts.GiftFacts.relation``: ``universal``).
A Vestige is a material, not a keyword; ``storage.KEYWORDS`` still accepts the old word
so that a saved team naming it loads.
"""

#: Status systems: Keyword Refresh's first seven, and the Identity filter's "Keyword".
SYSTEMS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge')
#: Keyword Refresh's last three, and the Identity filter's "Skill Attack Type".
ATTACK_TYPES = ('Slash', 'Pierce', 'Blunt')
#: Everything an E.G.O Gift can be filed under, as the shop's dialog lays it out.
GIFT_KEYWORDS = SYSTEMS + ATTACK_TYPES
#: The Identity filter's "Skill Affinity", as printed (the panel abbreviates Gluttony).
AFFINITIES = ('Wrath', 'Lust', 'Sloth', 'Gluttony', 'Gloom', 'Pride', 'Envy')
#: What the team settings offer, in order: the game's ten, then the program's own switch.
TEAM_CHOICES = GIFT_KEYWORDS + ('Keywordless',)
