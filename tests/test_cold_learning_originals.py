"""Lossless originals do not approve proposals or weaken independent raw needs."""
import json
from pathlib import Path

import numpy as np
import pytest

from maalimbus import capture_retention, learning_dataset as data
from maalimbus import native_image_archive as archive
from maalimbus.native_evidence import frame_reference
from maalimbus.review_storage import original_byte_documents
from maalimbus.semantic_labels import persist_frame_proposals
from test_archive_page_ownership import closed_original


def pending(root,episode='real-run'):
    path,pixels,record=closed_original(root,'MAP')
    answer=persist_frame_proposals(root,path,episode,'en',root/'build/learning-review/frames')
    assert answer['status']=='queued'
    return path,pixels,Path(answer['proposal'])


def test_pending_original_keeps_identity_pixels_manifest_and_authority_when_cold(tmp_path):
    path,pixels,proposal=pending(tmp_path);image=path.with_suffix('.png')
    files=[path,proposal,proposal.parent/'review.json']
    before={p:p.read_bytes() for p in files};reference=frame_reference(path)
    original_image=data.read_image(data.local_file(tmp_path,image))
    row=dict(frame=image.relative_to(tmp_path).as_posix(),proof=path.relative_to(tmp_path).as_posix(),
             reviewed=True,episode='real-run',label='MAP')
    manifest=data.manifest(tmp_path,[row])
    assert proposal in original_byte_documents(tmp_path)
    assert image in capture_retention._reference_keep(tmp_path)
    assert image not in capture_retention.archive_reference_keep(tmp_path)
    assert archive.compact(tmp_path)['files']==1
    assert not image.exists()
    assert data.local_file(tmp_path,image)==image
    assert data.original_bytes(image)==pixels
    assert data.digest(image)==archive.sha(pixels)
    assert np.array_equal(data.read_image(image),original_image)
    assert frame_reference(path)==reference
    assert data.manifest(tmp_path,[row])==manifest
    assert not manifest['training_ready'] and not manifest['input_authorized']
    assert {p:p.read_bytes() for p in files}==before
    assert image in capture_retention._reference_keep(tmp_path),'Permanent deletion still protects pending review'
    assert json.loads(proposal.read_bytes())['reviewed'] is False
    assert not image.exists(),'Read-only consumers cannot implicitly materialize PNGs'


@pytest.mark.parametrize('fault',['approved','notes','corrected_boxes','corrected_scene',
    'extra_review_field','extra_proposal_field','complete','input_authorized','record_hash','png_hash','mirror'])
def test_changed_or_non_pending_review_keeps_raw_need(tmp_path,fault):
    path,pixels,proposal=pending(tmp_path);review=proposal.parent/'review.json'
    v=json.loads(proposal.read_bytes());r=json.loads(review.read_bytes())
    if fault=='approved':r['approved']=True
    elif fault=='notes':r['notes']='Human work in progress'
    elif fault=='corrected_boxes':r['corrected_boxes']=[dict(box=[1,1,2,2])]
    elif fault=='corrected_scene':r['corrected_scene']='HOME'
    elif fault=='extra_review_field':r['pending_transaction']=True
    elif fault=='extra_proposal_field':v['pending_transaction']=True
    elif fault in ('complete','input_authorized'):v[fault]=True
    elif fault=='record_hash':v['native_record_sha256']='0'*64
    elif fault=='png_hash':v['image_sha256']='0'*64
    elif fault=='mirror':(proposal.parent/'frame.png').write_bytes(b'conflicting legacy copy')
    proposal.write_text(json.dumps(v));review.write_text(json.dumps(r))
    assert original_byte_documents(tmp_path)==set()
    assert archive.candidates(tmp_path)==[]
    assert path.with_suffix('.png').read_bytes()==pixels


@pytest.mark.parametrize('fault',['unclosed','recent'])
def test_pending_role_never_grants_active_or_recent_session_archival(tmp_path,fault):
    path,pixels,_=pending(tmp_path)
    if fault=='unclosed':(path.parent/'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_start'))+'\n')
    else:
        import os
        os.utime(path.parent/'events.jsonl',(10000,10000))
    assert archive.candidates(tmp_path)==[]
    assert path.with_suffix('.png').read_bytes()==pixels


@pytest.mark.parametrize('owner',['pending','model','source','report','other_review'])
def test_independent_reference_wins_even_for_an_untouched_proposal(tmp_path,owner):
    path,pixels,proposal=pending(tmp_path)
    names={'pending':'config/pending.json','model':'assets/resource/base/model/inputs.json',
        'source':'docs/required.md','report':'build/acceptance.json',
        'other_review':'build/learning-review/transitions/other.json'}
    pin=tmp_path/names[owner];pin.parent.mkdir(parents=True,exist_ok=True)
    if owner=='source':pin.write_text(path.relative_to(tmp_path).as_posix())
    else:pin.write_text(json.dumps(dict(proof=str(path))))
    assert proposal in original_byte_documents(tmp_path)
    assert archive.candidates(tmp_path)==[]
    assert path.with_suffix('.png').read_bytes()==pixels


