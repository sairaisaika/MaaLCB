"""A floor gift is ranked on the gift too, not only on its Mounting Trial.

The bundled catalogue carries names, keywords and icons. Tier and shop cost come from the
wiki's data table, imported as facts only: no description text is written anywhere. The
user's reading of three runs (2026-11-24) was that the gifts taken were weak; the ranking
could not tell a tier IV gift from a tier I gift.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus.floor_gifts import Offer, Trial, rank
from maalimbus.gift_facts import TIER_VALUE, GiftFacts

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'assets/resource/base'
spec = importlib.util.spec_from_file_location('import_wiki_gift_facts', ROOT / 'tools/import_wiki_gift_facts.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

FREE = Trial(0, 'none', 0)
#: The shape of the wiki's table, with invented gifts and invented description text.
TABLE = '''return {
	--A section
	["Tin Whistle"] = { name = "Tin Whistle", desc = "Clash Power +1 for {{StatusEffect|Burn|d}} Skills.", sin = "wrath", tier = "II", cost = 200, category = "Burn", upgrade = 2 },
	["Tin Whistle+"] = { name = "Tin Whistle", desc = "Clash Power +2.", desc = "Clash Power +3.", sin = "wrath", tier = "II", cost = 200, category = "Burn" },
	["Tin Whistle++"] = { name = "Tin Whistle", desc = "Clash Power +4.", sin = "wrath", tier = "II", cost = 200, category = "Burn" },
	["Paper Boat (MD)"] = { name = "Paper Boat", desc = "Heal 5 HP. Deal +10% damage.", sin = "gloom", tier = "IV", cost = 400 },
	["Paper Boat"] = { name = "Paper Boat", desc = "A story dungeon gift.", sin = "gloom", category = "Bleed", tier = "IV", cost = 400 },
	["Paper Boat (Legacy)"] = { name = "Paper Boat", desc = "An older one.", sin = "gloom", tier = "I", cost = 100 },
	["Story Lantern"] = { name = "Story Lantern", desc = "No tier.", sin = "pride" },
{FILL}
}
'''
FILLER = '\n'.join('\t["Filler %d"] = { name = "Filler %d", desc = "Nothing.", sin = "envy", tier = "I", cost = 100 },'
                   % (i, i) for i in range(100))


def table(extra=''):
    return TABLE.replace('{FILL}', FILLER + extra)


def test_the_table_is_read_strictly_and_only_facts_come_out():
    rows, left_out = importer.facts(table())
    by_name = {row['name']: row for row in rows}
    assert by_name['Tin Whistle'] == dict(name='Tin Whistle', tier=2, cost=200, keyword='Burn', sin='wrath',
                                          enhancements=2, systems=['Burn'], terms=['clash_power'])
    # The suffixed entry is the Mirror Dungeon gift; its story twin and its legacy copy are not.
    assert by_name['Paper Boat'] == dict(name='Paper Boat', tier=4, cost=400, keyword=None, sin='gloom',
                                         enhancements=0, systems=[], terms=['damage_up', 'heal'])
    assert 'Story Lantern' not in by_name and len(rows) == 102
    assert left_out == dict(without_tier=1, legacy=1, enhanced=2, story_dungeon_twin=1,
                            repeated_fields=['Tin Whistle+.desc'])
    assert not any('desc' in row for row in rows)


@pytest.mark.parametrize('line, complaint', [
    ('\tp.Something = 3', 'not a gift entry'),
    ('\t["Odd"] = { name = "Odd", desc = "x", sin = "envy", tier = "IX", cost = 1 },', 'unknown tier'),
    ('\t["Odd"] = { name = "Odd", desc = "x", sin = "envy", tier = "I", cost = 1, category = "Frost" },', 'unknown keyword'),
    ('\t["Odd+"] = { name = "Odd", desc = "x", sin = "envy", tier = "I", cost = 1 },', 'no base entry'),
    ('\t["Filler 3"] = { name = "Filler 3", desc = "x", sin = "envy", tier = "I", cost = 1 },', 'twice'),
    ('\t["Odd"] = { name = "Odd", desc = "x", sin = "envy", tier = "I", cost = {1} },', 'unreadable field'),
])
def test_a_line_the_reader_does_not_understand_stops_the_import(line, complaint):
    with pytest.raises(ValueError, match=complaint):
        importer.facts(table('\n' + line))


def test_the_committed_file_holds_facts_and_no_description():
    data = json.loads((BASE / 'gift-facts.json').read_text(encoding='utf-8'))
    assert data['source']['page'] == 'Module:EgoGift/data' and data['source']['revid'] and data['source']['license']
    assert len(data['gifts']) > 400
    allowed = {'name', 'tier', 'cost', 'keyword', 'sin', 'enhancements', 'systems', 'terms'}
    for row in data['gifts']:
        assert set(row) == allowed
        assert row['tier'] in TIER_VALUE and set(row['terms']) <= set(data['source']['terms'])
    # Every gift a fusion recipe names is known, so a recipe's result has a tier.
    recipes = json.loads((BASE / 'gift-fusion-recipes.json').read_text(encoding='utf-8'))['recipes']
    facts = GiftFacts(BASE)
    assert all(facts.of(name) for row in recipes for name in row['ingredients'] + [row['result']])


def test_a_printed_title_a_letter_off_is_still_the_gift_and_a_stranger_is_unknown():
    facts = GiftFacts(BASE)
    assert facts.of('Golden Urn')['tier'] == 2 and facts.of('golden urn') is facts.of('Golden Urn')
    assert facts.of('Decamillenpial Stewpot') is facts.of('Decamillennial Stewpot')   # the catalogue's spelling
    assert facts.of('A Gift Nobody Listed') is None and facts.of('') is None
    assert facts.value('A Gift Nobody Listed', {'Burn'}) == 0


def test_a_gift_is_worth_its_tier_to_the_team_it_works_for():
    facts = GiftFacts(BASE)
    epicenter = facts.of('Epicenter')
    assert (epicenter['tier'], epicenter['keyword']) == (3, 'Tremor')
    assert facts.value('Epicenter', {'Tremor'}) == TIER_VALUE[3]
    assert facts.value('Epicenter', {'Poise'}) == 0                 # another team's gift
    assert facts.value('Grey Coat', {'Poise'}) == TIER_VALUE[2]     # no keyword: works for anyone
    # No tier is worth a lost clash.
    assert max(TIER_VALUE.values()) < Trial(0, 'clash_power', 1).penalty


def offer(title, trial=FREE, owned=False, keywords=()):
    return Offer(title, title, frozenset(keywords), (0, 0, 10, 10), trial, owned)


def test_the_ranking_prefers_the_better_gift_and_says_why():
    team = SimpleNamespace(allow=frozenset(), block=frozenset(), keywords=frozenset({'Poise'}))
    facts = GiftFacts(BASE)
    lunar, phlebotomy = facts.of('Lunar Memory'), facts.of('Phlebotomy Pack')
    assert lunar['tier'] > phlebotomy['tier'] and lunar['keyword'] is None and phlebotomy['keyword'] is None
    offers = [offer('Phlebotomy Pack'), offer('Lunar Memory'), offer('Epicenter', keywords={'Tremor'})]
    # Without facts the three free gifts tie and the alphabet decides.
    assert [row['title'] for row in rank(offers, team, set())] == ['Epicenter', 'Lunar Memory', 'Phlebotomy Pack']
    ranked = rank(offers, team, set(), facts)
    assert ranked[0]['title'] == 'Lunar Memory'
    assert ranked[0]['score_components']['gift_value'] == -TIER_VALUE[lunar['tier']]
    assert ranked[0]['gift_tier'] == lunar['tier']
    assert {row['title']: row['score_components']['gift_value'] for row in ranked}['Epicenter'] == 0
    for row in ranked:
        assert row['score'] == sum(row['score_components'].values())


def test_an_owned_copy_and_a_clash_trial_are_not_bought_with_tier():
    team = SimpleNamespace(allow=frozenset(), block=frozenset(), keywords=frozenset())
    facts = GiftFacts(BASE)
    ranked = rank([offer('Lunar Memory', owned=True), offer('Phlebotomy Pack')], team, set(), facts)
    assert [row['title'] for row in ranked] == ['Phlebotomy Pack', 'Lunar Memory']
    assert ranked[1]['score_components']['gift_value'] == 0
    clash = rank([offer('Lunar Memory', Trial(1, 'clash_power', 1)), offer('Phlebotomy Pack', Trial(1, 'hp', 10))],
                 team, set(), facts)
    assert clash[0]['title'] == 'Phlebotomy Pack'
