"""Four things the user asked for on 2026-11-27, looking at the installed app.

* The step bound is not a setting: a number of loop steps means nothing to a player.
* The keyword choices are the game's own dictionary, in the game's own order (the shop's
  Keyword Refresh dialog; the Identity filter panel for what describes an Identity).
* Starlight belongs to the team: it is set where the team's systems and order are set,
  and the Mirror task only chooses the source.
* A task reads the deployment order off the team page the player has open and saves it.
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


def team_page(numbers, slot):
    return lambda record, controls: dict(numbers=list(numbers), saved_team=slot)


def test_the_order_on_the_team_page_is_saved_for_the_team_it_shows(tmp_path):
    assert 'read_team_order' in TASKS
    assert any(task['name'] == 'read_team_order' and task['entry'] == 'ReadTeamOrderTask' for task in PI['task'])
    assert NODES['ReadTeamOrderTask']['custom_action_param'] == dict(task='read_team_order')
    # The user's screenshot: card i carries the number printed on it.
    numbers = [12, 10, 4, 11, 5, 9, 3, 2, 7, 1, 8, 6]
    result = team_order_task.read(tmp_path, dict(size=[1920, 1080]), {}, tmp_path / 'frame-0001.json',
                                  team_state=team_page(numbers, 1))
    assert result['passed'] and result['reason'] == 'team_order_saved' and not result['input_sent']
    # Position 1 is the card that printed 1: the tenth card, Sinclair.
    assert result['order'][:3] == ['Sinclair', 'Ishmael', 'Heathcliff'] and result['order'][-1] == 'Yi Sang'
    saved = ProfileStore(tmp_path / 'user-team-profiles.json').load()
    assert [team.slot for team in saved] == [1] and list(saved[0].deployment) == result['order']
    records = json.loads((tmp_path / 'user-team-order-records.json').read_text(encoding='utf-8'))
    assert records['teams']['1']['positions'][:3] == [10, 8, 7]
    again = team_order_task.read(tmp_path, {}, {}, None, team_state=team_page(numbers, 1))
    assert again['passed'] and again['reason'] == 'team_order_unchanged'
    # Another team's systems are not touched by saving an order next to them.
    ProfileStore(tmp_path / 'user-team-profiles.json').save(list(saved) + [Team(4, frozenset({'Burn'}))])
    team_order_task.read(tmp_path, {}, {}, None, team_state=team_page(list(range(1, 13)), 4))
    after = {team.slot: team for team in ProfileStore(tmp_path / 'user-team-profiles.json').load()}
    assert after[4].keywords == frozenset({'Burn'}) and after[4].deployment == tuple(SINNERS)
    assert list(after[1].deployment) == result['order']


@pytest.mark.parametrize('numbers, slot, reason', [
    ([None] * 12, 1, 'team_order_cards_not_visible'),
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, None], 1, 'team_order_numbers_unread'),
    ([1, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], 1, 'team_order_numbers_unread'),
    (list(range(1, 13)), None, 'team_order_team_number_unread'),
])
def test_a_partial_reading_saves_nothing_and_says_what_was_missing(tmp_path, numbers, slot, reason):
    result = team_order_task.read(tmp_path, {}, {}, None, team_state=team_page(numbers, slot))
    assert not result['passed'] and result['reason'] == reason and result['message']
    assert not (tmp_path / 'user-team-profiles.json').exists()
    assert team_order_task.read(tmp_path, {}, {}, None, team_state=lambda record, controls: None)['reason'] == \
        'team_order_cards_not_visible'


def test_inside_a_dungeon_the_page_prints_no_team_number_and_the_run_names_the_team(tmp_path):
    # Replayed on eight pre-battle frames of pi-20261126-233844: twelve numbers, no TEAMS #n.
    numbers = [4, 6, 1, 2, 8, 12, 5, 9, 3, 10, 11, 7]
    ProfileStore(tmp_path / 'user-team-profiles.json').save([Team(2, frozenset({'Charge'}))])
    write_json(tmp_path / 'user-run-ledger.json', dict(active=dict(team=2)))
    result = team_order_task.read(tmp_path, {}, {}, None, team_state=team_page(numbers, None))
    assert result['passed'] and result['reason'] == 'team_order_saved' and result['slot_source'] == 'run_in_progress'
    assert result['slot'] == 2 and result['order'][0] == 'Don Quixote' and '正在进行' in result['message']
    saved = ProfileStore(tmp_path / 'user-team-profiles.json').load()[0]
    assert list(saved.deployment) == result['order'] and saved.keywords == frozenset({'Charge'})
    # A page that does print the number is believed over the ledger.
    other = team_order_task.read(tmp_path, {}, {}, None, team_state=team_page(numbers, 5))
    assert other['slot'] == 5 and other['slot_source'] == 'page'


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


def test_read_it_once_is_a_choice_of_the_order_dropdown_and_saves_what_the_run_reads(tmp_path):
    # The user looked for the reading in this dropdown (2026-11-27): "这里面东西没加啊".
    from maalimbus import team_order_record
    for slot in (1, 40):
        cases = PI['option']['global_team_%d_order' % slot]['cases']
        assert [case['name'] for case in cases] == ['keep', 'game', 'read', 'custom']
    ProfileStore(tmp_path / 'user-team-profiles.json').save(
        [Team(2, frozenset({'Charge'}), deployment=tuple(SINNERS)), Team(3, frozenset())])
    edits = collect_builds(order_nodes(2, 'read'))
    assert edits == {'2': dict(keywords='keep', order='read')}
    assert apply_builds(tmp_path, edits) == [2]
    # Like "follow the game" the saved order is forgotten, and the team is marked.
    assert ProfileStore(tmp_path / 'user-team-profiles.json').load()[0].deployment == ()
    assert json.loads((tmp_path / team_order_record.CAPTURE).read_text(encoding='utf-8'))['slots'] == [2]
    numbers = [4, 6, 1, 2, 8, 12, 5, 9, 3, 10, 11, 7]
    entry = team_order_record.record(tmp_path, 2, numbers, tmp_path / 'frame-0001.json')
    assert team_order_record.save_if_armed(tmp_path, 3, entry) is False        # another team was not asked for
    assert team_order_record.save_if_armed(tmp_path, 2, entry) is True
    saved = ProfileStore(tmp_path / 'user-team-profiles.json').load()[0]
    assert list(saved.deployment) == entry['order'] and saved.deployment[0] == 'Don Quixote'
    assert saved.keywords == frozenset({'Charge'})
    # Once: the mark is used up, and choosing another order removes a mark that was not.
    assert team_order_record.save_if_armed(tmp_path, 2, entry) is False
    apply_builds(tmp_path, collect_builds(order_nodes(3, 'read')))
    apply_builds(tmp_path, collect_builds(order_nodes(3, 'game')))
    assert json.loads((tmp_path / team_order_record.CAPTURE).read_text(encoding='utf-8'))['slots'] == []
    source = (ROOT / 'src/maalimbus/runner.py').read_text(encoding='utf-8')
    assert 'team_order_record.save_if_armed(' in source and 'deployment_order_saved_from_game' in source
