"""Four things the user asked for on 2026-11-27, looking at the installed app.

* The step bound is not a setting: a number of loop steps means nothing to a player.
* The keyword choices are the game's own dictionary, in the game's own order (the shop's
  Keyword Refresh dialog; the Identity filter panel for what describes an Identity).
* Starlight belongs to the team: it is set where the team's systems and order are set,
  and the Mirror task only chooses the source.
* A task reads the deployment orders off the game's team screen, team by team down the
  TEAMS list, and writes each into that team's "deployment order" in the settings the
  player sees. (Three earlier shapes missed it: one frame into the profile; a settings
  choice that read during the next run; a file of records with "use the record". The
  user's answer to the last: the order belongs in the settings themselves.)
"""
import importlib.util
import json
from pathlib import Path

import pytest

from maalimbus import game_vocabulary, team_order_task
from maalimbus.global_settings import apply_builds, collect_builds
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


def test_starlight_is_set_with_the_team_and_the_task_only_chooses_whose_plan():
    # The plan itself, its levels and the stock are covered in tests/test_mirror_starlight.py.
    for slot in (1, 40):
        name = 'global_team_%d' % slot
        section = next(s for s in PI['setting'] if s['name'] == name)
        assert section['option'] == [name + '_systems', name + '_order', name + '_stars']
        assert name + '_stars' in PI['global_option']
    source = PI['option']['mirror_star_source']
    assert source['default_case'] == 'team' and [case['name'] for case in source['cases']] == ['team', 'task']
    assert not [name for name in PI['option'] if name.startswith('mirror_star_team_')]


class TeamScreen:
    """The team screen outside a dungeon: a list of six visible TEAMS rows and twelve numbered cards."""

    def __init__(self, orders, selected=1, top=1, visible=6, ignore_press=()):
        self.orders, self.selected, self.top, self.visible = dict(orders), selected, top, visible
        self.ignore_press, self.presses, self.drags = set(ignore_press), [], 0
        self.counter = {}

    def observe(self):
        rows = [dict(text='TEAMS #%d' % slot, box=[110, 480 + 60 * index, 130, 36], score=.99)
                for index, slot in enumerate(range(self.top, min(40, self.top + self.visible - 1) + 1))]
        return dict(size=[1920, 1080], ocr=rows, shown=self.selected)

    def team_state(self, record):
        numbers = list(self.orders.get(record['shown'], [None] * 12))
        picked = sum(type(number) is int for number in numbers)
        return dict(numbers=numbers, saved_team=record['shown'],
                    participants=self.counter.get(record['shown'], (picked, 12)))

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


class Settings:
    """The client's configuration as its local service hands it out and takes it back."""

    def __init__(self, tmp_path, enabled=True, answers=True):
        self.directory = tmp_path / 'client'
        self.directory.mkdir(exist_ok=True)
        self.config = dict(version='1.0', instances=[dict(id='a')], settings=dict(language='zh-CN'),
                           globalOptionValues={'global_team_1_systems': dict(type='select', caseName='keep'),
                                               'global_team_9_order': dict(type='select', caseName='game')})
        write_json(self.directory / 'mxu-MaaLimbus.json',
                   dict(settings=dict(language='zh-CN', webServerEnabled=enabled, webServerPort=12711)))
        self.answers, self.calls = answers, []

    def ask(self, port, method='GET', body=None):
        self.calls.append((port, method))
        if not self.answers:
            raise OSError('connection refused')
        if method == 'PUT':
            self.config = json.loads(json.dumps(body))
            return dict(ok=True)
        return json.loads(json.dumps(self.config))

    def write(self, lines):
        from maalimbus import mxu_settings
        return mxu_settings.write_orders(self.directory, lines, ask=self.ask)

    def order(self, slot):
        values = self.config['globalOptionValues']
        return (values.get('global_team_%d_order' % slot, {}).get('caseName'),
                values.get('global_team_%d_order_text' % slot, {}).get('values', {}).get('order'))


def run_task(tmp_path, screen, count, settings=None):
    settings = settings or Settings(tmp_path)
    result = team_order_task.read(tmp_path, count, observe=screen.observe, press=screen.press, drag=screen.drag,
                                  team_state=screen.team_state, frame=lambda: tmp_path / 'frame-0001.json',
                                  write=settings.write)
    return result, settings


