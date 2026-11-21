"""Sampling bounds optional proposals, never existing reviews or gameplay."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maalimbus.learning_dataset import digest
from maalimbus.semantic_labels import persist_frame_proposals
from maalimbus.storage import read_json,write_json


def capture(root,n,scene='MAP',neural=None):
    folder=root/'evidence/runtime/current';folder.mkdir(parents=True,exist_ok=True)
    png=folder/f'frame-{n:04}.png'
    cv2.imwrite(str(png),np.full((32,32,3),n,np.uint8))
    record=png.with_suffix('.json')
    write_json(record,dict(size=[32,32],image_sha256=digest(png),scene=scene,
                           ocr=[],neural_sinners=neural or {}))
    return record


def queue(root,frame,episode='episode-a',locale='en',limit=32):
    return persist_frame_proposals(root,frame,episode,locale,
        root/'build/learning-review/frames',sample_limit=limit)


def snapshot(folder):return {p:p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def test_repeated_empty_scene_preserves_one_candidate_and_manual_correction(tmp_path):
    first=capture(tmp_path,1)
    result=queue(tmp_path,first)
    folder=Path(result['proposal']).parent
    review=read_json(folder/'review.json');review.update(status='approved',approved=True,
        corrected_scene='NODE_PANEL',notes='human correction')
    write_json(folder/'review.json',review)
    second=capture(tmp_path,2)
    before=snapshot(tmp_path/'build')
    skipped=queue(tmp_path,second)
    assert skipped['status']=='sampled_out'
    assert skipped['reason']=='empty_scene_representative_already_retained'
    assert not skipped['training_eligible'] and not skipped['input_authorized']
    assert snapshot(tmp_path/'build')==before
    assert queue(tmp_path,first)['proposal']==result['proposal']
    assert snapshot(tmp_path/'build')==before


def test_episode_cap_keeps_old_bytes_and_does_not_create_new_metadata(tmp_path):
    queue(tmp_path,capture(tmp_path,1,'MAP'),limit=2)
    queue(tmp_path,capture(tmp_path,2,'UNKNOWN'),limit=2)
    third=capture(tmp_path,3,'BATTLE_HUD');before=snapshot(tmp_path/'build')
    result=queue(tmp_path,third,limit=2)
    assert result['reason']=='episode_frame_proposal_limit'
    assert result['retained_candidates']==2
    assert snapshot(tmp_path/'build')==before


def test_another_episode_locale_or_scene_has_its_own_representative(tmp_path):
    assert queue(tmp_path,capture(tmp_path,1))['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,2,'UNKNOWN'))['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,3),episode='episode-b')['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,4),locale='jp')['status']=='queued'


def test_real_object_candidates_are_not_treated_as_empty_scene_repeats(tmp_path,monkeypatch):
    # Inference/teacher validation has separate tests; isolate admission here.
    import maalimbus.sinner_detection as teacher
    monkeypatch.setattr(teacher,'proposals',lambda *args:[{'class_id':0,'box':[1,1,20,20]}])
    neural=dict(status='shadow',boxes=[dict(class_id=0,box=[1,1,20,20],score=.99)])
    assert queue(tmp_path,capture(tmp_path,1,'PRE_BATTLE_TEAM',neural),limit=2)['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,2,'PRE_BATTLE_TEAM',neural),limit=2)['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,3,'PRE_BATTLE_TEAM',neural),limit=2)['reason']=='episode_frame_proposal_limit'


def test_explicit_offline_collection_remains_unsampled(tmp_path):
    assert queue(tmp_path,capture(tmp_path,1),limit=None)['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,2),limit=None)['status']=='queued'


def test_empty_history_cannot_starve_real_object_review(tmp_path,monkeypatch):
    import maalimbus.sinner_detection as teacher
    monkeypatch.setattr(teacher,'proposals',lambda *args:[{'class_id':0,'box':[1,1,20,20]}])
    # Simulate the legacy unsampled queue. Keep every old proposal/review byte.
    queue(tmp_path,capture(tmp_path,1,'MAP'),limit=None)
    queue(tmp_path,capture(tmp_path,2,'MAP'),limit=None)
    queue(tmp_path,capture(tmp_path,3,'UNKNOWN'),limit=None)
    old=snapshot(tmp_path/'build')
    neural=dict(status='shadow',boxes=[dict(class_id=0,box=[1,1,20,20],score=.99)])
    assert queue(tmp_path,capture(tmp_path,4,'PRE_BATTLE_TEAM',neural),limit=2)['status']=='queued'
    assert queue(tmp_path,capture(tmp_path,5,'PRE_BATTLE_TEAM',neural),limit=2)['status']=='queued'
    skipped=queue(tmp_path,capture(tmp_path,6,'PRE_BATTLE_TEAM',neural),limit=2)
    assert skipped['sample_bucket']=='objects' and skipped['retained_candidates']==2
    assert skipped['retained_episode_total']==5
    assert all(p.read_bytes()==body for p,body in old.items())
    before=snapshot(tmp_path/'build')
    assert queue(tmp_path,capture(tmp_path,7,'BATTLE_HUD'),limit=2)['sample_bucket']=='empty'
    assert snapshot(tmp_path/'build')==before


@pytest.mark.parametrize('limit',[False,0,-1,257,'32'])
def test_invalid_sampling_limit_does_not_create_a_queue(tmp_path,limit):
    with pytest.raises(ValueError,match='sampling limit'):
        queue(tmp_path,capture(tmp_path,1),limit=limit)
    assert not (tmp_path/'build').exists()
