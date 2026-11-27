"""Graces: ten cards, three levels each, an allowance and the owned stock behind it.

Read on the game's own page on 2026-11-27, with the user's selection left on it (cards 1,
5 and 6 at ``++``; evidence/runtime/packaged-mirror-20261127-180801 and -181009):

* a card costs its base once, twice (``+``) or three times (``++``);
* a card's own ``+`` / ``++`` button sets its level and selects nothing; pressing the lit
  button returns the card to plain; "Enhance All" does the same for all ten;
* past the run's allowance the counter prints ``0+90`` beside "Available" and
  ``3607-90`` beside "Owned": the rest comes from the stock;
* the game remembers no selection, so there is no "saved" plan to follow.

Until then a plan was plain cards and one total, and enhancement was refused outright.
"""
import json
from pathlib import Path

import pytest

from maalimbus import grace_vision, mirror_starlight, star_vision
from maalimbus.global_settings import apply_builds, collect_builds
from maalimbus.grace_transaction import GraceTransaction
from maalimbus.mirror_starlight import STOCK_ALL, apply, collect, from_nodes, notation, plan, resolve
from maalimbus.mirror_task_options import collect as collect_task_options
from maalimbus.policies import Team
from maalimbus.storage import ProfileStore
from maalimbus.vision import Text
from maalimbus.window import plan_step

ROOT = Path(__file__).resolve().parents[1]
PI = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
NODES = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
SIZE = (1920, 1080)


def nodes(names, mode, rows=(), spend='allowance', cap='0', extra=None):
    """Option nodes as the framework hands them over: `rows` is ((part, cards), ...)."""
    chosen = {names['plan']: dict(attach=dict(mode=mode)), names['spend']: dict(attach=dict(mode=spend)),
              names['cap']: dict(attach=dict(cap=cap)),
              names['base']: dict(attach={}), names['plus']: dict(attach={}), names['plusplus']: dict(attach={})}
    for part, cards in rows:
        chosen[names[part]] = dict(attach={'star_%d' % card: True for card in cards})
    chosen.update(extra or {})

    def get(name):
        if name in chosen:
            return chosen[name]
        if name.endswith(('_keywords', '_star_base', '_star_plus', '_star_plusplus')):
            return dict(attach={})
        if name.endswith('_order_text'):
            return dict(attach=dict(order=''))
        if name.endswith('_star_cap'):
            return dict(attach=dict(cap='0'))
        if name.endswith('_star_spend'):
            return dict(attach=dict(mode='allowance'))
        return dict(attach=dict(mode='keep'))
    return get


TASK = mirror_starlight.TASK_NODES


def test_a_plan_is_cards_with_levels_and_what_may_come_from_the_stock():
    chosen = plan(dict(levels={5: 2, 0: 2, 4: 2}, stock=90))
    assert chosen == dict(choices=[0, 4, 5], levels={0: 2, 4: 2, 5: 2}, budget=1000000, stock=90)
    assert notation(chosen) == ('0++', '4++', '5++')
    # A plan saved before levels existed is plain cards and its own total.
    assert plan(dict(choices=[1, 3], budget=60)) == dict(choices=[1, 3], levels={1: 0, 3: 0}, budget=60, stock=0)
    for bad in (dict(levels={10: 0}), dict(levels={1: 3}), dict(levels={1: 1}, stock=-1), dict(choices=[1, 1], budget=5), []):
        with pytest.raises(ValueError):
            plan(bad)
    team = Team(2, frozenset(), graces=('0++', '4+', '5'), grace_budget=1000000, grace_stock=90)
    assert mirror_starlight.from_team(team)['levels'] == {0: 2, 4: 1, 5: 0}
    assert mirror_starlight.from_team(Team(3, frozenset())) is None            # no plan was ever set


