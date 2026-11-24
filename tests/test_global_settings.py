"""A team has two settings, systems and deployment order, and each can be left alone.

Until 2026-11-23 a team took fifteen options, twelve of them dropdowns that each listed
all twelve sinners. The user called the dropdowns unusable; the order is now one line.
"""
import json
from pathlib import Path

import pytest

from maalimbus.global_settings import GAME, KEEP, apply_builds, collect_builds, parse_order
from maalimbus.policies import Team
from maalimbus.storage import ProfileStore, SINNERS, write_json

ROOT = Path(__file__).resolve().parents[1]
REVERSED = tuple(reversed(SINNERS))


def test_an_order_is_written_as_numbers_or_names_in_any_of_the_three_languages():
    assert parse_order('12 11 10 9 8 7 6 5 4 3 2 1') == REVERSED
    assert parse_order('12,11，10、9 > 8 → 7-6 5 4 3 2 1') == REVERSED
    assert parse_order('Gregor Outis Sinclair Rodion Ishmael Heathcliff Hong Lu Meursault Ryoshu '
                       'Don Quixote Faust Yi Sang') == REVERSED
    assert parse_order('格里高尔 奥提斯 辛克莱 罗佳 以实玛利 希斯克利夫 鸿璐 默尔索 良秀 堂吉诃德 浮士德 李箱') == REVERSED
    assert parse_order('  hong lu 8 希斯克利夫 ')[:3] == ('Hong Lu', 'Ishmael', 'Heathcliff')


def test_a_line_may_name_only_the_first_few_and_the_rest_follow_in_roster_order():
    assert parse_order('6 8 7 3 5') == ('Hong Lu', 'Ishmael', 'Heathcliff', 'Don Quixote', 'Meursault',
                                        'Yi Sang', 'Faust', 'Ryoshu', 'Rodion', 'Sinclair', 'Outis', 'Gregor')


def test_keep_and_game_are_words_not_orders():
    for word in ('', '  ', 'keep', 'KEEP', '不变', 'そのまま'):
        assert parse_order(word) == KEEP
    for word in ('game', 'Game', '游戏', '跟随游戏', 'ゲーム'):
        assert parse_order(word) == GAME


@pytest.mark.parametrize('line, said', [('6 6 7', 'Hong Lu is named twice'), ('6 13', '"13" is not a sinner'),
                                        ('6 faustus', '"faustus" is not a sinner'), (', ,', 'names no sinner')])
def test_a_line_that_cannot_be_an_order_is_refused_by_what_is_wrong(line, said):
    with pytest.raises(ValueError, match=said):
        parse_order(line)
    with pytest.raises(ValueError):
        parse_order(None)


def test_each_setting_replaces_only_its_own_field(tmp_path):
    store = ProfileStore(tmp_path / 'user-team-profiles.json')
    original = [Team(5, frozenset({'Burn'})),
                Team(2, frozenset({'Bleed'}), allow=frozenset({'Portable Battery Socket'}),
                     pack_weights=(('ASEA', 20),), deployment=SINNERS)]
    store.save(original)
    assert apply_builds(tmp_path, {'2': dict(keywords=KEEP, order='12 11 10 9 8 7 6 5 4 3 2 1')}) == [2]
    team = store.load()[1]
    assert team.deployment == REVERSED and team.keywords == frozenset({'Bleed'})
    assert team.allow == original[1].allow and team.pack_weights == original[1].pack_weights
    assert store.load()[0] == original[0]
    assert apply_builds(tmp_path, {'2': dict(keywords=['Charge', 'Tremor'], order='keep')}) == [2]
    team = store.load()[1]
    assert team.keywords == frozenset({'Charge', 'Tremor'}) and team.deployment == REVERSED
    assert apply_builds(tmp_path, {'2': dict(keywords=['Charge', 'Tremor'], order='keep')}) == []


