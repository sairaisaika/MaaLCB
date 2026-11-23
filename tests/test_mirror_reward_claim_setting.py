"""Whether a cleared run claims its rewards by itself is the Mirror task's own setting.

Until 2026-11-23 a clear always stopped on the reward page until someone wrote a budget
for that very run into the settings file by hand. The user asked for the choice to sit
in the task's settings. The setting is a standing limit in modules: an offer at or under
it is claimed, anything else stops on the reward page with nothing clicked.
"""
import json
from pathlib import Path

import pytest

from maalimbus.paid_reward_action import scoped_module_cap
from maalimbus.reward_task_budget import STANDING_CHOICES, apply_standing
from maalimbus.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def settings(tmp_path, **values):
    write_json(tmp_path / 'user-mirror-settings.json', dict(max_reward_modules=0, module_budget_pending=True, **values))
    return tmp_path / 'user-mirror-settings.json'


def test_a_standing_limit_allows_the_next_run_whatever_its_id(tmp_path):
    path = settings(tmp_path, reward_budget_scope='an-older-run')
    assert scoped_module_cap(read_json(path), 'new-run') is None
    assert apply_standing(tmp_path, 6) == 'saved'
    policy = read_json(path)
    assert policy['auto_claim_modules'] == 6 and policy['reward_budget_scope'] == 'an-older-run'
    assert scoped_module_cap(policy, 'new-run') == 6 and scoped_module_cap(policy, 'another-run') == 6
    assert scoped_module_cap(policy, None) is None and scoped_module_cap(policy, '') is None
    assert apply_standing(tmp_path, 6) == 'unchanged'


def test_an_answer_given_for_this_very_run_stands_also_when_it_is_a_refusal(tmp_path):
    path = settings(tmp_path, reward_budget_scope='this-run', auto_claim_modules=18)
    assert scoped_module_cap(read_json(path), 'this-run') is None          # refused for this run
    write_json(path, dict(read_json(path), max_reward_modules=5, module_budget_pending=False))
    assert scoped_module_cap(read_json(path), 'this-run') == 5             # answered 5, not the standing 18
    assert scoped_module_cap(read_json(path), 'next-run') == 18


def test_off_removes_the_limit_and_saved_keeps_whatever_is_there(tmp_path):
    path = settings(tmp_path, auto_claim_modules=5)
    assert apply_standing(tmp_path, 'saved') == 'kept' and read_json(path)['auto_claim_modules'] == 5
    assert apply_standing(tmp_path, 0) == 'saved' and 'auto_claim_modules' not in read_json(path)
    assert scoped_module_cap(read_json(path), 'new-run') is None
    # The choice can be the first thing ever saved.
    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    assert apply_standing(fresh, 5) == 'saved' and read_json(fresh / 'user-mirror-settings.json') == {'auto_claim_modules': 5}


def test_an_open_claim_keeps_the_limit_it_was_reserved_under(tmp_path):
    path = settings(tmp_path, auto_claim_modules=6)
    write_json(tmp_path / 'user-reward-claim-transaction.json', dict(scope='this-run', pending='reserved'))
    assert apply_standing(tmp_path, 0) == 'kept_while_a_claim_is_open'
    assert read_json(path)['auto_claim_modules'] == 6
    write_json(tmp_path / 'user-reward-claim-transaction.json', dict(scope='this-run', pending=None, completed=True))
    assert apply_standing(tmp_path, 0) == 'saved'


@pytest.mark.parametrize('selection', [7, -5, '5', True, None, 5.0])
def test_a_limit_the_interface_does_not_offer_is_refused(tmp_path, selection):
    settings(tmp_path)
    with pytest.raises(ValueError, match='limit'):
        apply_standing(tmp_path, selection)


def test_the_interface_offers_exactly_the_limits_the_program_accepts():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    option = pi['option']['mirror_reward_claim']
    values = [case['pipeline_override']['MirrorRewardClaim']['attach']['modules'] for case in option['cases']]
    assert values == ['saved', *STANDING_CHOICES] and option['default_case'] == 'saved'
    task = next(t for t in pi['task'] if t['name'] == 'mirror_loop')
    assert 'mirror_reward_claim' in task['option']
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert nodes['MirrorRewardClaim']['attach'] == {'modules': 'saved'}
    # Every limit offered is the cost of an offer the reader has actually measured.
    from maalimbus.paid_reward_action import MEASURED_OFFERS
    assert {value for value in STANDING_CHOICES if value} == {cost for cost, weekly in MEASURED_OFFERS}


def test_the_mirror_task_saves_the_choice_before_it_looks_at_the_game():
    source = (ROOT / 'agent/recognition.py').read_text(encoding='utf-8')
    body = source[source.index('class MainTaskAction'):]
    assert body.index('apply_standing(data_directory(ROOT),claim)') < body.index("config/'user-run-ledger.json'")
