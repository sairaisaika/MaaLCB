"""Four things the user asked for on 2026-11-27, looking at the installed app.

* The step bound is not a setting: a number of loop steps means nothing to a player.
* The keyword choices are the game's own dictionary, in the game's own order (the shop's
  Keyword Refresh dialog; the Identity filter panel for what describes an Identity).
* Starlight belongs to the team: it is set where the team's systems and order are set,
  and the Mirror task only chooses the source.
* A task reads the deployment orders off the game's team screen, team by team down the
  TEAMS list, and records them; a team's settings can choose to use its record. (The
  first version read one frame into the profile, the second put a choice in the settings
  that read during the next run; the user then set this shape: read in the task, choose
  in the settings.)
"""
import importlib.util
import json
from pathlib import Path

import pytest

from maalimbus import game_vocabulary, team_order_task
from maalimbus.global_settings import apply_builds, collect_builds
from maalimbus.mirror_starlight import apply as apply_stars, resolve
from maalimbus.mirror_task_options import collect as collect_task_options
from maalimbus.policies import Team
from maalimbus.storage import KEYWORDS, SINNERS, ProfileStore, write_json
from maalimbus.task_preferences import TASKS

ROOT = Path(__file__).resolve().parents[1]
PI = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
NODES = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))


def test_the_step_bound_is_not_offered_and_a_pipeline_without_it_still_starts():
    mirror = next(task for task in PI['task'] if task['name'] == 'mirror_loop')
    assert 'mirror_run_bounds' not in mirror['option'] and 'mirror_run_bounds' not in PI['option']
    for language in ('zh_cn', 'en_us', 'ja_jp'):
        text = json.loads((ROOT / 'assets/i18n' / (language + '.json')).read_text(encoding='utf-8'))
        assert not [key for key in text if key.startswith('mirror_run_bounds')]

    def get(name):
        if name == 'MirrorRunBounds':
            raise KeyError(name)
        return {'MirrorInitialKeyword': dict(attach=dict(keyword='saved')),
                'MirrorGiftSearch': dict(attach=dict(mode='saved')),
                'MirrorRunCount': dict(attach=dict(run_count=3)),
                'MirrorBattleAssignment': dict(attach=dict(mode='saved'))}.get(name, dict(attach={}))
    assert collect_task_options(get) == dict(run_count=3)
    # The net under the loop is in the agent, above anything the asked runs can use.
    source = (ROOT / 'agent/recognition.py').read_text(encoding='utf-8')
    assert "window = max(window, 4000, 1500 * int(getattr(settings, 'run_count', 0) or 0))" in source


def test_the_keyword_choices_are_the_games_dictionary_in_the_games_order():
    assert game_vocabulary.GIFT_KEYWORDS == (
        'Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge', 'Slash', 'Pierce', 'Blunt')
    assert game_vocabulary.SYSTEMS == game_vocabulary.GIFT_KEYWORDS[:7]
    assert len(game_vocabulary.AFFINITIES) == 7 and set(game_vocabulary.TEAM_CHOICES) <= set(KEYWORDS)
    spec = importlib.util.spec_from_file_location('import_wiki_gift_facts_vocabulary',
                                                  ROOT / 'tools/import_wiki_gift_facts.py')
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)
    assert importer.KEYWORDS == game_vocabulary.GIFT_KEYWORDS and importer.SYSTEMS == game_vocabulary.SYSTEMS
    assert tuple(sin.capitalize() for sin in importer.SINS) == game_vocabulary.AFFINITIES
    for slot in (1, 20, 40):
        cases = [case['name'] for case in PI['option']['global_team_%d_keywords' % slot]['cases']]
        assert tuple(cases) == game_vocabulary.TEAM_CHOICES
    cases = [case['name'] for case in PI['option']['mirror_initial_keyword']['cases']]
    assert cases == ['saved'] + [word.lower() for word in game_vocabulary.TEAM_CHOICES]


