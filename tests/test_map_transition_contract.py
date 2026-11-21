"""One immutable successor judgement; allowed waiting is not learned success."""
from dataclasses import FrozenInstanceError
import pytest

from maalimbus import map_dispatch, window


@pytest.mark.parametrize('page', ['UNKNOWN','LOADING','CONNECTING','TUTORIAL',None,''])
def test_uncertain_or_covered_successor_remains_unjudged(page):
    result=map_dispatch.node_transition(page)
    assert result.outcome=='unjudged'


def test_named_successors_derive_from_the_real_planner_instead_of_a_second_table():
    plan=window.plan_step('MAP',candidates=[[10,20,30,40]])
    for page in plan['expect']:
        result=map_dispatch.node_transition(page)
        assert result.expected==tuple(plan['expect'])
        assert result.outcome==('unjudged' if page=='UNKNOWN' else 'accepted')
    assert map_dispatch.node_transition('HOME').outcome=='unjudged'
    assert map_dispatch.node_transition('MAP').outcome=='rejected'


def test_original_action_contract_and_frozen_verdict_are_preserved():
    result=map_dispatch.node_transition('SHOP', ['NODE_PANEL','UNKNOWN'])
    assert result.outcome=='unjudged'
    with pytest.raises(FrozenInstanceError):result.outcome='accepted'


def test_named_preview_retires_navigation_but_never_grants_the_room_enter():
    expected=window.plan_step('MAP',candidates=[[10,20,30,40]])['expect']
    state={'navigation_probe_pending':True}
    assert map_dispatch.after_settle(state,'MAP','NODE_PREVIEW',expected=expected)
    assert state['navigation_probe_pending'] is False
    # The separate preview input still needs its own current-frame control.
    proposal=window.plan_step('NODE_PREVIEW',preview=None)
    assert proposal['action']==window.RECORD and proposal['target'] is None


def test_new_preview_contract_cannot_rejudge_an_older_narrow_action():
    state={'navigation_probe_pending':True}
    assert not map_dispatch.after_settle(state,'MAP','NODE_PREVIEW',expected=['NODE_PANEL','UNKNOWN'])
    assert state=={'navigation_probe_pending':True}
    assert not map_dispatch.after_settle(state,'MAP','UNKNOWN',expected=['NODE_PANEL','UNKNOWN'])
    assert state=={'navigation_probe_pending':True}