def test_the_presets_are_one_choice_and_a_custom_plan_is_one_tick_a_card():
    # "Select All Graces" and "Enhance All ++" are two presses in the game; here one choice.
    assert from_nodes(nodes(TASK, 'all_plusplus', spend='stock_all'), TASK) == plan(
        dict(levels={card: 2 for card in range(10)}, stock=STOCK_ALL))
    assert from_nodes(nodes(TASK, 'all'), TASK)['levels'] == {card: 0 for card in range(10)}
    assert from_nodes(nodes(TASK, 'none'), TASK)['choices'] == []
    # The user's own examples: 1, 5 and 6 all at ++ is three ticks in one row;
    # 1 and 5 at + with 6 at ++ is three ticks in two rows.
    assert from_nodes(nodes(TASK, 'custom', (('plusplus', (0, 4, 5)),)), TASK)['levels'] == {0: 2, 4: 2, 5: 2}
    assert from_nodes(nodes(TASK, 'custom', (('plus', (0, 4)), ('plusplus', (5,)))), TASK)['levels'] == {0: 1, 4: 1, 5: 2}
    # Ticked in two rows: the higher level.
    assert from_nodes(nodes(TASK, 'custom', (('base', (2,)), ('plusplus', (2,)))), TASK)['levels'] == {2: 2}
    assert from_nodes(nodes(TASK, 'custom', (('base', (2,)),), spend='stock_cap', cap='150'), TASK)['stock'] == 150
    for broken in (nodes(TASK, 'keep'), nodes(TASK, 'all', spend='everything'), nodes(TASK, 'all', spend='stock_cap', cap='many')):
        with pytest.raises(ValueError):
            from_nodes(broken, TASK)


def test_the_interface_offers_two_sources_the_presets_and_a_row_per_level():
    source = PI['option']['mirror_star_source']
    assert [case['name'] for case in source['cases']] == ['team', 'task'] and source['default_case'] == 'team'
    assert NODES['MirrorStarSource']['attach'] == dict(source='team')
    task = PI['option']['mirror_star_task_plan']
    assert [case['name'] for case in task['cases']] == ['none', 'all', 'all_plus', 'all_plusplus', 'custom']
    custom = next(case for case in task['cases'] if case['name'] == 'custom')
    assert custom['option'] == ['mirror_star_task_base', 'mirror_star_task_plus', 'mirror_star_task_plusplus',
                                'mirror_star_task_spend']
    for slot in (1, 40):
        team = PI['option']['global_team_%d_stars' % slot]
        assert [case['name'] for case in team['cases']] == ['keep', 'none', 'all', 'all_plus', 'all_plusplus', 'custom']
        assert team['default_case'] == 'keep'
        for part in ('base', 'plus', 'plusplus'):
            row = PI['option']['global_team_%d_star_%s' % (slot, part)]
            assert row['type'] == 'checkbox' and [case['name'] for case in row['cases']] == [str(n) for n in range(1, 11)]
        spend = PI['option']['global_team_%d_star_spend' % slot]
        assert [case['name'] for case in spend['cases']] == ['allowance', 'stock_cap', 'stock_all']
        assert spend['default_case'] == 'allowance'        # the owned stock is not touched unless asked
        for name in mirror_starlight.team_nodes(slot).values():
            assert name in NODES
    # The cards carry their names and their three costs.
    text = json.loads((ROOT / 'assets/i18n/zh_cn.json').read_text(encoding='utf-8'))
    assert text['mirror_star_card_0'] == '1 Star of the Beginning（10 / 20 / 30）'
    assert text['mirror_star_card_9'] == '10 Perfected Possibility（60 / 120 / 180）'
    # Gone: the saved and automatic sources, the per-card on/off options, the total budget.
    assert not [name for name in PI['option'] if name.startswith(('mirror_star_task_0', 'mirror_star_task_budget'))]
    assert not [name for name in NODES if name.startswith(('MirrorTeamStar', 'MirrorTaskStar0', 'MirrorTaskStarBudget'))]
    assert not [key for key in text if key in ('mirror_star_saved', 'mirror_star_auto', 'mirror_star_budget')]


def test_the_task_follows_the_team_and_lends_its_own_plan_to_a_team_without_one(tmp_path):
    get = nodes(TASK, 'custom', (('plus', (1, 3)),), extra={'MirrorStarSource': dict(attach=dict(source='team'))})
    source, task = collect(get)
    assert source == 'team' and task['levels'] == {1: 1, 3: 1}
    # A choice saved before 2026-11-27 said "saved" or "auto": both mean the default now.
    for old in ('saved', 'auto'):
        assert collect(nodes(TASK, 'none', extra={'MirrorStarSource': dict(attach=dict(source=old))}))[0] == 'team'
    with pytest.raises(ValueError):
        collect(nodes(TASK, 'none', extra={'MirrorStarSource': dict(attach=dict(source='elsewhere'))}))
    assert resolve(tmp_path, 2) is None                       # no rule file: the loop keeps its own defaults
    ProfileStore(tmp_path / 'user-team-profiles.json').save([
        Team(2, frozenset({'Charge'}), graces=('0++', '4++', '5++'), grace_budget=1000000, grace_stock=90),
        Team(3, frozenset({'Burn'}))])
    apply(tmp_path, source, task)
    own = resolve(tmp_path, 2)
    assert own == dict(graces='1,5,6', grace_levels='1:2,5:2,6:2', grace_budget=1000000, grace_stock=90,
                       grace_auto=False, star_source='team', plan_of='team', team=2)
    lent = resolve(tmp_path, 3)
    assert lent['plan_of'] == 'task' and lent['graces'] == '2,4' and lent['grace_levels'] == '2:1,4:1'
    assert lent['grace_stock'] == 0
    apply(tmp_path, 'task', task)
    assert resolve(tmp_path, 2)['plan_of'] == 'task' and resolve(tmp_path, 2)['graces'] == '2,4'
    with pytest.raises(ValueError):
        apply(tmp_path, 'saved', task)


