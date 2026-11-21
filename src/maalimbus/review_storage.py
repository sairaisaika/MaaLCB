"""Compact byte-identical, pending review mirrors; keep canonical observations.

Only legacy semantic frame and navigation queues are supported. No transaction, reviewed label,
model, canonical screenshot or proposal metadata is removed or rewritten.
"""
from pathlib import Path

from .learning_dataset import digest, local_file
from .storage import read_json


def original_byte_documents(root, *, image=None):
    """Untouched semantic proposals whose readers preserve cold original bytes.

    This grants no deletion, approval, training or business completion. Other
    review families and independent state/model/source/report references win.
    Already cold originals need no new raw-retirement eligibility.
    """
    root=Path(root).resolve();queue=root/'build/learning-review/frames';documents=set()
    if queue.is_symlink() or getattr(queue,'is_junction',lambda:False)():return documents
    for path in queue.glob('*/proposal.json'):
        try:
            value=read_json(local_file(root,path))
            fields=set(('schema_version episode locale frame image_sha256 native_record '
                'native_record_sha256 scene_proposal scene_teacher boxes model_sha256 '
                'gallery_sinner_index identity_observations reviewed complete '
                'training_eligible input_authorized').split())
            if (not isinstance(value,dict) or set(value)!=fields
                    or type(value['schema_version']) is not int or value['schema_version']!=1
                    or any(value[k] is not False for k in ('reviewed','complete','training_eligible','input_authorized'))
                    or not isinstance(value['episode'],str) or not value['episode']
                    or value['locale'] not in ('en','jp')
                    or value['scene_teacher']!='native_caption_observer_not_ground_truth'):
                continue
            review=read_json(local_file(root,path.parent/'review.json'))
            if not isinstance(review,dict) or set(review)!=set(
                    ('status approved corrected_boxes corrected_scene notes').split()):continue
            if (review['status']!='pending' or review['approved'] is not False
                    or review['corrected_boxes']!=[] or review['corrected_scene'] is not None
                    or review['notes']!=''):continue
            picture=Path(value.get('frame',''))
            if not picture.is_absolute():picture=root/picture
            if image is not None and picture!=image:continue
            if not picture.is_file():continue
            proposal,_,sources=_pending_sources(root,path)
            if any((proposal.parent/name).exists()
                    and digest(local_file(root,proposal.parent/name))!=digest(original)
                    for original,name in sources):continue
            documents.add(proposal)
        except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    return documents


def _pending_sources(root, proposal_path):
    proposal_path=local_file(root,proposal_path)
    proposal=read_json(proposal_path)
    review_path=local_file(root,proposal_path.parent/'review.json')
    review=read_json(review_path)
    if 'attempt' in proposal and 'scope' in proposal:
        return _pending_transition_sources(root,proposal_path,proposal,review_path,review)
    if (proposal.get('schema_version')!=1 or proposal.get('reviewed') is not False
            or proposal.get('training_eligible') is not False
            or review.get('status')!='pending' or review.get('approved') is not False
            or review.get('corrected_boxes') or review.get('corrected_scene')
            or review.get('notes')):
        raise ValueError('Only untouched pending semantic proposals can be compacted')
    frame=local_file(root,proposal['native_record'])
    image=local_file(root,proposal['frame'])
    if (not frame.resolve().is_relative_to(root/'evidence/runtime')
            or not image.resolve().is_relative_to(root/'evidence/runtime')
            or frame==image or frame.with_suffix('.png')!=image
            or digest(frame)!=proposal['native_record_sha256']
            or digest(image)!=proposal['image_sha256']
            or read_json(frame).get('image_sha256')!=proposal['image_sha256']):
        raise ValueError('Canonical review evidence hash binding differs')
    return proposal_path,review_path,((frame,'frame.json'),(image,'frame.png'))


