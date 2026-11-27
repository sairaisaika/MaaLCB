"""Whose gift is this: the game's own filing, for every team, and the order the shop buys in.

Until 2026-11-27 the shop knew a gift's keyword only through the bundled catalogue, a
pinned import of 332 names. The wiki's table lists 477 obtainable gifts; the 145 the
catalogue lacks were keywordless to the shop whatever the game files them under, in all
ten keywords (live 2026-11-23: a Charge team left ``Material Interference Force Field``
on the shelf). And inside one keyword the shop bought by the alphabet.

The table is also closed over the game's terms: every status a description names is
classified in the importer, and a new one stops the import.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from maalimbus.floor_gifts import Offer, Trial, rank
from maalimbus.gift_facts import PAYS, RELATIONS, TIER_VALUE, GiftFacts, load
from maalimbus.gift_plan import shop_wanted

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'assets/resource/base'
spec = importlib.util.spec_from_file_location('import_wiki_gift_facts_relation', ROOT / 'tools/import_wiki_gift_facts.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

KEYWORDS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge', 'Slash', 'Pierce', 'Blunt')


def team(*keywords, allow=(), block=()):
    return SimpleNamespace(keywords=frozenset(keywords), allow=frozenset(allow), block=frozenset(block))


def catalogue(**entries):
    return SimpleNamespace(entries={name: dict(keywords=list(keywords)) for name, keywords in entries.items()})


def test_every_gift_stands_in_exactly_one_relation_to_every_team():
    facts = GiftFacts(BASE)
    for keyword in KEYWORDS:
        counts = {}
        for row in facts.by_name.values():
            relation = facts.relation(row['name'], {keyword})
            assert relation in RELATIONS and relation != 'unknown'
            counts[relation] = counts.get(relation, 0) + 1
        # Each of the ten keywords has gifts of its own: no team is left without a shelf.
        assert counts['own'] >= 15, (keyword, counts)
        assert counts['own'] + counts['foreign'] == sum(row['keyword'] is not None for row in facts.by_name.values())
    assert facts.relation('A Gift Nobody Listed', {'Burn'}) == 'unknown'


def test_the_relation_is_the_games_own_filing():
    facts = GiftFacts(BASE)
    assert facts.relation('Material Interference Force Field', {'Charge'}) == 'own'
    assert facts.relation('Material Interference Force Field', {'Burn'}) == 'foreign'
    assert facts.worth('Material Interference Force Field', {'Burn'})['value'] == 0
    assert facts.relation('Faint Vestige', {'Burn'}) == 'material'
    assert facts.relation('Tarnished Gauntlet', {'Burn'}) == 'drawback'        # a liability until it changes
    assert facts.relation('Regular Operational Gear', {'Burn'}) == 'restricted'    # written for one faction
    assert facts.relation('One with the Blade', {'Burn'}) == 'universal'
    # A keywordless gift that mentions a system does so as a bonus: it still works for anyone.
    assert facts.of('Warning Notice')['systems'] == ['Tremor']
    assert facts.relation('Warning Notice', {'Burn'}) == 'universal'
    for name in ('Faint Vestige', 'Tarnished Gauntlet', 'Regular Operational Gear'):
        assert facts.worth(name, {'Burn'})['value'] == 0
    assert PAYS == {'own', 'universal'}


def test_the_status_table_is_closed_and_covers_what_the_file_was_built_from():
    kinds = set(importer.STATUS_KIND.values())
    terms = {term for term, _ in importer.TERMS}
    # A status is a system, a term of the vocabulary, or named as unique: nothing else.
    assert kinds <= set(importer.SYSTEMS) | terms
    assert not set(importer.STATUS_KIND) & importer.UNIQUE and 'unique' in terms
    data = json.loads((BASE / 'gift-facts.json').read_text(encoding='utf-8'))
    assert data['version'] == 2
    assert data['source']['statuses_classified'] == len(importer.STATUS_KIND) + len(importer.UNIQUE) == 136
    # What lives inside a system counts as that system.
    assert importer.systems('Trigger {{StatusEffect|Tremor Burst|d}} and gain {{StatusEffect|Charge Barrier|b}}.') == \
        ['Tremor', 'Charge']
    assert importer.terms('Inflict 1 {{StatusEffect|Fragile|d}} and 2 {{StatusEffect|Bind|d}}.') == ['fragile', 'bind']
    assert importer.terms('Gain {{StatusEffect|Dimensional Rift|b}}.') == ['unique']


def test_the_shop_asks_for_the_gifts_the_catalogue_lacks_and_buys_the_better_tier_first():
    facts = load(BASE)
    names = facts.filed_under({'Charge'})
    assert 'Material Interference Force Field' in names and len(names) > 30
    # A catalogue that knows two Charge gifts, a tier II and a tier IV, and one Burn gift.
    low = next(row['name'] for row in facts.by_name.values() if row['keyword'] == 'Charge' and row['tier'] == 2)
    high = sorted(row['name'] for row in facts.by_name.values() if row['keyword'] == 'Charge' and row['tier'] == 4)[-1]
    burn = next(row['name'] for row in facts.by_name.values() if row['keyword'] == 'Burn')
    known = catalogue(**{low: ['Charge'], high: ['Charge'], burn: ['Burn']})
    before = shop_wanted(team('Charge'), known)
    assert before == sorted([low, high])                       # the alphabet, and nothing the catalogue lacks
    after = shop_wanted(team('Charge'), known, facts=facts)
    assert set(after) == set(names) and burn not in after
    tiers = [TIER_VALUE[facts.of(name)['tier']] for name in after]
    assert tiers == sorted(tiers, reverse=True) and after.index(high) < after.index(low)
    # The player's own list and block still decide first.
    assert shop_wanted(team('Charge', allow=[low]), known, facts=facts)[0] == low
    assert high not in shop_wanted(team('Charge', block=[high]), known, facts=facts)


def test_every_team_gets_a_longer_list_and_keywordless_is_still_the_players_tick():
    facts = load(BASE)
    empty = catalogue()
    for keyword in KEYWORDS:
        wanted = shop_wanted(team(keyword), empty, facts=facts)
        assert wanted == facts.filed_under({keyword}) and len(wanted) >= 15
        assert all(facts.relation(name, {keyword}) == 'own' for name in wanted)
    with_any = shop_wanted(team('Burn', 'Keywordless'), empty, facts=facts)
    assert 'One with the Blade' in with_any
    assert not {'Faint Vestige', 'Tarnished Gauntlet', 'Regular Operational Gear'} & set(with_any)
    # A catalogue that files a Vestige as keywordless does not get it bought on the tick alone,
    # and does when the player names it.
    vestige = catalogue(**{'Faint Vestige': ['Keywordless']})
    assert 'Faint Vestige' not in shop_wanted(team('Keywordless'), vestige, facts=facts)
    assert 'Faint Vestige' in shop_wanted(team('Keywordless', allow=['Faint Vestige']), vestige, facts=facts)


def test_a_floor_gift_the_catalogue_does_not_know_is_still_the_teams():
    facts = load(BASE)
    offers = [Offer(name, name, frozenset(), (0, 0, 10, 10), Trial(0, 'none', 0), False)
              for name in ('Material Interference Force Field', 'Phlebotomy Pack')]
    ranked = rank(offers, team('Charge'), set(), facts)
    top = ranked[0]
    assert top['title'] == 'Material Interference Force Field' and top['preferred'] and top['gift_relation'] == 'own'
    assert top['score_components']['synergy'] == -40
    for row in ranked:
        assert row['score'] == sum(row['score_components'].values())
    other = rank(offers, team('Burn'), set(), facts)
    assert {row['title']: row['gift_relation'] for row in other} == {
        'Material Interference Force Field': 'foreign', 'Phlebotomy Pack': 'universal'}
    assert not any(row['preferred'] for row in other)