def test_a_teams_plan_is_set_with_the_team(tmp_path):
    ProfileStore(tmp_path / 'user-team-profiles.json').save(
        [Team(2, frozenset({'Charge'}), deployment=('Yi Sang',)), Team(3, frozenset())])
    names = mirror_starlight.team_nodes(2)
    edits = collect_builds(nodes(names, 'custom', (('plusplus', (0, 4, 5)),), spend='stock_cap', cap='90'))
    assert edits == {'2': dict(keywords='keep', order='keep', stars=dict(levels={0: 2, 4: 2, 5: 2}, stock=90))}
    assert apply_builds(tmp_path, edits) == [2]
    saved = {team.slot: team for team in ProfileStore(tmp_path / 'user-team-profiles.json').load()}
    assert saved[2].graces == ('0++', '4++', '5++') and saved[2].grace_stock == 90 and saved[2].grace_budget == 1000000
    assert saved[2].keywords == frozenset({'Charge'}) and saved[2].deployment == ('Yi Sang',)
    # "No graces" is a plan too: the team has one, and it buys nothing.
    apply_builds(tmp_path, collect_builds(nodes(mirror_starlight.team_nodes(3), 'none')))
    empty = ProfileStore(tmp_path / 'user-team-profiles.json').load()[1]
    assert empty.graces == () and empty.grace_budget == 1000000
    assert collect_builds(nodes(names, 'keep')) == {}
    with pytest.raises(ValueError):
        collect_builds(nodes(names, 'sometimes'))


def header(owned, available):
    return [Text('Owned', (1082, 55, 66, 30), 1.0), Text(owned, (1160, 53, 132, 36), 1.0),
            Text('Available', (1374, 59, 74, 22), 1.0), Text(available, (1478, 51, 98, 36), .85),
            Text('250', (1658, 49, 84, 38), 1.0)]


def test_the_counters_are_read_on_both_sides_of_the_allowance():
    # As the page printed them: within the allowance, and 90 past it.
    assert grace_vision.available_starlight(header('3607', '*50'), SIZE) == 50
    assert grace_vision.owned_starlight(header('3607', '*50'), SIZE) == (3607, 0)
    assert grace_vision.available_starlight(header('3607-90', '*0+90'), SIZE) == -90
    assert grace_vision.owned_starlight(header('3607-90', '*0+90'), SIZE) == (3607, 90)
    # A purchase lowers the one number by its cost across zero: 50, then a card of 90.
    assert 50 - 90 == grace_vision.available_starlight(header('3607-40', '0+40'), SIZE)
    # Unread is not zero.
    assert grace_vision.owned_starlight([Text('Owned', (1082, 55, 66, 30), 1.0)], SIZE) is None
    assert grace_vision.owned_starlight(header('about', '*50'), SIZE) is None


def test_a_cards_level_is_its_cost_and_its_buttons_sit_under_it():
    assert [grace_vision.cost_at(card, 2) for card in range(1, 11)] == [30, 30, 60, 60, 90, 90, 120, 120, 150, 180]
    assert [grace_vision.cost_at(card, 1) for card in range(1, 11)] == [20, 20, 40, 40, 60, 60, 80, 80, 100, 120]
    assert grace_vision.level_of(2, 10) == 0 and grace_vision.level_of(2, 20) == 1 and grace_vision.level_of(2, 30) == 2
    assert grace_vision.level_of(2, 25) is None                 # no level costs that: the table is out of date
    # Card 2's box in the 1920 frame; its + read at [572,510,16,20] and its ++ at [682,508,34,22].
    box = (505, 226, 278, 340)
    plus, plusplus = star_vision.level_box(box, 1), star_vision.level_box(box, 2)
    assert plus[0] <= 580 <= plus[0] + plus[2] and plus[1] <= 520 <= plus[1] + plus[3]
    assert plusplus[0] <= 699 <= plusplus[0] + plusplus[2] and plusplus[1] <= 519 <= plusplus[1] + plusplus[3]
    # Neither button overlaps the body press that selects the card.
    body = star_vision.target_box(box)
    assert body[1] + body[3] < plus[1]


