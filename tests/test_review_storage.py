"""Compression keeps canonical evidence and pending labels, never self-approves."""
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

from maalimbus.learning_dataset import digest
from maalimbus.semantic_labels import persist_frame_proposals
from maalimbus.review_storage import compaction_plan,compact
from maalimbus.storage import read_json,write_json
from maalimbus.workspace import protected_evidence


def sample(root,*,legacy=True):
    run=root/'evidence/runtime/episode-a';run.mkdir(parents=True)
    image=run/'frame-0001.png';frame=image.with_suffix('.json')
    cv2.imwrite(str(image),np.zeros((32,32,3),np.uint8))
    write_json(frame,dict(size=[32,32],image_sha256=digest(image),scene='MAP',ocr=[]))
    queue=root/'build/learning-review/frames'
    result=persist_frame_proposals(root,frame,'episode-a','en',queue)
    folder=Path(result['proposal']).parent
    if legacy:
        shutil.copyfile(frame,folder/'frame.json');shutil.copyfile(image,folder/'frame.png')
    return queue,folder,frame,image


def test_new_queue_stores_references_pins_originals_and_is_idempotent(tmp_path):
    queue,folder,frame,image=sample(tmp_path,legacy=False)
    proposal=read_json(folder/'proposal.json')
    assert not (folder/'frame.png').exists() and not (folder/'frame.json').exists()
    assert (tmp_path/proposal['frame'])==image
    assert proposal['image_sha256']==digest(image)
    assert {frame,image}<=protected_evidence(tmp_path)
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    persist_frame_proposals(tmp_path,frame,'episode-a','en',queue)
    assert before=={p.name:p.read_bytes() for p in folder.iterdir()}


def test_reference_only_queue_never_opens_originals_during_compaction(tmp_path, monkeypatch):
    queue, _, _, _ = sample(tmp_path, legacy=False)
    from maalimbus import review_storage

    def unexpected_read(*args):
        pytest.fail('Only entries with legacy copies should resolve canonical originals')

    monkeypatch.setattr(review_storage, '_pending_sources', unexpected_read)
    assert compaction_plan(tmp_path, queue) == dict(files=[], rejected=[], reclaimable_bytes=0)


def test_legacy_compaction_only_unlinks_copies_preserves_metadata_and_originals(tmp_path):
    queue,folder,frame,image=sample(tmp_path)
    originals={p:p.read_bytes() for p in (frame,image,folder/'proposal.json',folder/'review.json',folder/'trace.log')}
    plan=compaction_plan(tmp_path,queue)
    assert len(plan['files'])==2 and not plan['rejected']
    result=compact(tmp_path,queue,plan)
    assert result['freed_bytes']==plan['reclaimable_bytes']>0
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert not read_json(folder/'proposal.json')['training_eligible']
    assert not read_json(folder/'review.json')['approved']
    assert compaction_plan(tmp_path,queue)['files']==[]


@pytest.mark.parametrize('fault',['missing_source','changed_source','changed_copy','reviewed','correction','notes'])
def test_unproved_or_reviewed_evidence_is_not_a_cleanup_candidate(tmp_path,fault):
    queue,folder,frame,image=sample(tmp_path)
    if fault=='missing_source':image.unlink()
    elif fault=='changed_source':image.write_bytes(b'changed')
    elif fault=='changed_copy':(folder/'frame.png').write_bytes(b'changed')
    else:
        review=read_json(folder/'review.json')
        review.update(dict(reviewed=dict(status='approved',approved=True),
            correction=dict(corrected_scene='HOME'),notes=dict(notes='human investigation'))[fault])
        write_json(folder/'review.json',review)
    plan=compaction_plan(tmp_path,queue)
    assert not plan['files'] and len(plan['rejected'])==1
    compact(tmp_path,queue,plan)
    assert (folder/'frame.png').exists() and (folder/'frame.json').exists()


def test_changed_plan_is_rejected_before_any_unlink(tmp_path):
    queue,folder,frame,image=sample(tmp_path)
    plan=compaction_plan(tmp_path,queue)
    (folder/'frame.png').write_bytes(b'new evidence')
    with pytest.raises(ValueError,match='plan changed'):compact(tmp_path,queue,plan)
    assert (folder/'frame.json').exists()


def test_arbitrary_queue_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='Only the workspace'):
        compaction_plan(tmp_path,tmp_path/'assets')


def test_existing_legacy_copy_conflict_is_not_silently_replaced(tmp_path):
    queue,folder,frame,image=sample(tmp_path)
    (folder/'frame.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Conflicting immutable frame-review'):
        persist_frame_proposals(tmp_path,frame,'episode-a','en',queue)
    assert (folder/'frame.png').read_bytes()==b'changed'


def transition_sample(root):
    from maalimbus.unknown_exploration import Exploration
    from test_unknown_exploration import frame
    run=root/'evidence/runtime/navigation';run.mkdir(parents=True)
    before,record=frame(run,'frame-0001');after,_=frame(run,'frame-0002','MAP',20)
    queue=root/'build/learning-review/transitions'
    transaction=Exploration(root/'config/navigation.json',queue,'run')
    transaction.reserve(before,transaction.choose(record),(10,6),450)
    proposal=Path(transaction.finish(after,'MAP')['proposal']);folder=proposal.parent
    identity=read_json(proposal)['attempt']
    for prefix,item in [('before',identity['before']),('after',identity['successor'])]:
        shutil.copyfile(item['record'],folder/(prefix+'.json'))
        shutil.copyfile(item['image'],folder/(prefix+'.png'))
    return queue,folder,before,after


def test_navigation_compaction_keeps_original_pins_and_all_review_and_state_bytes(tmp_path):
    queue,folder,before,after=transition_sample(tmp_path)
    protected=protected_evidence(tmp_path)
    assert {before,after,before.with_suffix('.png'),after.with_suffix('.png')}<=protected
    preserve=[before,after,before.with_suffix('.png'),after.with_suffix('.png'),
              folder/'proposal.json',folder/'review.json',tmp_path/'config/navigation.json']
    originals={p:p.read_bytes() for p in preserve}
    plan=compaction_plan(tmp_path,queue)
    assert len(plan['files'])==4 and not plan['rejected']
    compact(tmp_path,queue,plan)
    assert originals=={p:p.read_bytes() for p in preserve}
    assert protected_evidence(tmp_path)==protected
    assert compaction_plan(tmp_path,queue)['files']==[]


@pytest.mark.parametrize('fault',['canonical_changed','copy_changed','review_approved','human_notes','corrected_label'])
def test_navigation_proof_or_human_changes_refuse_compaction(tmp_path,fault):
    queue,folder,before,after=transition_sample(tmp_path)
    if fault=='canonical_changed':before.with_suffix('.png').write_bytes(b'changed')
    elif fault=='copy_changed':(folder/'before.png').write_bytes(b'changed')
    else:
        review=read_json(folder/'review.json')
        review.update({'review_approved':dict(approved=True,status='approved'),
                       'human_notes':dict(notes='Keep for investigation'),
                       'corrected_label':dict(corrected_label='NOT_MAP')}[fault])
        write_json(folder/'review.json',review)
    plan=compaction_plan(tmp_path,queue)
    assert not plan['files'] and len(plan['rejected'])==1
    assert all((folder/name).exists() for name in ['before.json','before.png','after.json','after.png'])