def _pending_transition_sources(root,path,proposal,review_path,review):
    if (proposal.get('version')!=1 or proposal.get('reviewed') is not False
            or proposal.get('training_eligible') is not False
            or proposal.get('input_authorized') is not False
            or review.get('status')!='pending' or review.get('approved') is not False
            or review.get('corrected_label') or review.get('notes')):
        raise ValueError('Only untouched pending navigation proposals can be compacted')
    attempt=proposal['attempt'];sources=[]
    for prefix,identity in (('before',attempt['before']),('after',attempt['successor'])):
        record=local_file(root,identity['record']);image=local_file(root,identity['image'])
        if (not record.resolve().is_relative_to(root/'evidence/runtime')
                or record.with_suffix('.png')!=image or record==image
                or digest(record)!=identity['record_sha256']
                or digest(image)!=identity['image_sha256']
                or read_json(record).get('image_sha256')!=identity['image_sha256']):
            raise ValueError('Canonical navigation review evidence hash binding differs')
        sources.extend(((record,prefix+'.json'),(image,prefix+'.png')))
    return path,review_path,tuple(sources)


def compaction_plan(root, queue):
    """Read-only plan. Any corrupt/missing/reviewed entry stays untouched."""
    root=Path(root).resolve();queue=Path(queue).resolve()
    expected=tuple(root/('build/learning-review/'+kind) for kind in ('frames','transitions'))
    if queue not in expected:
        raise ValueError('Only the workspace semantic/navigation review queues are supported')
    rows=[];rejected=[]
    if not queue.exists():return dict(files=rows,rejected=rejected,reclaimable_bytes=0)
    if queue.is_symlink() or getattr(queue,'is_junction',lambda:False)():
        raise ValueError('Linked review queue')
    legacy_names = (('frame.json','frame.png') if queue.name == 'frames'
                    else ('before.json','before.png','after.json','after.png'))
    for proposal in sorted(queue.glob('*/proposal.json')):
        # Current proposals only reference the owner's canonical bytes. Do
        # not open or decompress that evidence solely to find there is no copy.
        if not any((proposal.parent/name).exists() for name in legacy_names):
            continue
        try:
            proposal,review,sources=_pending_sources(root,proposal)
            family='transitions' if 'attempt' in read_json(proposal) else 'frames'
            if proposal.parent.parent.name!=family:
                raise ValueError('Review proposal schema differs from queue')
            for original,name in sources:
                copied=proposal.parent/name
                if not copied.exists():continue
                copied=local_file(root,copied)
                if copied==original or digest(copied)!=digest(original):
                    raise ValueError('Legacy review mirror differs from canonical evidence')
            # Validate the entire pair before making either deletion eligible.
            for original,name in sources:
                copied=proposal.parent/name
                if copied.exists():
                    rows.append(dict(path=str(copied.relative_to(root)),
                        source=str(original.relative_to(root)),sha256=digest(original),
                        bytes=copied.stat().st_size,proposal=str(proposal.relative_to(root)),
                        proposal_sha256=digest(proposal),review_sha256=digest(review)))
        except (ValueError,KeyError,OSError,TypeError,AttributeError) as error:
            rejected.append(dict(proposal=str(proposal.relative_to(root)),reason=str(error)))
    return dict(files=rows,rejected=rejected,reclaimable_bytes=sum(x['bytes'] for x in rows))


def compact(root, queue, plan):
    """Revalidate the whole plan before unlinking exact files, never directories."""
    root=Path(root).resolve()
    current=compaction_plan(root,queue)
    if current!=plan:raise ValueError('Review compaction plan changed; nothing removed')
    removed=[]
    for row in current['files']:
        # Recheck immediately before each unlink as well as the whole-plan check.
        copied=local_file(root,row['path']);original=local_file(root,row['source'])
        proposal,review,_=_pending_sources(root,root/row['proposal'])
        if (digest(copied)!=row['sha256'] or digest(original)!=row['sha256']
                or digest(proposal)!=row['proposal_sha256'] or digest(review)!=row['review_sha256']):
            raise ValueError('Review evidence changed during compaction')
        copied.unlink()
        removed.append(row['path'])
    return dict(removed=removed,freed_bytes=sum(x['bytes'] for x in current['files']),
                canonical_evidence_removed=False,review_metadata_changed=False)