def test_a_level_press_buys_nothing_and_a_purchase_past_the_allowance_needs_the_stock(tmp_path):
    controls = {'graces.enter_button': [1740, 986, 102, 42]}
    level = plan_step('STAR_GRACES', controls=controls, graces=dict(level_card=5, level=2, box=[1592, 502, 56, 26], available=120))
    assert level['action'] == 'click' and level['target'] == [1592, 502, 56, 26]
    assert level['detail'] == dict(level_card=5, level=2) and 'card' not in level['detail']
    buy = plan_step('STAR_GRACES', controls=controls, graces=dict(card=5, point=(1640, 330), available=120))
    assert buy['detail'] == dict(card=5)
    books = GraceTransaction(tmp_path / 'grace.json')
    books.begin('run', [1, 5, 6], 1000000, 'entry.png')
    books.intent(1, 30, 120, 'f1.json')
    books.observe(90, 'f2.json')
    books.intent(5, 90, 90, 'f3.json')
    books.observe(0, 'f4.json')
    # Card 6 at ++ costs 90 and nothing is left of the allowance: refused without the stock,
    with pytest.raises(ValueError, match='not authorized'):
        books.intent(6, 90, 0, 'f5.json')
    # refused when the stock allowed is too small, and booked when it covers the card.
    with pytest.raises(ValueError, match='not authorized'):
        books.intent(6, 90, 0, 'f5.json', stock=60)
    books.intent(6, 90, 0, 'f5.json', stock=90)
    books.observe(-90, 'f6.json')                       # the page then prints 0+90
    assert books.data['selected'] == [1, 5, 6] and books.data['spent'] == 210 and books.data['available'] == -90


def test_the_loop_sets_the_level_before_it_selects_and_counts_the_stock():
    source = (ROOT / 'src/maalimbus/runner.py').read_text(encoding='utf-8')
    for needle in ("costs[index - 1] = cost_at(index, levels.get(index, 0))",
                   "total_budget = min(settings.grace_budget, spent + max(0, available) + stock_room)",
                   "stock_room = max(0, min(int(settings.grace_stock), owned[0]) - owned[1])",
                   "press = asked if asked else shown",
                   "'grace_level_not_set_after_two_presses'",
                   "stock=int(state.get('grace_stock_room') or 0)"):
        assert needle in source, needle


SHOP_COUNTER = (852, 174, 78, 56)


def shop(cost):
    return dict(scene='SHOP', size=list(SIZE), ocr=[
        dict(text='455', box=list(SHOP_COUNTER), score=.99),
        dict(text='Perversion', box=[1310, 500, 110, 26], score=.99),
        dict(text='157', box=[1340, 462, 60, 30], score=.99),
        dict(text='Refresh', box=[1470, 150, 110, 30], score=.99),
        dict(text=cost, box=[1500, 215, 40, 26], score=.99)])


def test_only_free_refreshes_presses_a_refresh_that_prints_zero_and_no_other():
    from maalimbus.runner import shop_state
    wanted = ['A Gift That Is Not On The Shelf']
    assert shop_state(shop('40'), wanted)['refresh']['cost'] == 40
    assert shop_state(shop('40'), wanted, free_refresh_only=True)['refresh'] is None
    assert shop_state(shop('0'), wanted, free_refresh_only=True)['refresh']['cost'] == 0
    # A price that was not read is not zero.
    unread = shop('40')
    unread['ocr'] = unread['ocr'][:-1]
    assert shop_state(unread, wanted, free_refresh_only=True)['refresh'] is None
    task = next(task for task in PI['task'] if task['name'] == 'mirror_loop')
    assert task['option'].index('mirror_shop_refresh_paid') == task['option'].index('mirror_shop_refresh_limit') + 1
    assert [case['name'] for case in PI['option']['mirror_shop_refresh_paid']['cases']] == ['any', 'free']
    assert NODES['MirrorShopRefreshPaid']['attach'] == dict(free_only=False)

    def get(name):
        return {'MirrorInitialKeyword': dict(attach=dict(keyword='saved')),
                'MirrorGiftSearch': dict(attach=dict(mode='saved')),
                'MirrorBattleAssignment': dict(attach=dict(mode='saved')),
                'MirrorShopRefreshPaid': dict(attach=dict(free_only=True))}.get(name, dict(attach={}))
    assert collect_task_options(get)['shop_free_refresh_only'] is True
