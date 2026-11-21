"""Viewport transforms cannot keep pre-transform measurements or click boxes."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from maalimbus import runner,map_dispatch
from maalimbus.storage import write_json


def fixture(tmp_path,monkeypatch,successors=('MAP','MAP')):
    records=[]
    for n,scene in enumerate(('MAP',*successors),1):
        record=dict(frame=f'frame-{n:04}',scene=scene,size=[1920,1080],ocr=[],
                    image_sha256=str(n)*64,map_party=[100*n,300])
        write_json(tmp_path/(record['frame']+'.json'),record);records.append(record)
    calls=[];queue=iter(records[1:])
    def click(*args,**kw):raise AssertionError('no ordinary click permitted')
    device=SimpleNamespace(controller=object(),click=click,
        pinch=lambda *args:calls.append(('zoom',)),
        swipe=lambda *args:calls.append(('drag',args)))
    loop=runner.MirrorRunner(device,settings=dict(interval=0),directory=tmp_path)
    monkeypatch.setattr(loop,'_observe',lambda **kw:next(queue))
    monkeypatch.setattr(runner,'frame_for',lambda directory,r:
        (np.full((4,4,3),int(r['frame'][-1]),np.uint8),r['frame']))
    monkeypatch.setattr(runner,'party_point',lambda im:(100*int(im[0,0,0]),300))
    monkeypatch.setattr(runner,'pinch_out',lambda *args,**kw:
        (_ for _ in ()).throw(AssertionError('viewport bypassed the shared device owner')))
    return loop,records,calls


def normalisation_probe(monkeypatch):
    measured=[]
    def normalise(measure,zoom,drag):
        measured.append(measure()[0]);zoom();measured.append(measure()[0])
        drag(100,0);measured.append(measure()[0])
        return dict(zoomed=True,dragged=1,steps=measured,centred=True)
    monkeypatch.setattr(runner,'normalise_view',normalise)
    return measured


def test_every_measurement_and_returned_record_uses_the_post_gesture_capture(tmp_path,monkeypatch):
    loop,records,calls=fixture(tmp_path,monkeypatch)
    measured=normalisation_probe(monkeypatch)
    current=loop._normalise_view_once(records[0])
    assert measured==[(100,300),(200,300),(300,300)]
    assert current is records[2] and [c[0] for c in calls]==['zoom','drag']


def test_whole_step_offers_the_fresh_record_to_candidate_measurement(tmp_path,monkeypatch):
    loop,records,calls=fixture(tmp_path,monkeypatch);normalisation_probe(monkeypatch)
    queue=iter(records);monkeypatch.setattr(loop,'_observe',lambda **kw:next(queue))
    class CandidatesReached(Exception):pass
    def candidates(directory,record,**kw):
        assert record is records[2]
        assert kw['fallback_party'] is None
        raise CandidatesReached()
    loop.state.update(map_party_point=dict(point=[999,999],at=runner.time.monotonic()),
                      map_party_floor=1,map_floor=1,last_party=[999,999])
    monkeypatch.setattr(runner,'candidates_of',candidates)
    with pytest.raises(CandidatesReached):loop.step()
    assert [c[0] for c in calls]==['zoom','drag']


@pytest.mark.parametrize('scene',['UNKNOWN','GIFT_PICK'])
def test_a_non_map_after_zoom_forbids_drag_and_returns_for_a_fresh_step(tmp_path,monkeypatch,scene):
    loop,records,calls=fixture(tmp_path,monkeypatch,(scene,))
    queue=iter(records);monkeypatch.setattr(loop,'_observe',lambda **kw:next(queue))
    # Use the actual bounded normalisation loop, not the probe.
    result=loop.step()
    assert result['waiting'] and [c[0] for c in calls]==['zoom']
    assert loop.artifacts['steps'][-1]['reason']=='map_view_successor_requires_reobserve'


def test_missing_zoom_successor_never_falls_back_to_old_image_or_card(tmp_path,monkeypatch):
    loop,records,calls=fixture(tmp_path,monkeypatch,())
    queue=iter(records);monkeypatch.setattr(loop,'_observe',lambda **kw:next(queue))
    result=loop.step()
    assert result['waiting'] and [c[0] for c in calls]==['zoom']
    assert loop.artifacts['steps'][-1]['reason']=='map_view_successor_awaiting_capture'


@pytest.mark.parametrize('pending',['map_pending','map_unjudged'])
def test_pending_node_outcome_defers_view_and_keeps_every_byte_of_state(tmp_path,monkeypatch,pending):
    state=dict(map_committed=[10,20,30,40],map_party=[100,300],
               gift_pending=dict(title='keep',pending=True))
    state[pending]=[1,2,3,4] if pending=='map_pending' else dict(proof='keep')
    before=deepcopy(state)
    assert map_dispatch.prepare_view_change(state) is None and state==before
    loop,records,calls=fixture(tmp_path,monkeypatch)
    loop.state.update(state)
    assert loop._normalise_view_once(records[0]) is None
    assert calls==[] and 'view_normalised' not in loop.state
    assert all(loop.state[k]==v for k,v in before.items())


def test_view_change_retires_pixel_caches_but_not_business_intent_or_scope():
    business=dict(title='keep',pending=True)
    state=dict(map_committed=[10,20,30,40],map_party=[100,300],map_pending=None,
               scope='same',gift_pending=business)
    expired=map_dispatch.prepare_view_change(state)
    assert expired==dict(map_committed=[10,20,30,40],map_party=[100,300])
    assert state==dict(map_pending=None,scope='same',gift_pending=business)
    assert state['gift_pending'] is business


def test_absent_view_controller_keeps_coordinates_and_normalisation_unspent(tmp_path,monkeypatch):
    loop,records,calls=fixture(tmp_path,monkeypatch)
    loop.device.controller=None;loop.state['map_committed']=[10,20,30,40]
    assert loop._normalise_view_once(records[0]) is None
    assert loop.state['map_committed']==[10,20,30,40]
    assert calls==[] and 'view_normalised' not in loop.state


def test_recovery_pan_retires_old_commitment_without_faking_click_acceptance(tmp_path,monkeypatch):
    loop,records,calls=fixture(tmp_path,monkeypatch)
    loop.state['map_committed']=[10,20,30,40]
    monkeypatch.setattr(loop,'_recovery_gesture',lambda name:calls.append((name,)))
    result=loop._recover('MAP',loop.state,dict(reason='no_candidate_node_observed'),
                         dict(reason='no_candidate_node_observed',target=None))
    assert result['waiting'] and calls
    assert 'map_committed' not in loop.state
    assert not loop.artifacts['verified_clear'] and not loop.state.get('map_unjudged')


@pytest.mark.parametrize('pending',['map_pending','map_unjudged'])
def test_recovery_defers_a_view_gesture_while_preserving_the_pending_outcome(tmp_path,monkeypatch,pending):
    loop,records,calls=fixture(tmp_path,monkeypatch)
    original=dict(target=[10,20,30,40],proof='keep')
    loop.state.update(map_committed=[10,20,30,40],**{pending:original})
    monkeypatch.setattr(loop,'_recovery_gesture',lambda name:calls.append((name,)))
    result=loop._recover('MAP',loop.state,dict(reason='no_candidate_node_observed'),
                         dict(reason='no_candidate_node_observed',target=None))
    assert result['waiting'] and not result['input_sent'] and not calls
    assert loop.state[pending] is original
    assert loop.state['map_committed']==[10,20,30,40]


@pytest.mark.parametrize('producer',['early_pinch','ladder'])
def test_every_recovery_producer_expires_coordinates_but_keeps_the_navigation_goal(tmp_path,monkeypatch,producer):
    loop,records,calls=fixture(tmp_path,monkeypatch)
    loop.state.update(map_committed=[10,20,30,40],navigation_probe_pending=True)
    monkeypatch.setattr(loop,'_recovery_gesture',lambda name:calls.append((name,)))
    method=loop._map_zoom_once if producer=='early_pinch' else loop._recover
    result=method('MAP',loop.state,dict(reason='no_candidate_node_observed'),
                  dict(reason='no_candidate_node_observed',target=[10,20,30,40]))
    assert result['waiting'] and calls
    assert 'map_committed' not in loop.state
    assert loop.state['navigation_probe_pending'] is True


def test_a_bright_page_glyph_is_kept_beside_larger_inactive_badges():
    clicks=[dict(box=[960,339,190,190],kind='gold_badge_node'),
            dict(box=[1033,546,40,40],kind='bright_lit_icon',point=[1053,559]),
            dict(box=[700,300,40,40],kind='badge_mark')]
    kept,info=runner.node_sized_boxes(clicks,width=1920)
    assert [row['kind'] for row in kept]==['gold_badge_node','bright_lit_icon']
    glyph=kept[1];x,y,w,h=glyph['box']
    assert x<=1053<x+w and y<=559<y+h and glyph['point']==(1053,559)
    kinds={runner.box_key(row['box']):row['kind'] for row in kept}
    assert runner.order_candidates([row['box'] for row in kept],kinds)[0]==glyph['box']
