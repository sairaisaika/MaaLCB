import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('packaged_verify', Path(__file__).resolve().parents[1]/'tools/verify_packaged_mirror_loop.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_started_then_failed_is_not_a_pass():
    actual = dict(reason='Deployment successor participant count not proven', passed=False,
                  steps=[dict(passed=False)], verified_clear=False)
    verdict = module.verdict(actual, dict(task_succeeded=True), True)
    assert verdict['entry_connected'] and not verdict['passed']
    assert not verdict['dungeon_complete']


def test_bounded_progress_is_not_dungeon_completion():
    actual = dict(reason='window_steps_passed', passed=True, steps=[dict(passed=True)], verified_clear=False)
    verdict = module.verdict(actual, dict(task_succeeded=True), True)
    assert verdict['bounded_progress_verified'] and not verdict['dungeon_complete']
    assert not module.verdict(actual, dict(task_succeeded=True, timed_out=True), True)['passed']
    assert not module.verdict(None, dict(task_succeeded=True), True)['passed']


def test_missing_task_result_retains_watchdog_reason_without_inventing_success():
    result=module.verdict(None,dict(task_succeeded=False),True,
        ending=dict(event='mirror_loop_stopped',reason='the_run_kept_observing_without_writing_anything'))
    assert result['stop_reason']=='the_run_kept_observing_without_writing_anything'
    assert not result['passed'] and not result['dungeon_complete']


def test_battle_clear_cannot_satisfy_requested_runs_before_settlement():
    record = dict(reason='window_steps_passed', passed=True, steps=[dict(passed=True)],
                  verified_clear=True, verified_runs=dict(target=1, completed=0, ledger_total=10, counted_at_launch=10))
    result = module.verdict(record, dict(task_succeeded=True), True, requested_runs=1)
    assert result['clear_verified'] and result['bounded_progress_verified']
    assert not result['passed'] and not result['dungeon_complete']


@pytest.mark.parametrize('fault', [None, 'prior_total', 'requested_mismatch', 'missing_event',
                                   'mismatched_event', 'interrupted', 'not_stopped', 'watchdog', 'observe_only'])
def test_completion_uses_this_launch_settlement_even_when_resuming_after_clear(fault):
    record = dict(reason='window_steps_passed', passed=True, steps=[dict(passed=True)],
                  verified_clear=False, verified_runs=dict(target=1, completed=1, ledger_total=11, counted_at_launch=10))
    ending = dict(event='mirror_loop_stopped', reason=record['reason'], passed=True, stop_path='agent_loop')
    completion = dict(event='run_count_reached', target=1, completed=1)
    outcome = dict(task_succeeded=True, stop_confirmed=True)
    requested = 1
    if fault == 'prior_total':
        record['verified_runs']['counted_at_launch'] = 11
    elif fault == 'requested_mismatch':
        requested = 2
    elif fault == 'missing_event':
        completion = None
    elif fault == 'mismatched_event':
        completion['completed'] = 2
    elif fault == 'interrupted':
        outcome['interrupted'] = True
    elif fault == 'not_stopped':
        outcome['stop_confirmed'] = False
    elif fault == 'watchdog':
        ending['stop_path'] = 'no_progress_watchdog'
    elif fault == 'observe_only':
        record['observe_only'] = True
    result = module.verdict(record, outcome, True, ending=ending,
                            completion=completion, requested_runs=requested)
    assert result['dungeon_complete'] is (fault is None)
    assert result['passed'] is (fault is None)
    assert not result['clear_verified']
