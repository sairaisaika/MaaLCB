"""Mirror team settings: gift systems by ticking, deployment order three ways.

Until 2026-11-23 a team took fifteen options, twelve of them dropdowns that each listed
all twelve sinners; the user called them unusable. The first replacement still offered
fixed system combinations ("Charge+Tremor") and a typed order. The user asked for free
ticking, including none at all so the program buys freely, for something more direct
than typing an order, and for the settings to be named for what they are: how a team is
used in the Mirror Dungeon.
"""
import json
from pathlib import Path

import pytest

from maalimbus.game_vocabulary import TEAM_CHOICES
from maalimbus.global_settings import GAME, KEEP, apply_builds, collect_builds, parse_order
from maalimbus.policies import Team
from maalimbus.storage import KEYWORDS, ProfileStore, SINNERS, write_json

ROOT = Path(__file__).resolve().parents[1]
REVERSED = tuple(reversed(SINNERS))


def nodes(slot=2, systems='keep', ticked=(), order='keep', text=''):
    """The option nodes as the framework hands them over after the ticked cases are merged."""
    prefix = f'Global_global_team_{slot}'
    chosen = {prefix + '_systems': dict(attach=dict(mode=systems)),
              prefix + '_keywords': dict(attach={'kw_' + word: True for word in ticked}),
              prefix + '_order': dict(attach=dict(mode=order)),
              prefix + '_order_text': dict(attach=dict(order=text))}

    def get(name):
        if name in chosen:
            return chosen[name]
        if name.endswith('_keywords'):
            return dict(attach={})
        if name.endswith('_order_text'):
            return dict(attach=dict(order=''))
        return dict(attach=dict(mode='keep'))
    return get


def test_any_number_of_systems_can_be_ticked_and_none_is_a_choice_too():
    assert collect_builds(nodes(systems='choose', ticked=('Tremor', 'Charge'))) == {
        '2': dict(keywords=['Charge', 'Tremor'], order='keep')}
    assert collect_builds(nodes(systems='choose', ticked=KEYWORDS))['2']['keywords'] == sorted(KEYWORDS)
    assert collect_builds(nodes(systems='choose'))['2']['keywords'] == []          # buy freely
    assert collect_builds(nodes()) == {}                                           # nothing chosen: no edit


def test_a_team_tied_to_no_system_is_saved_as_such_and_an_imported_value_does_not_outrank_it(tmp_path):
    store = ProfileStore(tmp_path / 'user-team-profiles.json')
    store.save([Team(2, frozenset({'Bleed'}), formation_keywords=frozenset({'Bleed'}), deployment=SINNERS)])
    assert apply_builds(tmp_path, {'2': dict(keywords=[], order='keep')}) == [2]
    team = store.load()[0]
    assert team.keywords == frozenset() and team.formation_keywords == frozenset() and team.deployment == SINNERS
    assert apply_builds(tmp_path, {'2': dict(keywords=['Charge', 'Tremor'], order='keep')}) == [2]
    team = store.load()[0]
    assert team.keywords == team.formation_keywords == frozenset({'Charge', 'Tremor'})


def test_the_whole_order_can_still_be_written_and_an_empty_line_is_refused():
    assert collect_builds(nodes(order='custom', text='6 8 7 3 5')) == {'2': dict(keywords='keep', order='6 8 7 3 5')}
    with pytest.raises(ValueError, match='Write the deployment order'):
        collect_builds(nodes(order='custom', text='  '))
    # Ticking "who deploys first" was offered for a few hours; ticking cannot say an order.
    for mode in ('alphabetical', 'starters'):
        with pytest.raises(ValueError, match='Unknown Mirror team setting'):
            collect_builds(nodes(order=mode))


def test_following_the_game_forgets_the_saved_order(tmp_path):
    assert collect_builds(nodes(order='game')) == {'2': dict(keywords='keep', order='game')}
    store = ProfileStore(tmp_path / 'user-team-profiles.json')
    store.save([Team(2, frozenset({'Bleed'}), deployment=SINNERS)])
    assert apply_builds(tmp_path, {'2': dict(keywords=KEEP, order='game')}) == [2]
    assert store.load()[0].deployment == () and store.load()[0].keywords == frozenset({'Bleed'})


