"""Shop fusion: the recipe table, its importer and the decisions drawn from it."""
import importlib.util
import json
from pathlib import Path

import pytest

from maalimbus import gift_fusion
from maalimbus.gift_fusion import Recipes, keyword_chance, random_fusion, result_tier

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'assets/resource/base' / gift_fusion.FILE


def importer():
    spec = importlib.util.spec_from_file_location('import_wiki_fusion_recipes',
                                                  ROOT / 'tools/import_wiki_fusion_recipes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def recipes():
    return gift_fusion.load(DATA)


def test_the_table_says_where_it_came_from_and_covers_every_system(recipes):
    source = recipes.source
    assert source['page'] == 'List of E.G.O Gifts/Fusion' and isinstance(source['revid'], int)
    assert source['license_url'].startswith('https://creativecommons.org/licenses/by-sa/')
    assert len(source['wikitext_sha256']) == 64 and 'no artwork' in source['scope']
    per_system = {system: [row for row in recipes.rows if row['kind'] == 'keyword' and row['group'] == system]
                  for system in gift_fusion.SYSTEMS}
    # Each system has a two-gift recipe, a recipe that consumes that result, and a third.
    for system, rows in per_system.items():
        assert len(rows) == 3, system
        first = next(row for row in rows if len(row['ingredients']) == 2)
        assert any(first['result'] in row['ingredients'] for row in rows), system
    # Wiki page-title disambiguators are not part of a name the game prints.
    assert not [name for name in recipes.names if name.endswith('(MD)')]
    assert 'Rusted Hilt' in recipes.names and 'Sublimity' in recipes.names


def test_the_one_recipe_with_more_than_three_gifts_takes_any_two_fragments(recipes):
    row, = [row for row in recipes.rows if row['kind'] == 'super_shop']
    assert row['result'] == 'Lunar Memory' and len(row['ingredients']) == 3
    slot, = row['any_of']
    assert slot['count'] == 2 and len(slot['names']) == 7 and 'Fragment of Hellfire' in slot['names']
    owned = row['ingredients'] + ['Fragment of Decay', 'Fragment of Conceit']
    assert recipes.ready(owned) == []                      # not offered in an ordinary shop
    plan, = recipes.ready(owned, super_shop=True)
    assert plan['result'] == 'Lunar Memory' and plan['gifts'][-2:] == ['Fragment of Decay', 'Fragment of Conceit']
    assert recipes.ready(row['ingredients'] + ['Fragment of Decay'], super_shop=True) == []


def test_the_tier_and_chance_numbers_are_the_ones_the_wiki_states():
    # Points 3/6/10/15/30; 11, 17 and 25 points are the steps in an ordinary shop.
    assert result_tier([1, 1]) == 1 and result_tier([1, 1, 1]) == 1          # 6, 9
    assert result_tier([1, 1, 2]) == 2 and result_tier([2, 2]) == 2          # 12, 12
    assert result_tier([2, 3]) == 2 and result_tier([2, 2, 2]) == 3          # 16, 18
    assert result_tier([3, 3]) == 3 and result_tier([3, 4]) == 4             # 20, 25
    assert result_tier([3, 3, 1]) == 3 and result_tier([3, 3, 2]) == 4       # 23, 26
    # A super shop asks for less: 10, 15 and 22.
    assert result_tier([1, 1, 1], super_shop=True) == 1
    assert result_tier([1, 1, 2], super_shop=True) == 2 and result_tier([2, 3], super_shop=True) == 3
    assert result_tier([3, 3, 1], super_shop=True) == 4
    assert [keyword_chance(n) for n in (2, 3, 4, 6)] == [.60, .90, .99, .99]
    assert [keyword_chance(n, wish=True) for n in (2, 3, 4)] == [.90, .99, .9999]
    assert gift_fusion.WISH_STARLIGHT == 5
    for bad in ([], [2], [2, 6], [None, 1]):
        with pytest.raises(ValueError):
            result_tier(bad)
    with pytest.raises(ValueError):
        keyword_chance(1)


def test_a_recipe_is_ready_when_all_its_gifts_are_owned_and_its_result_is_not(recipes):
    assert recipes.ready(['Melted Paraffin']) == []
    plan, = recipes.ready(['Melted Paraffin', 'Decamillennial Stewpot', 'Awe'])
    assert plan['result'] == 'Secret Cookbook' and plan['gifts'] == ['Melted Paraffin', 'Decamillennial Stewpot']
    # Owning the result already: nothing to do.
    assert recipes.ready(['Melted Paraffin', 'Decamillennial Stewpot', 'Secret Cookbook']) == []
    # The result feeds the next recipe of the same system.
    plan, = recipes.ready(['Ashes to Ashes', 'Dust to Dust', 'Secret Cookbook'])
    assert plan['result'] == 'Soothe the Dead'
    # A team built around another system does not chase this one's recipes.
    assert recipes.ready(['Melted Paraffin', 'Decamillennial Stewpot'], ['Charge']) == []
    assert recipes.ready(['Melted Paraffin', 'Decamillennial Stewpot'], ['Charge', 'Burn'])


def test_two_ready_recipes_that_share_a_gift_yield_the_longer_one(recipes):
    owned = ['Spicebush Branch', 'Ragged Umbrella', 'Broken Glasses']
    plan, = recipes.ready(owned, ['Tremor'])               # theme recipes serve any team
    assert plan['result'] == 'Spicebush, Glasses, and Mailed Letter' and sorted(plan['gifts']) == sorted(owned)
    # Without the branch only the short one is there.
    plan, = recipes.ready(owned[1:])
    assert plan['result'] == 'Unmailed Letter'
    # Two recipes that share nothing are both offered.
    both = recipes.ready(['Melted Paraffin', 'Decamillennial Stewpot', 'UPS System', 'Miniature Telepole'])
    assert {plan['result'] for plan in both} == {'Secret Cookbook', 'Insulator'}


def test_titles_read_from_the_screen_name_their_gift_or_nothing(recipes):
    assert recipes.identify('Omnivibro-octovecti-bell') == 'Omnivibro-octovecti-bell'
    assert recipes.identify('omnivibro octovecti bell') == 'Omnivibro-octovecti-bell'
    assert recipes.identify('Decamillennial Stewp0t') == 'Decamillennial Stewpot'      # one wrong glyph
    assert recipes.identify('Pocket Watch : Type') is None                           # four candidates
    assert recipes.identify('Gift') == 'Gift' and recipes.identify('Gif') is None
    assert recipes.identify('Wound Clerid') is None                                  # not a recipe gift
    # Owned names arrive as the screen printed them.
    assert recipes.ready(['melted paraffin', 'DECAMILLENNIAL STEWPOT'])[0]['result'] == 'Secret Cookbook'


def test_what_to_buy_names_the_gifts_that_complete_a_recipe_nearest_first(recipes):
    rows = recipes.shopping(['Melted Paraffin'], ['Burn'])
    assert rows[0] == dict(name='Decamillennial Stewpot', result='Secret Cookbook', missing=1)
    names = [row['name'] for row in rows]
    assert 'Ashes to Ashes' in names and 'UPS System' not in names
    # A theme recipe is only chased once one of its gifts is owned.
    assert 'Frozen Cries' not in names
    rows = recipes.shopping(['Haunted Shoes'], ['Burn'])
    assert dict(name='Frozen Cries', result='Hoarfrost Footprint', missing=1) in rows
    # No system chosen: every keyword recipe is open.
    assert {'UPS System', 'Melted Paraffin'} <= {row['name'] for row in recipes.shopping([], [])}
    # An owned result closes its recipe.
    assert 'Decamillennial Stewpot' not in [row['name'] for row in recipes.shopping(
        ['Melted Paraffin', 'Secret Cookbook'], ['Burn']) if row['result'] == 'Secret Cookbook']


def test_a_random_fusion_spends_only_gifts_of_other_known_keywords(recipes):
    gifts = {
        'Awe': dict(keywords=['Bleed'], tier=2),
        'Wound Clerid': dict(keywords=['Bleed'], tier=2),
        'Red Order': dict(keywords=['Sinking'], tier=2),
        'Stone Tomb': dict(keywords=['Poise'], tier=3),
        'Employee Card': dict(keywords=['Charge'], tier=2),           # the team's own
        'Phlebotomy Pack': dict(keywords=['Keywordless'], tier=1),    # helps any team
        'Some New Gift': dict(keywords=[], tier=1),                   # unknown: not ours to spend
    }
    plan = random_fusion(gifts, ['Charge', 'Tremor'], recipes)
    assert plan['keyword'] == 'Charge' and plan['gifts'] == ['Awe', 'Red Order', 'Wound Clerid']
    assert plan['chance'] == .90 and plan['tier'] == 3               # three tier II: 18 points
    assert random_fusion(gifts, [], recipes) is None                 # no keyword to ask for
    two = random_fusion(gifts, ['Charge'], recipes, size=2)
    assert two['gifts'] == ['Awe', 'Red Order'] and two['chance'] == .60 and two['tier'] == 2
    del gifts['Stone Tomb'], gifts['Red Order']
    assert random_fusion(gifts, ['Charge'], recipes) is None         # only two to spare
    # A tier nobody read leaves the result tier unknown instead of guessed.
    unknown = {name: dict(keywords=['Bleed'], tier=None) for name in ('A', 'B', 'C')}
    assert random_fusion(unknown, ['Burn'], recipes)['tier'] is None


def test_a_random_fusion_leaves_recipe_gifts_alone(recipes):
    gifts = {
        'Rusted Muzzle': dict(keywords=['Bleed'], tier=2),            # with Devotion and one more: Bloody Mist
        'Devotion': dict(keywords=['Bleed'], tier=3),                 # a recipe result
        'Awe': dict(keywords=['Bleed'], tier=2),
        'Red Order': dict(keywords=['Sinking'], tier=2),
        'Stone Tomb': dict(keywords=['Poise'], tier=3),
    }
    # No system chosen for the recipes: the Bleed recipes are in reach, their gifts stay.
    assert recipes.reserved(gifts) == {'Rusted Muzzle', 'Devotion'}
    plan = random_fusion(gifts, ['Charge'], recipes)
    # A Charge team does not chase Bleed recipes, so the ingredient is free; the result never is.
    assert recipes.reserved(gifts, ['Charge']) == {'Devotion'}
    assert 'Devotion' not in plan['gifts'] and len(plan['gifts']) == 3
    # An ingredient whose recipe is already done is free again.
    assert recipes.reserved(['Arrested Hymn', 'Devotion', 'Bloody Mist']) == {'Devotion', 'Bloody Mist'}


def test_the_importer_refuses_a_table_it_cannot_read_strictly():
    tool = importer()
    head = '{|class="x"\n! colspan="4" |Fused Gifts\n! |Result\n|-\n'
    group = "| rowspan=\"%d\" style=\"x\"|[[Burn|<font>'''Burn'''</font>]]\n"
    row = '|{{GiftTT|A One}}{{ItemHeader|x|A One}}\n|{{GiftTT|B Two (MD)|filename=B}}\n|\n|style="border-left:2px"|{{GiftTT|C Three}}\n'
    other = '|{{GiftTT|D Four}}\n|{{GiftTT|E Five}}\n|{{GiftTT|F Six}}\n|style="border-left:2px"|{{GiftTT|G Seven}}\n'
    good = head + group % 2 + row + '|-\n' + other + '|}\n'
    rows = tool.recipes(good)
    assert rows == [dict(kind='keyword', group='Burn', ingredients=['A One', 'B Two'], result='C Three'),
                    dict(kind='keyword', group='Burn', ingredients=['D Four', 'E Five', 'F Six'], result='G Seven')]
    with pytest.raises(ValueError, match='ended 1 rows early'):
        tool.recipes(head + group % 3 + row + '|-\n' + other + '|}\n')
    with pytest.raises(ValueError, match='belongs to no group'):
        tool.recipes(head + group % 1 + row + '|-\n' + other + '|}\n')
    with pytest.raises(ValueError, match='exactly one result'):
        tool.recipes(head + group % 1 + row.replace('style="border-left:2px"|', '') + '|}\n')
    with pytest.raises(ValueError, match='same gifts'):
        tool.recipes(head + group % 2 + row + '|-\n' + row + '|}\n')
    with pytest.raises(ValueError, match='Unknown keyword group'):
        tool.recipes(head + (group % 1).replace("'''Burn'''", "'''Frost'''") + row + '|}\n')


def test_the_importer_reproduces_the_committed_table_shape(tmp_path):
    tool = importer()
    data = json.loads(DATA.read_text(encoding='utf-8'))
    # Rebuilding from the same rows must be a fixed point of the loader's rules.
    assert Recipes(data).rows == data['recipes']
    assert tool.TARGET == DATA and tool.AGENT == 'wiki-data-check/1.0'      # no project name leaves this machine
    with pytest.raises(ValueError):
        Recipes(dict(data, source={}))
    with pytest.raises(ValueError):
        Recipes(dict(data, version=2))
