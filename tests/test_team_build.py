"""A team's keyword build is a global setting of the interface, not a pipeline chain.

The build used to have its own pipeline entry (`TeamKeywordSet` -> `TeamKeywordExtra` ->
`TeamBuildSave` -> `MirrorLoop`, written by the `limbus_team` action). Its options left the
interface on 2026-11-23 and the nodes and the action followed on 2026-11-27: explicit
edits are applied by `GlobalSettingsAction.apply` inside the Mirror task
(`tests/test_global_settings.py`). These checks keep the two halves from coming back apart.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from maalimbus.storage import KEYWORDS


def test_the_build_chain_is_gone_from_the_pipeline_and_the_interface():
    nodes = json.loads((ROOT/'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    pi = json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    for name in ('TeamKeywordSet','TeamKeywordExtra','TeamBuildSave','TeamBuildDone','GlobalSettingsApply'):
        assert name not in nodes
    assert not [name for name, node in nodes.items() if node.get('custom_action') == 'limbus_team']
    # The standalone build options no task reached were removed on 2026-11-23.
    for name in ('team_build_slot','team_build_name','team_keywords','team_keywords_extra'):
        assert name not in pi['option']
    tasks = {t['name']: t for t in pi['task']}
    assert 'team_build' not in tasks
    assert tasks['mirror_loop']['entry'] == 'MirrorTask'
    # Each team carries two settings and both default to "keep": nothing is replaced unasked.
    assert all(nodes[f'Global_global_team_{i}_systems']['attach'] == {'mode': 'keep'}
               and nodes[f'Global_global_team_{i}_order']['attach'] == {'mode': 'keep'}
               for i in range(1,41))
    assert 'team_keywords' not in tasks['mirror_loop']['option']
    assert tasks['mirror_loop']['option']==['mirror_team_mode','mirror_star_source',
        'mirror_initial_keyword','mirror_shop_policy','mirror_shop_refresh_limit','mirror_shop_refresh_paid',
            'mirror_shop_coin_reserve','mirror_shop_fusion','mirror_shop_skill_mode','mirror_run_count','mirror_defeat_accept','mirror_reward_claim',
        'mirror_schedule',
        'mirror_preferences',
        'mirror_battle_assignment']
    assert not tasks['mirror_loop'].get('pipeline_override')


def test_every_keyword_a_build_can_name_is_one_the_engine_knows():
    """The GUI offers the same list the profile rejects unknown names against."""
    pi = json.loads((ROOT/'assets/interface.json').read_text(encoding='utf-8'))
    offered = {case['name'] for slot in (1, 20, 40)
               for case in pi['option'][f'global_team_{slot}_keywords']['cases']}
    # A Vestige is a material, not a keyword: the engine still loads a team that names it.
    assert offered == set(KEYWORDS) - {'Vestige'}
