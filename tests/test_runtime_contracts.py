"""The shared record constrains meaning without inventing domain success."""
from dataclasses import FrozenInstanceError, asdict

import pytest

from maalimbus.map_dispatch import MapTransition, node_transition
from maalimbus.runtime_contracts import TransitionVerdict


def test_production_map_judge_uses_shared_verdict_with_compatible_import():
    verdict = node_transition('NODE_PANEL', ['NODE_PANEL', 'UNKNOWN'])
    assert MapTransition is TransitionVerdict
    assert isinstance(verdict, TransitionVerdict)
    assert asdict(verdict) == dict(outcome='accepted', after='NODE_PANEL',
                                 expected=('NODE_PANEL', 'UNKNOWN'),
                                 reason='named_expected_successor')
    with pytest.raises(FrozenInstanceError):
        verdict.reason = 'silently changed'


@pytest.mark.parametrize('outcome', ['passed', 'success', 'undetermined', True, None])
def test_legacy_status_cannot_be_misread_as_a_transition_verdict(outcome):
    with pytest.raises(ValueError):
        TransitionVerdict(outcome, 'NODE_PANEL', ('NODE_PANEL',), 'legacy')


@pytest.mark.parametrize('after', [None, '', 'HOME'])
def test_acceptance_cannot_broaden_the_original_successor_contract(after):
    with pytest.raises(ValueError):
        TransitionVerdict('accepted', after, ('NODE_PANEL',), 'unproved')


def test_unknown_allowed_wait_stays_unjudged_in_real_domain_judge():
    verdict = node_transition('UNKNOWN', ['NODE_PANEL', 'UNKNOWN'])
    assert isinstance(verdict, TransitionVerdict)
    assert verdict.outcome == 'unjudged'
    assert verdict.expected == ('NODE_PANEL', 'UNKNOWN')


def test_external_mutation_cannot_change_the_record_successor_contract():
    original = ['NODE_PANEL']
    with pytest.raises(ValueError):
        TransitionVerdict('unjudged', None, original, 'waiting')
    verdict = node_transition(None, original)
    original.append('HOME')
    assert verdict.expected == ('NODE_PANEL',)


@pytest.mark.parametrize('reason', ['', '   ', None])
def test_verdict_cannot_omit_its_judgement_reason(reason):
    with pytest.raises(ValueError):
        TransitionVerdict('unjudged', None, ('NODE_PANEL',), reason)
