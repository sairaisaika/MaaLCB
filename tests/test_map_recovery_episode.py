"""A recovered node ends its failure episode; page toggles do not."""
from copy import deepcopy
import pytest
from maalimbus import runner,map_dispatch


def prior_episode():
    return dict(recovery_for='MAP',recovery_rung=1,recovery_episode='MAP',
                recovery_since=1.0,map_pending=[800,400,40,40],
                map_unjudged=dict(target=[800,400,40,40],frame='before',
                                  expect=['NODE_PANEL','UNKNOWN']),
                scope='unchanged',paid_pending=dict(phase='receipt'))


def test_independent_expected_node_successor_retires_old_episode_only(tmp_path,monkeypatch):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings=dict(interval=0))
    loop.state.update(prior_episode())
    paid=deepcopy(loop.state['paid_pending'])
    assert loop._resolve_map_click('NODE_PANEL',observation=dict(frame='after'))=='accepted'
    assert all(k not in loop.state for k in ('recovery_for','recovery_rung','recovery_episode','recovery_since'))
    assert loop.state['scope']=='unchanged' and loop.state['paid_pending']==paid
    # Hundreds of seconds of intervening valid gameplay belong to no recovery.
    monkeypatch.setattr(runner.time,'monotonic',lambda:700.0)
    monkeypatch.setattr(loop,'_viewport_recovery',lambda *args:True)
    result=loop._recover('MAP',loop.state,dict(reason='map_target_outside_current_step'),dict(reason='map_node_click_is_the_only_proven_forward_input'))
    assert result is not None and loop.state['recovery_since']==700.0
    assert loop.state['recovery_rung']==1


@pytest.mark.parametrize('outcome',['rejected','unjudged','superseded'])
def test_unanswered_or_failed_input_does_not_renew_episode(tmp_path,outcome):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(prior_episode());before=deepcopy(loop.state)
    loop._map_verdict(outcome=outcome,reason='diagnostic')
    for key in ('recovery_for','recovery_rung','recovery_episode','recovery_since','map_pending','map_unjudged','paid_pending'):
        assert loop.state[key]==before[key]


@pytest.mark.parametrize('page',['UNKNOWN','LOADING','HOME','MIRROR_ENTRY','RESUME_DIALOG'])
def test_auxiliary_navigation_and_unknown_successors_preserve_old_budget(tmp_path,page):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(prior_episode());before=deepcopy(loop.state)
    assert loop._resolve_map_click(page)=='unjudged'
    assert loop.state==before


def test_map_progress_does_not_retire_a_different_pages_recovery():
    state=prior_episode();state['recovery_for']='EVENT_CHECK';before=deepcopy(state)
    assert map_dispatch.retire_recovery_after_progress(state) is None
    assert state==before
