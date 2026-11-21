import pytest
from maalimbus.mirror_task_options import collect


def nodes(keyword='saved', search='saved', steps='saved', battle='saved', runs='saved', skill=None):
    data={'MirrorInitialKeyword': {'attach': {'keyword': keyword}},
          'MirrorGiftSearch': {'attach': {'mode': search}},
          'MirrorRunBounds': {'attach': {'steps': steps}},
          'MirrorRunCount': {'attach': {'run_count': runs}},
          'MirrorBattleAssignment':{'attach':{'mode':battle}}}
    if skill is not None:
        data['MirrorShopSkillMode']={'attach':{'mode':skill}}
    return data.__getitem__


def test_saved_options_preserve_existing_launch_and_loop_defaults():
    assert collect(nodes()) == {}


def test_distinct_nodes_keep_all_three_runtime_preferences():
    assert collect(nodes('poise', 'refuse', 120)) == dict(
        gift_keyword='poise', gift_search='refuse', steps=120)


def test_the_named_run_count_is_kept_apart_from_the_step_bound():
    """Two independent settings: the step bound is one window, the count is whole runs."""
    assert collect(nodes(steps=120, runs=3)) == dict(steps=120, run_count=3)


def test_no_named_run_count_is_not_a_zero_count():
    """'saved' leaves the launch's own setting alone; the window is not told 'stop at 0'."""
    assert collect(nodes(runs='saved')) == {}


def test_a_run_count_without_a_step_bound_still_travels():
    assert collect(nodes(runs=2)) == dict(run_count=2)


@pytest.mark.parametrize('args', [('unknown','saved','saved'),
    ('saved','select','saved'), ('saved','saved',True),
    ('saved','saved',0), ('saved','saved',2001)])
def test_invalid_or_paid_search_options_stop(args):
    with pytest.raises(ValueError):
        collect(nodes(*args))


@pytest.mark.parametrize('runs', [True, False, -1, 51, 'many', 1.0])
def test_invalid_run_counts_stop(runs):
    with pytest.raises(ValueError):
        collect(nodes(runs=runs))


@pytest.mark.parametrize('mode',['win_rate','damage','observe'])
def test_battle_mode_survives_other_independent_options(mode):
    assert collect(nodes('poise','refuse',120,mode))==dict(
        gift_keyword='poise',gift_search='refuse',steps=120,battle_assignment=mode)


def test_unknown_battle_mode_is_rejected():
    with pytest.raises(ValueError):collect(nodes(battle='unknown'))


def test_skill_checks_are_independent_task_options_with_off_as_default():
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'assets'
    pi=json.loads((root/'interface.json').read_bytes())
    option=pi['option']['mirror_shop_skill_mode']
    assert option['default_case']=='off'
    assert {case['name'] for case in option['cases']}=={'off','keep_one_each','keep_one_s2'}
    for case in option['cases']:
        assert case['pipeline_override']=={'MirrorShopSkillMode':{'attach':{'mode':case['name']}}}
        assert collect(nodes(steps=120,skill=case['name']))==dict(steps=120,shop_skill_mode=case['name'])
    with pytest.raises(ValueError,match='Unknown shop skill policy'):
        collect(nodes(skill='unlimited'))
