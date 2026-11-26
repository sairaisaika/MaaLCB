import json
from maalimbus import gui_preferences


def _config(team='2', systems='Charge+Tremor', keyword='saved', search='saved'):
    return {'instances': [{'tasks': [{'optionValues': {
        'mirror_team_mode': {'caseName': 'single'},
        'mirror_single_team': {'caseName': team},
        'mirror_initial_keyword': {'caseName': keyword},
        'mirror_gift_search': {'caseName': search},
        'mirror_run_count': {'caseName': '3'},
    }}]}],
        'globalOptionValues': {
            f'global_team_{team}_systems': {'caseName': 'keep' if systems == 'keep' else 'choose'},
            f'global_team_{team}_keywords': {'caseNames': [] if systems == 'keep' else systems.split('+')}}}


def _write(tmp_path, data):
    path = tmp_path / 'mxu.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_the_players_team_and_systems_are_read(tmp_path):
    prefs = gui_preferences.read(_write(tmp_path, _config()))
    assert prefs['mirror_single_team'] == 2
    assert prefs['team_systems'] == 'Charge+Tremor'
    assert prefs['mirror_initial_keyword'] == 'saved'
    assert prefs['mirror_run_count'] == '3'


def test_keeping_the_saved_systems_is_not_a_system(tmp_path):
    prefs = gui_preferences.read(_write(tmp_path, _config(systems='keep')))
    assert prefs['mirror_single_team'] == 2 and prefs['team_systems'] is None


def test_a_missing_field_is_not_invented(tmp_path):
    data = _config()
    del data['instances'][0]['tasks'][0]['optionValues']['mirror_single_team']
    prefs = gui_preferences.read(_write(tmp_path, data))
    assert prefs['mirror_single_team'] is None
    assert prefs['team_systems'] is None


def test_an_unreadable_file_is_empty_not_a_guess(tmp_path):
    assert gui_preferences.read(tmp_path / 'absent.json') == {}
    broken = tmp_path / 'broken.json'
    broken.write_text('{not json', encoding='utf-8')
    assert gui_preferences.read(broken) == {}


def test_the_evidence_line_names_the_team(tmp_path):
    prefs = gui_preferences.read(_write(tmp_path, _config()))
    assert 'team 2' in gui_preferences.describe(prefs)
    assert 'Charge+Tremor' in gui_preferences.describe(prefs)
    assert gui_preferences.describe({}) == 'no_gui_preferences'

# -- the task is found by name, and its saved choices are replayed whole (2026-11-26) --

INTERFACE = {
    'task': [{'name': 'mirror_loop', 'option': ['mirror_team_mode', 'mirror_shop_coin_reserve', 'mirror_run_count']}],
    'option': {
        'mirror_team_mode': {'type': 'select', 'default_case': 'saved', 'cases': [
            {'name': 'saved', 'pipeline_override': {'MirrorTaskTeamMode': {'attach': {'team_mode': 'saved'}}}},
            {'name': 'single', 'pipeline_override': {'MirrorTaskTeamMode': {'attach': {'team_mode': 'single'}}},
             'option': ['mirror_single_team']}]},
        'mirror_single_team': {'type': 'select', 'default_case': '1', 'cases': [
            {'name': '1', 'pipeline_override': {'MirrorTaskSingleTeam': {'attach': {'slot': 1}}}},
            {'name': '2', 'pipeline_override': {'MirrorTaskSingleTeam': {'attach': {'slot': 2}}}}]},
        'mirror_shop_coin_reserve': {'type': 'select', 'default_case': 'saved', 'cases': [
            {'name': 'saved', 'pipeline_override': {'MirrorShopCoinReserve': {'attach': {'shop_reserve_coins': 'saved'}}}},
            {'name': '0', 'pipeline_override': {'MirrorShopCoinReserve': {'attach': {'shop_reserve_coins': 0}}}}]},
        'mirror_run_count': {'type': 'select', 'default_case': '0', 'cases': [
            {'name': '0', 'pipeline_override': {'MirrorRunCount': {'attach': {'run_count': 0}}}},
            {'name': '3', 'pipeline_override': {'MirrorRunCount': {'attach': {'run_count': 3}}}}]},
    }}