def test_game_forgets_the_saved_order_so_the_run_deploys_what_the_game_shows(tmp_path):
    store = ProfileStore(tmp_path / 'user-team-profiles.json')
    store.save([Team(2, frozenset({'Bleed'}), deployment=SINNERS)])
    assert apply_builds(tmp_path, {'2': dict(keywords=KEEP, order='game')}) == [2]
    assert store.load()[0].deployment == () and store.load()[0].keywords == frozenset({'Bleed'})


def test_nothing_chosen_changes_nothing_and_creates_nothing(tmp_path):
    assert apply_builds(tmp_path, {}) == []
    assert not (tmp_path / 'user-team-profiles.json').exists()
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert collect_builds(nodes.__getitem__) == {}        # the shipped defaults are "keep" twice, forty times


def test_a_team_that_is_not_saved_yet_needs_its_systems_first(tmp_path):
    with pytest.raises(ValueError, match='choose its systems first'):
        apply_builds(tmp_path, {'3': dict(keywords=KEEP, order='6 8 7')})
    assert apply_builds(tmp_path, {'3': dict(keywords=['Poise'], order='6 8 7')}) == [3]
    saved = ProfileStore(tmp_path / 'user-team-profiles.json').load()[0]
    assert saved.slot == 3 and saved.deployment[:3] == ('Hong Lu', 'Ishmael', 'Heathcliff')


@pytest.mark.parametrize('fault', ['duplicate', 'unknown_word', 'unknown_system', 'shape', 'slot', 'active'])
def test_an_invalid_second_edit_never_partially_replaces_the_first(tmp_path, fault):
    store = ProfileStore(tmp_path / 'user-team-profiles.json')
    store.save([Team(1, frozenset({'Bleed'})), Team(2, frozenset({'Burn'}))])
    before = store.path.read_bytes()
    good, bad, key = dict(keywords=['Poise'], order='6 8 7'), dict(keywords=['Poise'], order='6 8 7'), '2'
    if fault == 'duplicate': bad['order'] = '6 6'
    if fault == 'unknown_word': bad['order'] = '6 nobody'
    if fault == 'unknown_system': bad['keywords'] = ['unknown']
    if fault == 'shape': bad['edit'] = True
    if fault == 'slot': key = '41'
    if fault == 'active': write_json(tmp_path / 'user-run-ledger.json', {'active': {'team': 2}})
    with pytest.raises(ValueError):
        apply_builds(tmp_path, {'1': good, key: bad})
    assert store.path.read_bytes() == before


def test_the_interface_gives_each_of_forty_teams_exactly_those_two_settings():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    sections = [s for s in pi['setting'] if s['name'].startswith('global_team_')]
    assert len(sections) == 40 and len(set(pi['global_option'])) == len(pi['global_option'])
    assert 'software_auto_update' in pi['global_option']
    team_options = [name for name in pi['option'] if name.startswith('global_team_')]
    assert len(team_options) == 80                       # it was 600
    for slot in range(1, 41):
        systems, order = pi['option'][f'global_team_{slot}_systems'], pi['option'][f'global_team_{slot}_order']
        assert systems['default_case'] == 'keep' and systems['cases'][0]['name'] == 'keep'
        assert order['type'] == 'input' and [field['default'] for field in order['inputs']] == ['keep']
        assert next(s for s in sections if s['name'] == f'global_team_{slot}')['option'] == [
            f'global_team_{slot}_systems', f'global_team_{slot}_order']
        # A queue position past 20 used to default to team 20, whichever position it was.
        assert pi['option'][f'mirror_queue_{slot}']['default_case'] == str(slot) or slot <= 20
    for name in ('experience_team', 'thread_team'):      # both named a default case they did not have
        option = pi['option'][name]
        assert option['default_case'] in {case['name'] for case in option['cases']}
    task = next(t for t in pi['task'] if t['name'] == 'mirror_loop')
    assert task['entry'] == 'MirrorTask'
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert nodes['GlobalSettingsApply']['next'] == ['MirrorLoop']
    assert len([name for name in nodes if name.startswith('Global_global_team_')]) == 80
