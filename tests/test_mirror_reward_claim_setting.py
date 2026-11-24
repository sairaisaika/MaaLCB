"""Whether a cleared run claims its rewards is one yes-or-no setting of the Mirror task.

Until 2026-11-23 a clear always stopped on the reward page until someone wrote a budget
for that very run into the settings file by hand. The first version of this setting
offered module limits (5, 6, 18); the user pointed out that a run's rewards cost 5
modules apart from weekly bonuses, so the only question is whether to claim.
"""
import json
from pathlib import Path

import pytest

from maalimbus.paid_reward_action import MEASURED_OFFERS, scoped_module_cap
from maalimbus.reward_task_budget import STANDING_CHOICES, apply_standing
from maalimbus.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
ANY_MEASURED_OFFER = max(cost for cost, weekly in MEASURED_OFFERS)


def settings(tmp_path, **values):
    write_json(tmp_path / 'user-mirror-settings.json', dict(max_reward_modules=0, module_budget_pending=True, **values))
    return tmp_path / 'user-mirror-settings.json'


def test_claim_allows_the_next_run_whatever_its_id_and_whichever_offer_the_game_shows(tmp_path):
    path = settings(tmp_path, reward_budget_scope='an-older-run')
    assert scoped_module_cap(read_json(path), 'new-run') is None
    assert apply_standing(tmp_path, 'claim') == 'saved'
    policy = read_json(path)
    assert policy['auto_claim_modules'] == ANY_MEASURED_OFFER and policy['reward_budget_scope'] == 'an-older-run'
    assert all(cost <= scoped_module_cap(policy, 'new-run') for cost, weekly in MEASURED_OFFERS)
    assert scoped_module_cap(policy, 'another-run') == ANY_MEASURED_OFFER
    assert scoped_module_cap(policy, None) is None and scoped_module_cap(policy, '') is None
    assert apply_standing(tmp_path, 'claim') == 'unchanged'


def test_an_answer_given_for_this_very_run_stands_also_when_it_is_a_refusal(tmp_path):
    path = settings(tmp_path, reward_budget_scope='this-run', auto_claim_modules=ANY_MEASURED_OFFER)
    assert scoped_module_cap(read_json(path), 'this-run') is None          # refused for this run
    write_json(path, dict(read_json(path), max_reward_modules=5, module_budget_pending=False))
    assert scoped_module_cap(read_json(path), 'this-run') == 5             # answered 5 for this run
    assert scoped_module_cap(read_json(path), 'next-run') == ANY_MEASURED_OFFER


def test_off_stops_on_the_reward_page_and_saved_keeps_whatever_is_there(tmp_path):
    path = settings(tmp_path, auto_claim_modules=5)
    assert apply_standing(tmp_path, 'saved') == 'kept' and read_json(path)['auto_claim_modules'] == 5
    assert apply_standing(tmp_path, 'off') == 'saved' and 'auto_claim_modules' not in read_json(path)
    assert scoped_module_cap(read_json(path), 'new-run') is None
    # The choice can be the first thing ever saved.
    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    assert apply_standing(fresh, 'claim') == 'saved'
    assert read_json(fresh / 'user-mirror-settings.json') == {'auto_claim_modules': ANY_MEASURED_OFFER}


def test_an_open_claim_keeps_the_limit_it_was_reserved_under(tmp_path):
    path = settings(tmp_path, auto_claim_modules=ANY_MEASURED_OFFER)
    write_json(tmp_path / 'user-reward-claim-transaction.json', dict(scope='this-run', pending='reserved'))
    assert apply_standing(tmp_path, 'off') == 'kept_while_a_claim_is_open'
    assert read_json(path)['auto_claim_modules'] == ANY_MEASURED_OFFER
    write_json(tmp_path / 'user-reward-claim-transaction.json', dict(scope='this-run', pending=None, completed=True))
    assert apply_standing(tmp_path, 'off') == 'saved'


@pytest.mark.parametrize('selection', [5, 18, 0, 'yes', True, None])
def test_anything_but_the_two_choices_is_refused(tmp_path, selection):
    settings(tmp_path)
    with pytest.raises(ValueError, match='choice'):
        apply_standing(tmp_path, selection)


def test_the_interface_asks_only_whether_to_claim_and_defaults_to_claiming():
    pi = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    option = pi['option']['mirror_reward_claim']
    values = [case['pipeline_override']['MirrorRewardClaim']['attach']['modules'] for case in option['cases']]
    assert tuple(values) == STANDING_CHOICES == ('claim', 'off') and option['default_case'] == 'claim'
    task = next(t for t in pi['task'] if t['name'] == 'mirror_loop')
    assert 'mirror_reward_claim' in task['option']
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    assert nodes['MirrorRewardClaim']['attach'] == {'modules': 'claim'}


def test_the_mirror_task_saves_the_choice_before_it_looks_at_the_game():
    source = (ROOT / 'agent/recognition.py').read_text(encoding='utf-8')
    body = source[source.index('class MainTaskAction'):]
    assert body.index('apply_standing(data_directory(ROOT),claim)') < body.index("config/'user-run-ledger.json'")