def _listed(values):
    """The layout the interface writes now: a pretask and "open game" before the Mirror task."""
    return {'instances': [{'tasks': [
        {'taskName': '__MXU_PRETASK__launch_emulator', 'optionValues': {'launch_emulator': {'type': 'input'}}},
        {'taskName': 'open_game', 'optionValues': {}},
        {'taskName': 'mirror_loop', 'optionValues': values}]}], 'globalOptionValues': {}}


def test_the_mirror_task_is_found_by_name_not_by_being_first(tmp_path):
    saved = {'mirror_team_mode': {'caseName': 'single', 'type': 'select'},
             'mirror_single_team': {'caseName': '2', 'type': 'select'},
             'mirror_run_count': {'caseName': '3', 'type': 'select'}}
    prefs = gui_preferences.read(_write(tmp_path, _listed(saved)))
    assert prefs['mirror_team_mode'] == 'single' and prefs['mirror_single_team'] == 2
    assert prefs['mirror_run_count'] == '3'
    assert 'team 2' in gui_preferences.describe(prefs)
    # A list with other tasks only holds no Mirror choices at all.
    other = _listed(saved)
    other['instances'][0]['tasks'].pop()
    assert all(value is None for value in gui_preferences.read(_write(tmp_path, other)).values())


def test_the_saved_choices_are_replayed_whole_by_the_rule_of_the_interface(tmp_path):
    import pytest
    interface = tmp_path / 'interface.json'
    interface.write_text(json.dumps(INTERFACE), encoding='utf-8')
    saved = {'mirror_team_mode': {'caseName': 'single'}, 'mirror_single_team': {'caseName': '2'},
             'mirror_shop_coin_reserve': {'caseName': '0'}}
    override, chosen = gui_preferences.task_override(_write(tmp_path, _listed(saved)), interface)
    assert override == {'MirrorTaskTeamMode': {'attach': {'team_mode': 'single'}},
                        'MirrorTaskSingleTeam': {'attach': {'slot': 2}},
                        'MirrorShopCoinReserve': {'attach': {'shop_reserve_coins': 0}},
                        'MirrorRunCount': {'attach': {'run_count': 0}}}
    assert chosen == [('mirror_team_mode', 'single', 'saved'), ('mirror_single_team', '2', 'saved'),
                      ('mirror_shop_coin_reserve', '0', 'saved'), ('mirror_run_count', '0', 'default')]
    # A nested option is only taken under the case that carries it.
    override, chosen = gui_preferences.task_override(_write(tmp_path, _listed({})), interface)
    assert 'MirrorTaskSingleTeam' not in override and all(source == 'default' for _, _, source in chosen)
    # What cannot be replayed is refused by name, never dropped.
    for broken in ({'mirror_run_count': {'caseName': '7'}}, {'mirror_team_mode': {'caseName': 'rotation'}}):
        with pytest.raises(ValueError, match='no case'):
            gui_preferences.task_override(_write(tmp_path, _listed(broken)), interface)
    typed = json.loads(json.dumps(INTERFACE))
    typed['option']['mirror_run_count']['type'] = 'input'
    interface.write_text(json.dumps(typed), encoding='utf-8')
    with pytest.raises(ValueError, match='cannot be replayed'):
        gui_preferences.task_override(_write(tmp_path, _listed(saved)), interface)
    twice = json.loads(json.dumps(INTERFACE))
    twice['option']['mirror_run_count']['cases'][0]['pipeline_override'] = {'MirrorTaskTeamMode': {}}
    interface.write_text(json.dumps(twice), encoding='utf-8')
    with pytest.raises(ValueError, match='Two choices patch'):
        gui_preferences.task_override(_write(tmp_path, _listed(saved)), interface)


def test_the_real_interface_replays_a_default_configuration_without_complaint(tmp_path):
    from pathlib import Path
    interface = Path(__file__).resolve().parents[1] / 'assets/interface.json'
    override, chosen = gui_preferences.task_override(_write(tmp_path, _listed({})), interface)
    assert override
    assert {name for name, _, _ in chosen} >= {'mirror_team_mode', 'mirror_reward_claim', 'mirror_defeat_accept'}