def test_an_order_is_written_as_numbers_or_names_in_any_of_the_three_languages():
    assert parse_order('12 11 10 9 8 7 6 5 4 3 2 1') == REVERSED
    assert parse_order('12,11，10、9 > 8 → 7-6 5 4 3 2 1') == REVERSED
    assert parse_order('Gregor Outis Sinclair Rodion Ishmael Heathcliff Hong Lu Meursault Ryoshu '
                       'Don Quixote Faust Yi Sang') == REVERSED
    assert parse_order('格里高尔 奥提斯 辛克莱 罗佳 以实玛利 希斯克利夫 鸿璐 默尔索 良秀 堂吉诃德 浮士德 李箱') == REVERSED
    assert parse_order('6 8 7 3 5') == ('Hong Lu', 'Ishmael', 'Heathcliff', 'Don Quixote', 'Meursault',
                                        'Yi Sang', 'Faust', 'Ryoshu', 'Rodion', 'Sinclair', 'Outis', 'Gregor')
    for word in ('', 'keep', '不变'):
        assert parse_order(word) == KEEP
    for word in ('game', '游戏'):
        assert parse_order(word) == GAME


@pytest.mark.parametrize('line, said', [('6 6 7', 'Hong Lu is named twice'), ('6 13', '"13" is not a sinner'),
                                        ('6 faustus', '"faustus" is not a sinner'), (', ,', 'names no sinner')])
def test_a_line_that_cannot_be_an_order_is_refused_by_what_is_wrong(line, said):
    with pytest.raises(ValueError, match=said):
        parse_order(line)


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
    assert apply_builds(tmp_path, {'2': dict(keywords=KEEP, order='keep')}) == []
    assert apply_builds(tmp_path, {}) == []


def test_a_team_that_was_never_saved_can_be_given_an_order_alone(tmp_path):
    assert apply_builds(tmp_path, {'3': dict(keywords=KEEP, order='6 8 7')}) == [3]
    saved = ProfileStore(tmp_path / 'user-team-profiles.json').load()[0]
    assert saved.slot == 3 and saved.keywords == frozenset() and saved.deployment[:3] == ('Hong Lu', 'Ishmael', 'Heathcliff')


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


def test_the_interface_matches_what_the_program_reads():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    sections = [s for s in pi['setting'] if s['name'].startswith('global_team_')]
    assert len(sections) == 40 and len(set(pi['global_option'])) == len(pi['global_option'])
    # It was 600. Four per team for systems and order, six for the team's starlight plan:
    # the plan, a row of ticks per level, and what may come from the stock.
    assert len([name for name in pi['option'] if name.startswith('global_team_')]) == 400
    assert collect_builds(pipeline.__getitem__) == {}        # the shipped defaults change nothing
    for slot in range(1, 41):
        prefix = f'global_team_{slot}'
        section = next(s for s in sections if s['name'] == prefix)
        assert section['label'] == f'$mirror_team_{slot}' and section['option'] == [prefix + '_systems', prefix + '_order', prefix + '_stars']
        systems, keywords = pi['option'][prefix + '_systems'], pi['option'][prefix + '_keywords']
        assert systems['default_case'] == 'keep' and [c['name'] for c in systems['cases']] == ['keep', 'choose']
        assert keywords['type'] == 'checkbox' and keywords['default_case'] == []
        # The game's ten keywords in the game's order, then the program's own switch.
        assert [c['name'] for c in keywords['cases']] == list(TEAM_CHOICES)
        # Every ticked case sets its own attach key on one node, so several can be ticked at once.
        keys = [list(c['pipeline_override'][f'Global_{prefix}_keywords']['attach']) for c in keywords['cases']]
        assert keys == [['kw_' + word] for word in TEAM_CHOICES]
        order = pi['option'][prefix + '_order']
        assert order['default_case'] == 'keep' and [c['name'] for c in order['cases']] == ['keep', 'game', 'custom']
        assert prefix + '_starters' not in pi['option']
        assert pi['option'][prefix + '_order_text']['type'] == 'input'
        assert pi['option'][f'mirror_queue_{slot}']['default_case'] == str(slot) or slot <= 20
    for name in ('experience_team', 'thread_team'):
        option = pi['option'][name]
        assert option['default_case'] in {case['name'] for case in option['cases']}
    assert 'GlobalSettingsApply' not in pipeline   # removed 2026-11-27: the Mirror task applies them
    assert len([name for name in pipeline if name.startswith('Global_global_team_')]) == 400