def test_the_task_goes_down_the_team_list_and_writes_each_order_into_that_teams_settings(tmp_path):
    assert 'read_team_order' in TASKS
    task = next(task for task in PI['task'] if task['name'] == 'read_team_order')
    assert task['entry'] == 'ReadTeamOrderTask' and task['option'] == ['read_team_count']
    assert [case['name'] for case in PI['option']['read_team_count']['cases']] == [str(n) for n in range(1, 41)]
    assert NODES['ReadTeamOrderCount']['attach'] == dict(count=1)
    screen = TeamScreen({1: ORDER_A, 2: ORDER_B, 3: list(range(1, 13))}, selected=2)
    result, settings = run_task(tmp_path, screen, 3)
    assert result['passed'] and result['reason'] == 'team_orders_written_to_settings' and result['input_sent']
    assert [one['slot'] for one in result['recorded']] == [1, 2, 3] and not result['failed']
    # Team 2 was showing: team 1's row was pressed first, then 2 and 3 in turn, and at the end
    # the row of team 2 again, so the game is left on the team the player had selected.
    assert screen.presses == [1, 2, 3, 2] and screen.drags == 0
    assert screen.selected == 2 and result['shown_at_start'] == 2 and result['restored'] is True
    # Team 1's order is in team 1's own setting, as the line a player would have typed:
    # position 1 is the card that printed 1, the tenth, Sinclair.
    assert settings.order(1) == ('custom', '辛克莱 以实玛利 希斯克利夫 堂吉诃德 默尔索 格里高尔 罗佳 奥提斯 鸿璐 浮士德 良秀 李箱')
    assert settings.order(2)[1].startswith('堂吉诃德 良秀') and settings.order(3)[0] == 'custom'
    # Everything else in the client's configuration went back as it came.
    assert settings.config['globalOptionValues']['global_team_1_systems'] == dict(type='select', caseName='keep')
    assert settings.order(9) == ('game', None) and settings.config['instances'] == [dict(id='a')]
    assert settings.calls == [(12711, 'GET'), (12711, 'PUT')]
    # The line is one the settings read back as the same order.
    from maalimbus.global_settings import parse_order
    assert parse_order(settings.order(1)[1])[:3] == ('Sinclair', 'Ishmael', 'Heathcliff')
    assert '写进了总设置' in result['message'] and '队伍 1：辛克莱' in result['message']
    # The task writes the settings, not a team's saved profile: the next Mirror task applies them.
    assert not (tmp_path / 'user-team-profiles.json').exists()


def test_a_team_below_the_visible_rows_is_reached_by_dragging_the_list(tmp_path):
    screen = TeamScreen({slot: ORDER_B for slot in range(1, 9)})
    result, settings = run_task(tmp_path, screen, 8)
    assert result['passed'] and [one['slot'] for one in result['recorded']] == list(range(1, 9))
    # Team 1 was already showing; after team 8 the list is dragged back and team 1 selected again.
    assert screen.drags >= 2 and screen.presses == list(range(2, 9)) + [1] and screen.selected == 1
    assert settings.order(8)[0] == 'custom'


def test_a_team_that_cannot_be_read_is_skipped_by_name_and_the_others_are_still_written(tmp_path):
    # Four numbers on the cards while the page's counter says five are picked: one was not read.
    partial = [1, 2, 3, None, 4, None, None, None, None, None, None, None]
    screen = TeamScreen({1: ORDER_A, 2: partial, 3: ORDER_B, 4: ORDER_B}, ignore_press={4})
    screen.counter[2] = (5, 12)
    result, settings = run_task(tmp_path, screen, 4)
    assert not result['passed'] and result['reason'] == 'team_orders_partly_read'
    assert [one['slot'] for one in result['recorded']] == [1, 3]
    assert [(one['slot'], one['reason']) for one in result['failed']] == [
        (2, 'team_order_numbers_unread'), (4, 'team_order_row_press_did_not_select')]
    assert settings.order(1)[0] == 'custom' and settings.order(3)[0] == 'custom'
    assert settings.order(2) == (None, None) and settings.order(4) == (None, None)       # untouched
    assert '队伍 2（编号没有读全' in result['message'] and '队伍 4（' in result['message']
    assert screen.presses.count(4) == team_order_task.PRESSES
    assert screen.selected == 1 and result['restored'] is True


def test_a_team_that_is_not_full_is_written_as_the_sinners_the_game_numbered(tmp_path):
    # Live pi-20261127-032808: TEAMS #2 showed 5/12 with these numbers and was skipped as unread.
    live = [None, None, 1, 2, 5, 3, None, None, 4, None, None, None]
    assert team_order_task.completed(live, (5, 12)) == ([6, 7, 1, 2, 5, 3, 8, 9, 4, 10, 11, 12], 5)
    assert team_order_task.completed(live, None) is None                 # no counter: unread and unpicked look alike
    assert team_order_task.completed(live, (6, 12)) is None              # the counter says a number is missing
    assert team_order_task.completed([None] * 12, (0, 12)) is None
    assert team_order_task.completed(ORDER_A, (12, 12)) == (ORDER_A, 12)
    screen = TeamScreen({1: ORDER_A, 2: live})
    result, settings = run_task(tmp_path, screen, 2)
    assert result['passed'] and result['recorded'][1]['picked'] == 5
    # Only the five the game numbered are written; the settings put the rest after them themselves.
    assert settings.order(2) == ('custom', '堂吉诃德 良秀 鸿璐 罗佳 默尔索')
    from maalimbus.global_settings import parse_order
    assert parse_order(settings.order(2)[1]) == (
        'Don Quixote', 'Ryoshu', 'Hong Lu', 'Rodion', 'Meursault',
        'Yi Sang', 'Faust', 'Heathcliff', 'Ishmael', 'Sinclair', 'Outis', 'Gregor')
    assert '只选了这 5 位' in result['message']