def star_nodes(slot, cards, budget, mode='choose'):
    prefix = 'Global_global_team_%d' % slot
    chosen = {prefix + '_stars': dict(attach=dict(mode=mode)),
              prefix + '_star_cards': dict(attach={'star_%d' % card: True for card in cards}),
              prefix + '_star_budget': dict(attach=dict(budget=budget))}

    def get(name):
        if name in chosen:
            return chosen[name]
        if name.endswith(('_keywords', '_star_cards')):
            return dict(attach={})
        if name.endswith('_star_budget'):
            return dict(attach=dict(budget='0'))
        if name.endswith('_order_text'):
            return dict(attach=dict(order=''))
        return dict(attach=dict(mode='keep'))
    return get


def test_a_teams_starlight_is_set_with_the_team_and_followed_by_default(tmp_path):
    for slot in (1, 40):
        name = 'global_team_%d' % slot
        section = next(s for s in PI['setting'] if s['name'] == name)
        assert section['option'] == [name + '_systems', name + '_order', name + '_stars']
        assert name + '_stars' in PI['global_option']
        assert [case['name'] for case in PI['option'][name + '_star_cards']['cases']] == [str(n) for n in range(10)]
        for suffix in ('_stars', '_star_cards', '_star_budget'):
            assert 'Global_' + name + suffix in NODES
    # The task chooses the source only; the per-team editor it used to carry is gone.
    source = PI['option']['mirror_star_source']
    assert source['default_case'] == 'team'
    assert not [name for name in PI['option'] if name.startswith('mirror_star_team_')]
    assert all('mirror_star_team_editor' not in case.get('option', ()) for case in source['cases'])

    edits = collect_builds(star_nodes(2, (0, 3, 5), '120'))
    assert edits == {'2': dict(keywords='keep', order='keep', stars=dict(choices=[0, 3, 5], budget=120))}
    assert collect_builds(star_nodes(2, (0,), '5', mode='keep')) == {}
    write_json(tmp_path / 'user-team-profiles.json', dict(version=1, teams=[]))
    ProfileStore(tmp_path / 'user-team-profiles.json').save(
        [Team(2, frozenset({'Charge'}), deployment=tuple(SINNERS)), Team(3, frozenset({'Burn'}))])
    assert apply_builds(tmp_path, edits) == [2]
    saved = {team.slot: team for team in ProfileStore(tmp_path / 'user-team-profiles.json').load()}
    assert saved[2].graces == ('0', '3', '5') and saved[2].grace_budget == 120
    assert saved[2].keywords == frozenset({'Charge'}) and saved[2].deployment == tuple(SINNERS)   # the rest is kept
    # "Follow the team": the team with a plan uses it, the team without one keeps the saved rule.
    apply_stars(tmp_path, 'team', dict(choices=[], budget=0))
    assert resolve(tmp_path, 2) == dict(graces='1,4,6', grace_budget=120, grace_auto=False, star_source='team', team=2)
    assert resolve(tmp_path, 3) is None
    with pytest.raises(ValueError, match='decimal digits'):
        collect_builds(star_nodes(2, (0,), 'many'))
    with pytest.raises(ValueError, match='Star choices'):
        apply_builds(tmp_path, {'2': dict(keywords='keep', order='keep', stars=dict(choices=[11], budget=1))})


class TeamScreen:
    """The team screen outside a dungeon: a list of six visible TEAMS rows and twelve numbered cards."""

    def __init__(self, orders, selected=1, top=1, visible=6, ignore_press=()):
        self.orders, self.selected, self.top, self.visible = dict(orders), selected, top, visible
        self.ignore_press, self.presses, self.drags = set(ignore_press), [], 0

    def observe(self):
        rows = [dict(text='TEAMS #%d' % slot, box=[110, 480 + 60 * index, 130, 36], score=.99)
                for index, slot in enumerate(range(self.top, min(40, self.top + self.visible - 1) + 1))]
        return dict(size=[1920, 1080], ocr=rows, shown=self.selected)

    def team_state(self, record):
        return dict(numbers=list(self.orders.get(record['shown'], [None] * 12)), saved_team=record['shown'])

    def press(self, box):
        slot = self.top + round((box[1] - 480) / 60)
        self.presses.append(slot)
        if slot not in self.ignore_press:
            self.selected = slot
        return self.observe()

    def drag(self, start, to):
        self.drags += 1
        down = to[1] < start[1]
        self.top = max(1, min(40 - self.visible + 1, self.top + (3 if down else -3)))
        return self.observe()


