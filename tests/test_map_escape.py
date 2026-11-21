"""The map's progress panel is the last answer, not the first (D91).

Live run packaged-mirror-20261024-040640: one refused node click offered the
progress control, the panel left the exploration, the entry dialog resumed it and
the next click was refused exactly as before -- 70 s spent without a single
recovery rung. The ladder is what a refused click should spend first.
"""
import json
import types
import pytest

import maalimbus.runner as runner


class _Journal:
    def __init__(self, directory):
        self.path = directory / 'events.jsonl'
        self.path.write_text('', encoding='utf-8')

    def record(self, event, **details):
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'event': event, **details}, ensure_ascii=False) + '\n')


def _events(tmp_path, name):
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return [row for row in rows if row['event'] == name]


def test_a_fresh_map_does_not_want_the_panel():
    assert runner.map_escape_wanted({}) is False


def test_the_ladder_answers_the_first_two_refusals():
    assert runner.map_escape_wanted({'map_refused_streak': 1}) is False
    assert runner.map_escape_wanted({'map_refused_streak': 2}) is False


def test_the_third_refusal_is_the_one_the_streak_names():
    assert runner.MAP_ESCAPE_REFUSALS == 3
    assert runner.map_escape_wanted({'map_refused_streak': 3}) is True
    assert runner.map_escape_wanted({'map_refused_streak': 9}) is True


def test_a_stale_or_missing_count_is_not_a_streak():
    assert runner.map_escape_wanted({'map_refused_streak': None}) is False
    assert runner.map_escape_wanted({'map_refused_streak': '2'}) is False


def test_the_third_refusal_also_names_the_unresumed_case(tmp_path):
    state = {}
    notes = []
    for _ in range(3):
        runner.map_refusal_streak(state, lambda name, **fields: notes.append((name, fields)))
    assert state['map_refused_streak'] == 3
    assert [name for name, _ in notes] == ['map_clicks_refused_while_the_exploration_may_be_unresumed']
    assert runner.map_escape_wanted(state) is True


def test_the_step_asks_the_helper_instead_of_counting_itself():
    text = open(runner.__file__, encoding='utf-8').read()
    assert "if page=='MAP' and map_escape_wanted(state):" in text
    assert "if page=='MAP' and int(state.get('map_refused_streak') or 0)>=1:" not in text


def test_whole_runner_reserves_one_resume_then_stops_before_another_roundtrip(tmp_path,monkeypatch):
    from maalimbus.storage import write_json
    record=dict(scene='MAP',frame='frame-0001',size=[1920,1080],image_sha256='a'*64,ocr=[
        dict(text='Exploring Floor 3',box=[60,130,350,40],score=.99),
        dict(text='Devoured Gluttony',box=[60,190,230,30],score=.99)])
    write_json(tmp_path/'frame-0001.json',record)
    successor=dict(record,scene='DUNGEON_PROGRESS',frame='frame-0002',image_sha256='b'*64)
    reads=iter([record,successor,successor]);device=runner.FakeDevice()
    loop=runner.MirrorRunner(device,directory=tmp_path,settings=dict(interval=0,rounds=1))
    loop.state['map_refused_streak']=3
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(reads))
    monkeypatch.setattr(loop,'_normalise_view_once',lambda r:None)
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a,**kw:None)
    monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:('frame-0001.png',[[1100,500,100,100]]))
    result=loop.step()
    assert result['input_sent'] and len(device.clicks)==1
    assert loop.state['map_resume_attempted']['frame']=='frame-0001'
    # A failed saved/resumed return is not node progress. Another three independently
    # judged no-ops must end before a second progress/pause input.
    for index in range(3):
        loop.state['map_unjudged']=dict(target=[1100+index,500,100,100],kind='lit_icon',frame='prior')
        loop._resolve_map_click('MAP',observation=record)
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    result=loop.step()
    assert result['done'] and not result['input_sent']
    assert result['stopped']=='map_resume_did_not_restore_navigation' and len(device.clicks)==1


def test_only_a_real_node_successor_clears_the_speculative_resume_goal(tmp_path):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    proof=dict(frame='before',image_sha256='a'*64)
    loop.state.update(map_resume_attempted=proof,resume_requested=True)
    loop.state['map_unjudged']=dict(target=[1000,500,30,30],kind='lit_icon',frame='before',expect=['NODE_PANEL','UNKNOWN'])
    assert loop._resolve_map_click('UNKNOWN')=='unjudged'
    assert loop.state['map_resume_attempted']==proof and loop.state['resume_requested']
    assert loop._resolve_map_click('NODE_PANEL')=='accepted'
    assert 'map_resume_attempted' not in loop.state and 'resume_requested' not in loop.state
    assert loop.device.clicks==[]


def test_only_untried_supported_destination_gets_a_probe_after_resume():
    from maalimbus import map_dispatch

    ticket = {'frame': 'before'}
    supported = [1200, 480, 120, 100]
    observed = {'scene': 'MAP', 'map_gold_path_supported': [supported]}
    for offered, expected in (([], False), ([supported], True)):
        state = dict(map_resume_return_pending=True, map_resume_attempted=ticket, map_refused_streak=3)
        assert not map_dispatch.resume_return_has_untried_path(state, {'scene': 'LOADING'}, offered)
        assert map_dispatch.resume_return_has_untried_path(state, observed, offered) is expected
        assert state['map_resume_attempted'] == ticket
        assert runner.map_escape_wanted(state) is not expected
        assert not map_dispatch.resume_return_has_untried_path(state, observed, offered)


@pytest.mark.parametrize('page',['HOME','DRIVE','MIRROR_ENTRY','RESUME_DIALOG','DUNGEON_PROGRESS','LOADING','UNKNOWN'])
def test_auxiliary_pages_do_not_renew_failed_navigation_budget(tmp_path,page):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    proof=dict(frame='before',image_sha256='a'*64)
    loop.state.update(map_resume_attempted=proof,resume_requested=True)
    loop.state['map_unjudged']=dict(target=[1000,500,30,30],kind='lit_icon',frame='before',expect=['NODE_PANEL','UNKNOWN'])
    assert loop._resolve_map_click(page)=='unjudged'
    assert loop.state['map_resume_attempted']==proof and loop.state['resume_requested']
    assert loop.device.clicks==[]