def test_when_the_settings_cannot_be_written_the_lines_are_handed_to_the_player(tmp_path):
    from maalimbus import mxu_settings
    for options, why in ((dict(enabled=False), 'mxu_web_service_is_off'),
                         (dict(answers=False), 'mxu_web_service_did_not_answer')):
        settings = Settings(tmp_path, **options)
        result, _ = run_task(tmp_path, TeamScreen({1: ORDER_A}), 1, settings)
        assert not result['passed'] and result['reason'] == 'team_orders_read_but_not_written'
        assert result['settings']['reason'] == why and result['recorded'][0]['in_settings'] is False
        # Nothing is lost: the line to paste is in the message.
        assert '队伍 1：辛克莱 以实玛利' in result['message'] and '粘贴' in result['message']
        assert settings.calls == ([] if why == 'mxu_web_service_is_off' else [(12711, 'GET')])
    # A configuration the writer does not recognise is not sent back at all.
    odd = Settings(tmp_path)
    odd.config = dict(something='else')
    assert odd.write({1: 'x'}) == dict(written=[], reason='mxu_configuration_not_recognised')
    assert odd.calls == [(12711, 'GET')]
    assert mxu_settings.order_text([10, 8, 7], 3, 'en') == 'Sinclair Ishmael Heathcliff'
    assert mxu_settings.service(tmp_path / 'nowhere') == (None, 'zh')


def test_a_page_without_cards_writes_nothing_and_a_dungeon_page_is_the_runs_team(tmp_path):
    blank = TeamScreen({})
    result, settings = run_task(tmp_path, blank, 2)
    assert not result['passed'] and result['reason'] == 'team_order_cards_not_visible' and not result['input_sent']
    assert settings.calls == []
    # Inside a dungeon: twelve numbers, no list and no TEAMS #n (replayed on pi-20261126-233844).
    inside = Settings(tmp_path)
    dungeon = dict(observe=lambda: dict(size=[1920, 1080], ocr=[]), press=None, drag=None,
                   team_state=lambda record: dict(numbers=list(ORDER_B), saved_team=None),
                   frame=lambda: tmp_path / 'frame-0002.json', write=inside.write)
    nobody = team_order_task.read(tmp_path, 3, **dungeon)
    assert not nobody['passed'] and nobody['reason'] == 'team_order_team_number_unread'
    write_json(tmp_path / 'user-run-ledger.json', dict(active=dict(team=2)))
    result = team_order_task.read(tmp_path, 3, **dungeon)
    assert result['passed'] and result['slot_source'] == 'run_in_progress' and not result['input_sent']
    assert inside.order(2)[0] == 'custom' and inside.order(2)[1].startswith('堂吉诃德 良秀')
    with pytest.raises(ValueError, match='1..40'):
        team_order_task.read(tmp_path, 0, **dungeon)


def test_the_record_mode_and_its_show_and_delete_are_gone():
    # "一些不用的资产就删了": the order lives in the settings now, so nothing chooses a record.
    from maalimbus import global_settings, team_order_record
    for slot in (1, 40):
        assert [case['name'] for case in PI['option']['global_team_%d_order' % slot]['cases']] == ['keep', 'game', 'custom']
    assert 'read_team_action' not in PI['option'] and 'ReadTeamOrderAction' not in NODES
    assert not hasattr(global_settings, 'RECORD') and not hasattr(team_order_task, 'show')
    assert not hasattr(team_order_record, 'latest') and not hasattr(team_order_record, 'forget')
    for language in ('zh_cn', 'en_us', 'ja_jp'):
        text = json.loads((ROOT / 'assets/i18n' / (language + '.json')).read_text(encoding='utf-8'))
        assert not [key for key in text if key.startswith('read_team_action') or key == 'mirror_team_order_record']
    source = (ROOT / 'agent/recognition.py').read_text(encoding='utf-8')
    assert '_team_order_choice' not in source and 'mxu_settings.write_orders(client,lines)' in source