ORDER_A = [12, 10, 4, 11, 5, 9, 3, 2, 7, 1, 8, 6]      # the user's screenshot of TEAMS #1
ORDER_B = [4, 6, 1, 2, 8, 12, 5, 9, 3, 10, 11, 7]


def run_task(tmp_path, screen, count):
    return team_order_task.read(tmp_path, count, observe=screen.observe, press=screen.press, drag=screen.drag,
                                team_state=screen.team_state, frame=lambda: tmp_path / 'frame-0001.json')


def test_the_task_goes_down_the_team_list_and_records_each_team_under_its_own_number(tmp_path):
    from maalimbus import team_order_record
    assert 'read_team_order' in TASKS
    task = next(task for task in PI['task'] if task['name'] == 'read_team_order')
    assert task['entry'] == 'ReadTeamOrderTask' and task['option'] == ['read_team_count']
    assert [case['name'] for case in PI['option']['read_team_count']['cases']] == [str(n) for n in range(1, 41)]
    assert NODES['ReadTeamOrderCount']['attach'] == dict(count=1)
    screen = TeamScreen({1: ORDER_A, 2: ORDER_B, 3: list(range(1, 13))}, selected=2)
    result = run_task(tmp_path, screen, 3)
    assert result['passed'] and result['reason'] == 'team_orders_recorded' and result['input_sent']
    assert [one['slot'] for one in result['recorded']] == [1, 2, 3] and not result['failed']
    # Team 2 was showing: team 1's row was pressed first, then 2 and 3 in turn. No card was pressed.
    assert screen.presses == [1, 2, 3] and screen.drags == 0
    # Team 1's reading is under team 1: position 1 is the card that printed 1, the tenth, Sinclair.
    assert team_order_record.latest(tmp_path, 1)['order'][:3] == ['Sinclair', 'Ishmael', 'Heathcliff']
    assert team_order_record.latest(tmp_path, 2)['order'][0] == 'Don Quixote'
    assert team_order_record.latest(tmp_path, 3)['order'] == list(SINNERS)
    assert team_order_record.latest(tmp_path, 4) is None
    # Recording is not saving: no team's own settings were touched.
    assert not (tmp_path / 'user-team-profiles.json').exists()
    assert '队伍 1：辛克莱' in result['message'] and '使用录入记录' in result['message']


def test_a_team_below_the_visible_rows_is_reached_by_dragging_the_list(tmp_path):
    from maalimbus import team_order_record
    screen = TeamScreen({slot: ORDER_B for slot in range(1, 9)})
    result = run_task(tmp_path, screen, 8)
    assert result['passed'] and [one['slot'] for one in result['recorded']] == list(range(1, 9))
    assert screen.drags >= 1 and screen.presses == list(range(2, 9))      # team 1 was already showing
    assert team_order_record.latest(tmp_path, 8)['positions'][0] == 3


def test_a_team_that_cannot_be_read_is_skipped_by_name_and_the_others_are_still_recorded(tmp_path):
    from maalimbus import team_order_record
    partial = [1, 2, 3, None, None, None, None, None, None, None, None, None]     # only three picked
    screen = TeamScreen({1: ORDER_A, 2: partial, 3: ORDER_B, 4: ORDER_B}, ignore_press={4})
    result = run_task(tmp_path, screen, 4)
    assert not result['passed'] and result['reason'] == 'team_orders_partly_recorded'
    assert [one['slot'] for one in result['recorded']] == [1, 3]
    assert [(one['slot'], one['reason']) for one in result['failed']] == [
        (2, 'team_order_numbers_unread'), (4, 'team_order_row_press_did_not_select')]
    assert team_order_record.latest(tmp_path, 2) is None and team_order_record.latest(tmp_path, 4) is None
    assert '队伍 2（编号没有读全' in result['message'] and '队伍 4（' in result['message']
    assert screen.presses.count(4) == team_order_task.PRESSES


