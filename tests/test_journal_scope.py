"""Absent producer fields are not explicit null/conflicting scope facts."""
import copy
import pytest
from maalimbus.native_evidence import journal_scope


def test_missing_start_field_can_use_an_existing_explicit_episode_without_mutation():
    rows=[{'event':'mirror_loop_start'},
          {'event':'semantic_frame_proposal','episode':'scope'},
          {'event':'map_observed','episode':'foreign'}]
    before=copy.deepcopy(rows)
    assert journal_scope(rows)=='scope'
    assert rows==before


def test_matching_typed_producers_bind_one_recording():
    assert journal_scope([{'event':'mirror_loop_start','run_scope':'scope'},
        {'event':'semantic_frame_proposal','episode':'scope'}])=='scope'


@pytest.mark.parametrize('invalid',[None,'',' ',[],{},0,False])
@pytest.mark.parametrize('producer,key',[('mirror_loop_start','run_scope'),
                                        ('semantic_frame_proposal','episode')])
def test_present_invalid_fact_cannot_be_hidden_by_a_valid_episode(producer,key,invalid):
    assert journal_scope([{'event':producer,key:invalid},
        {'event':'semantic_frame_proposal','episode':'scope'}]) is None


@pytest.mark.parametrize('rows',[
    [],[{'event':'mirror_loop_start'}],
    [{'event':'other','run_scope':'scope','episode':'scope'}],
    [{'event':'mirror_loop_start','run_scope':'a'},
     {'event':'semantic_frame_proposal','episode':'b'}],
    [{'event':[],'run_scope':'scope'}],['not a record'],
])
def test_missing_untyped_or_conflicting_facts_never_guess_scope(rows):
    assert journal_scope(rows) is None
