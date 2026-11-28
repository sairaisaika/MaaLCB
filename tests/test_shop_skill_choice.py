"""Skill replacement: a switch, whose skills, and which copies each Identity keeps.

The user asked on 2026-11-28 for "everyone" as well as "front row only", and for "keep a
tier 1", "keep a tier 2", both or neither in any combination; eight combinations in one
dropdown read badly, so the settings offer a switch, a choice of whose skills and two
checkboxes, and one mode string carries both answers.
"""
import json
from pathlib import Path

import pytest

from maalimbus import shop_skill_policy as policy

ROOT = Path(__file__).resolve().parents[1]


def test_whose_skills_follows_the_choice_and_the_old_modes_keep_their_meaning():
    assert policy.eligible('front_keep_s2', 'frontline') and not policy.eligible('front_keep_s2', 'backup')
    assert policy.eligible('all_keep_s2', 'frontline') and policy.eligible('all_keep_s2', 'backup')
    assert not policy.eligible('off', 'frontline') and not policy.eligible('nonsense', 'frontline')
    # The two modes offered before stay front row only, with the copies they kept.
    assert policy.eligible('keep_one_each', 'frontline') and not policy.eligible('keep_one_each', 'backup')
    assert policy.minimums('keep_one_each') == (1, 1) and policy.minimums('keep_one_s2') == (0, 1)


@pytest.mark.parametrize('keep_s1,keep_s2,expected', [
    (True, True, (1, 1)), (False, True, (0, 1)), (True, False, (1, 0)), (False, False, (0, 0))])
def test_the_two_boxes_set_the_copies_each_identity_keeps(keep_s1, keep_s2, expected):
    for who in policy.WHO:
        mode = policy.mode_of(who, keep_s1, keep_s2)
        assert mode in policy.SKILL_MODES and policy.minimums(mode) == expected


def test_the_proposal_keeps_what_the_boxes_ask():
    from types import SimpleNamespace as S
    quote = lambda tier, price: S(to_tier=3, from_tier=tier, tiers_verified=True, price=price, select_box=(0, 0, 1, 1))
    modal = S(balance=1000, counts=(1, 1, 1), quotes=[quote(1, 100), quote(2, 150)])
    assert policy.propose_replacement(modal, 'front_keep_none', 0).quote.from_tier == 1
    assert policy.propose_replacement(modal, 'front_keep_s1', 0).quote.from_tier == 2
    assert policy.propose_replacement(modal, 'front_keep_s2', 0).quote.from_tier == 1
    assert policy.propose_replacement(modal, 'front_keep_s1s2', 0) is None


def test_the_settings_offer_a_switch_whose_skills_and_two_boxes():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    mode = pi['option']['mirror_shop_skill_mode']
    assert [case['name'] for case in mode['cases']] == ['off', 'on'] and mode['default_case'] == 'off'
    assert mode['cases'][1]['option'] == ['mirror_shop_skill_who', 'mirror_shop_skill_keep']
    who = pi['option']['mirror_shop_skill_who']
    assert [case['name'] for case in who['cases']] == ['front', 'all'] and who['default_case'] == 'front'
    keep = pi['option']['mirror_shop_skill_keep']
    assert keep['type'] == 'checkbox' and keep['default_case'] == ['s2']
    assert [case['name'] for case in keep['cases']] == ['s2', 's1']
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert pipeline['MirrorShopSkillWho']['attach'] == {'who': 'front'} and pipeline['MirrorShopSkillKeep']['attach'] == {}


def test_a_backup_gets_the_service_only_when_everyone_is_chosen(monkeypatch):
    from maalimbus import pre_battle_identity
    roles = {'Don Quixote': 'frontline', 'Ishmael': 'backup'}
    monkeypatch.setattr(pre_battle_identity, 'submitted_identity',
                        lambda deployment, scope, sinner: dict(role=roles[sinner]))
    offers = [dict(name='Replace Ishmael Skill', sinner='Ishmael')]
    pick = lambda mode: policy.choose_skill_service(offers, 900, 500, {'scope': 's'}, 's', (), (), mode=mode)
    assert pick('front_keep_s2') is None and pick('keep_one_each') is None
    assert pick('all_keep_s2') == offers[0]
    assert pick('off') is None