def test_a_page_without_cards_records_nothing_and_a_dungeon_page_is_the_runs_team(tmp_path):
    from maalimbus import team_order_record
    blank = TeamScreen({})
    result = run_task(tmp_path, blank, 2)
    assert not result['passed'] and result['reason'] == 'team_order_cards_not_visible' and not result['input_sent']
    # Inside a dungeon: twelve numbers, no list and no TEAMS #n (replayed on pi-20261126-233844).
    dungeon = dict(observe=lambda: dict(size=[1920, 1080], ocr=[]), press=None, drag=None,
                   team_state=lambda record: dict(numbers=list(ORDER_B), saved_team=None),
                   frame=lambda: tmp_path / 'frame-0002.json')
    nobody = team_order_task.read(tmp_path, 3, **dungeon)
    assert not nobody['passed'] and nobody['reason'] == 'team_order_team_number_unread'
    write_json(tmp_path / 'user-run-ledger.json', dict(active=dict(team=2)))
    inside = team_order_task.read(tmp_path, 3, **dungeon)
    assert inside['passed'] and inside['recorded'] == [dict(slot=2, positions=team_order_record.latest(tmp_path, 2)['positions'])]
    assert inside['slot_source'] == 'run_in_progress' and not inside['input_sent']
    with pytest.raises(ValueError, match='1..40'):
        team_order_task.read(tmp_path, 0, **dungeon)


def order_nodes(slot, mode):
    prefix = 'Global_global_team_%d' % slot

    def get(name):
        if name == prefix + '_order':
            return dict(attach=dict(mode=mode))
        if name.endswith(('_keywords', '_star_cards')):
            return dict(attach={})
        if name.endswith('_order_text'):
            return dict(attach=dict(order=''))
        if name.endswith('_star_budget'):
            return dict(attach=dict(budget='0'))
        return dict(attach=dict(mode='keep'))
    return get


def test_a_teams_settings_can_take_its_recorded_order_and_keep_what_they_have_without_one(tmp_path, capsys):
    from maalimbus import team_order_record
    for slot in (1, 40):
        cases = PI['option']['global_team_%d_order' % slot]['cases']
        assert [case['name'] for case in cases] == ['keep', 'game', 'record', 'custom']
    ProfileStore(tmp_path / 'user-team-profiles.json').save(
        [Team(2, frozenset({'Charge'}), deployment=tuple(SINNERS)), Team(3, frozenset(), deployment=tuple(SINNERS))])
    team_order_record.record(tmp_path, 2, ORDER_B, tmp_path / 'frame-0001.json')
    edits = collect_builds(order_nodes(2, 'record'))
    assert edits == {'2': dict(keywords='keep', order='record')}
    assert apply_builds(tmp_path, edits) == [2]
    saved = {team.slot: team for team in ProfileStore(tmp_path / 'user-team-profiles.json').load()}
    assert list(saved[2].deployment) == team_order_record.latest(tmp_path, 2)['order']
    assert saved[2].deployment[0] == 'Don Quixote' and saved[2].keywords == frozenset({'Charge'})
    assert apply_builds(tmp_path, edits) == []                 # the same record again changes nothing
    # No record for team 3: its order stays, the run is not refused, and the log says what to do.
    assert apply_builds(tmp_path, collect_builds(order_nodes(3, 'record'))) == []
    assert ProfileStore(tmp_path / 'user-team-profiles.json').load()[1].deployment == tuple(SINNERS)
    assert '队伍 3' in capsys.readouterr().out
    # The half-day version that read during the next run is gone.
    source = (ROOT / 'src/maalimbus/runner.py').read_text(encoding='utf-8')
    assert 'save_if_armed' not in source and not hasattr(team_order_record, 'arm')
