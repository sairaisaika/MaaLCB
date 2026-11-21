"""Existing full-body position must reach its native/navigation consumers."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import cv2
import numpy as np
import pytest

from maalimbus import map_vision,runner
from maalimbus.native_evidence import frame_reference
from maalimbus.native_image_archive import read_png
from maalimbus.vision import Text

ROOT=Path(__file__).resolve().parents[1]
CAPTURES=ROOT/'evidence/runtime/packaged-mirror-20261118-080819'
# Both tests read original(), a frame of this run.
pytestmark=pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261118-080819')
sys.path.insert(0,str(ROOT/'agent'))
import recognition


def original(number):
    # Literal owned fixtures also let the source-reference scanner retain the
    # required raw images after these sessions leave the recent-history window.
    names={6:'frame-0006.json',18:'frame-0018.json',20:'frame-0020.json',24:'frame-0024.json'}
    path=CAPTURES/names[number]
    reference,record=frame_reference(path)
    image=cv2.imdecode(np.frombuffer(read_png(path.with_suffix('.png')),np.uint8),cv2.IMREAD_COLOR)
    assert list(reference.size)==[image.shape[1],image.shape[0]]
    return image,record


@pytest.mark.parametrize('number,expected',[(6,(913,485)),(18,(967,607)),(20,(672,607))])
def test_panned_native_train_anchor_is_not_its_flame_or_neighbouring_badge(number,expected):
    image,_=original(number);before=image.copy()
    assert map_vision.locomotive_marker(image)==expected
    assert runner.party_point(image)==expected
    assert map_vision.party_point(image)==expected
    assert map_vision.party_tracked(image)==(expected,'locomotive')
    assert np.array_equal(image,before)


@pytest.mark.parametrize('scene,number',[('MAP',18),('UNKNOWN_DIALOG',24)])
def test_native_observation_owns_one_controller_and_its_map_only_position(monkeypatch,scene,number):
    image,raw=original(number);events=[]

    class Borrowed:
        def __init__(self,owner,generation):self.owner=owner;self.generation=generation
        @property
        def cached_image(self):
            assert self.generation==self.owner.lookups,'borrowed controller replaced'
            return image

    class Owner:
        lookups=0
        @property
        def controller(self):
            self.lookups+=1
            return Borrowed(self,self.lookups)

    owner=Owner();captured=[]
    monkeypatch.setattr(recognition,'screencap',lambda controller,timeout:captured.append(controller))
    if scene!='MAP':
        def forbidden(_):raise AssertionError('A non-MAP page cannot project a map party')
        monkeypatch.setattr(recognition,'party_point',forbidden)
    tokens=[Text(row['text'],tuple(row['box']),row['score']) for row in raw['ocr']]
    reader=SimpleNamespace(callback_failure=None,
        journal=SimpleNamespace(directory=CAPTURES,
            record=lambda event,**data:events.append(dict(event=event,**data))),
        observe=lambda context,pixels:(tokens,scene,'frame-%04d'%number),timing_fields=lambda:{})
    action=recognition.MapObservation(reader)
    answer=action.run(SimpleNamespace(tasker=owner),SimpleNamespace(node_name='WindowMapObserve'))
    assert reader.callback_failure is None,reader.callback_failure
    assert answer is (scene=='MAP')
    assert owner.lookups==1 and len(captured)==1
    observed=next(row for row in events if row['event']=='map_observed')
    assert observed['map_player']==([967,607] if scene=='MAP' else None)
    assert observed['input_sent'] is False and observed['verified_clear'] is False