def test_human_review_changed_after_publication_prevents_raw_retirement(tmp_path,monkeypatch):
    path,pixels,proposal=pending(tmp_path);retire=archive.retire
    def human_edits(root,names):
        review=proposal.parent/'review.json';r=json.loads(review.read_bytes());r['notes']='Keep this raw for inspection'
        review.write_text(json.dumps(r));return retire(root,names)
    monkeypatch.setattr(archive,'retire',human_edits)
    assert archive.compact(tmp_path)['retired_bytes']==0
    assert path.with_suffix('.png').read_bytes()==pixels


@pytest.mark.parametrize('fault',['container','raw','foreign','missing_json'])
def test_cold_readers_refuse_corruption_and_foreign_roots(tmp_path,fault):
    path,pixels,_=pending(tmp_path);assert archive.compact(tmp_path)['files']==1
    image=path.with_suffix('.png')
    if fault=='container':
        entry=archive.load_index(tmp_path)['members'][image.relative_to(tmp_path).as_posix()]
        # Changing any actual container byte invalidates the original, even warm.
        data.digest(image)
        target=tmp_path/entry['archive'];body=bytearray(target.read_bytes());body[-1]^=1;target.write_bytes(body)
    elif fault=='raw':
        image.write_bytes(b'corrupt raw takes precedence')
        assert data.digest(image)!=archive.sha(pixels)
    elif fault=='foreign':
        with pytest.raises(ValueError,match='outside'):data.local_file(tmp_path/'other',image)
        return
    else:path.unlink()
    with pytest.raises((ValueError,OSError)):
        if fault=='container':data.local_file(tmp_path,image)
        else:frame_reference(path)


@pytest.mark.parametrize('resize',[False,True])
def test_actual_reviewed_sinner_export_has_same_bytes_and_pixels_when_cold(tmp_path,resize):
    from maalimbus.sinner_dataset import manifest,export,verify_export,split
    episode=next(str(i) for i in range(20) if split(str(i))=='train')
    path,pixels,proposal=pending(tmp_path,episode);image=path.with_suffix('.png')
    from maalimbus.sinner_detection import LABELS
    boxes=[dict(label=LABELS[0],box=[1,1,10,10])]
    # Independent explicit review; the pending proposal itself is never approved.
    proof=tmp_path/'independent-human-review.json'
    proof.write_text(json.dumps(dict(episode=episode,locale='en',boxes=boxes,reviewed=True,
        complete=True,review_method='human_card_boundary',image_sha256=archive.sha(pixels))))
    row=dict(frame=image.relative_to(tmp_path).as_posix(),proof=proof.name,
             episode=episode,locale='en',reviewed=True,complete=True,boxes=boxes)
    value=manifest(tmp_path,[row],minimum=1)
    export(tmp_path,value,tmp_path/'raw-export',research=True,native_resize=resize)
    assert archive.compact(tmp_path)['retired_bytes']==len(pixels)
    assert manifest(tmp_path,[row],minimum=1)==value
    export(tmp_path,value,tmp_path/'cold-export',research=True,native_resize=resize)
    assert verify_export(tmp_path,tmp_path/'cold-export',research=True)==value
    raw=next((tmp_path/'raw-export/images').rglob('*.png'))
    cold=next((tmp_path/'cold-export/images').rglob('*.png'))
    assert raw.read_bytes()==cold.read_bytes()
    assert json.loads(proposal.read_bytes())['reviewed'] is False
    assert not image.exists()


def test_an_ancestor_archive_cannot_satisfy_another_project_root(tmp_path,monkeypatch):
    # Both paths satisfy the outer archive's canonical namespace, while the
    # inner consumer explicitly declares a different project root.
    inner=tmp_path/'evidence/runtime/nested-project'
    path,pixels,_=closed_original(inner,'MAP');image=path.with_suffix('.png')
    entry=dict(path=image.relative_to(tmp_path).as_posix(),bytes=len(pixels),
        sha256=archive.sha(pixels),record_sha256=archive.sha(path.read_bytes()))
    monkeypatch.setattr(archive,'candidates',lambda root:[entry])
    assert archive.compact(tmp_path)['retired_bytes']==len(pixels)
    assert archive.read_png(image)==pixels,'The generic reader can find the ancestor'
    with pytest.raises(ValueError,match='missing'):data.local_file(inner,image)
