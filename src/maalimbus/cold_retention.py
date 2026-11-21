"""Ordinary diagnostic deletion in the existing lossless PNG representation.

The capture-retention role reader grants eligibility. This module only rewrites
one immutable container, keeping exact survivor bytes and an ordered storage
receipt. No game state, pending action, review or model is changed.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import uuid

from . import native_image_archive as archive, workspace

JOURNAL='evidence/native-image-retirements.jsonl'
MAX_JOURNAL=16_000_000


def _hash(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def _append(root,row):
    body=_encoded(dict(record=row,sha256=archive.sha(_encoded(row))))+b'\n'
    path=archive.plain(root,JOURNAL)
    if (path.stat().st_size if path.exists() else 0)+len(body)>MAX_JOURNAL:
        raise ValueError('Cold retirement journal full; preserve originals')
    workspace.require_space(root,len(body)+8192)
    with path.open('ab') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())


def _states(root):
    path=archive.plain(root,JOURNAL)
    if not path.exists():return {}
    if path.stat().st_size>MAX_JOURNAL:raise ValueError('Cold retirement journal exceeds bound')
    states={}
    for line in path.read_bytes().splitlines():
        row=json.loads(line);record=row['record']
        if row.get('sha256')!=archive.sha(_encoded(record)):
            raise ValueError('Cold retirement receipt changed')
        operation=record['operation']
        if not isinstance(operation,str) or not re.fullmatch('[0-9a-f]{32}',operation):
            raise ValueError('Invalid cold retirement identity')
        if record['stage']=='intent':
            if operation in states:raise ValueError('Duplicate cold retirement intent')
            states[operation]=record
        elif record['stage'] in ('committed','rolled_back'):
            if operation not in states:raise ValueError('Cold retirement result without intent')
            states.pop(operation)
        else:raise ValueError('Unknown cold retirement stage')
    return states


def _verify(root,entries,*,metadata=True):
    """Validate canonical mapping, entire containers and original JSON bytes."""
    for name,entry in entries.items():
        if (not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts
                or Path(name).as_posix()!=name or not name.endswith('.png') or not name.startswith(
                ('evidence/runtime/','dist/MaaLimbus/evidence/runtime/'))):
            raise ValueError('Invalid cold original path')
        path=archive.plain(root,name);blob=entry['archive']
        if not re.fullmatch(re.escape(archive.BLOBS)+r'/[0-9a-f]{64}\.tar\.xz',blob):
            raise ValueError('Invalid cold container path')
        if Path(blob).name!=entry['archive_sha256']+'.tar.xz':
            raise ValueError('Cold container name differs from its digest')
        if metadata and (_hash(path.with_suffix('.json'))!=entry['record_sha256']
                or json.loads(path.with_suffix('.json').read_bytes()).get('image_sha256')!=entry['sha256']):
            raise ValueError('Cold original metadata changed')
        archive.archived_bytes(root,entry)


def _matches(index,before,expected):
    return all(index['members'].get(name)==expected.get(name) for name in before)


def _validate_intent(row):
    before,after=row['before'],row['after']
    old,new=row['old_archive'],row.get('new_archive')
    pattern=re.escape(archive.BLOBS)+r'/[0-9a-f]{64}\.tar\.xz'
    if (not isinstance(before,dict) or not before or not isinstance(after,dict)
            or not set(after)<set(before) or not isinstance(old,str) or not re.fullmatch(pattern,old)
            or any(e.get('archive')!=old for e in before.values())
            or (bool(after)!=(new is not None))):
        raise ValueError('Invalid cold retirement transition')
    if after and (not isinstance(new,str) or not re.fullmatch(pattern,new)
            or Path(new).name!=str(row.get('new_sha256'))+'.tar.xz'
            or any(e.get('archive')!=new or e.get('archive_sha256')!=row['new_sha256']
                   for e in after.values())):
        raise ValueError('Invalid staged cold container binding')
    for name,e in after.items():
        if {k:v for k,v in e.items() if k not in ('archive','archive_sha256')}!={
                k:v for k,v in before[name].items() if k not in ('archive','archive_sha256')}:
            raise ValueError('Cold survivor identity changed')


def recover(root):
    """Restore interrupted pre-unlink mappings; no new original retirement."""
    root=Path(root).resolve();count=0
    with archive.verified_reads():
        for operation,row in _states(root).items():
            _validate_intent(row)
            before,after=row['before'],row['after'];index=archive.load_index(root)
            old=archive.plain(root,row['old_archive'])
            if old.exists():
                # Restore original pixel access even when an external writer
                # changed JSON or the staged output. Keep original metadata
                # hashes; later native verification still rejects that change.
                _verify(root,before,metadata=False)
                if not (_matches(index,before,before) or _matches(index,before,after)):
                    raise ValueError('Interrupted cold mapping is ambiguous; preserve containers')
                if not _matches(index,before,before):
                    restored=deepcopy(index);restored['members'].update(before)
                    archive._publish(root,restored)
                _append(root,dict(operation=operation,stage='rolled_back'))
                # Only this intent's unreferenced staging output is disposable.
                if row.get('new_archive') and not any(e['archive']==row['new_archive']
                        for e in archive.load_index(root)['members'].values()):
                    staged=archive.plain(root,row['new_archive'])
                    if staged.exists() and _hash(staged)==row['new_sha256']:staged.unlink()
            elif _matches(index,before,after):
                # Unlink happened before its final receipt. Surviving bytes are
                # verified above; record that fact without performing another unlink.
                _verify(root,after)
                _append(root,dict(operation=operation,stage='committed',recovered=True))
            else:raise ValueError('Original cold container missing with ambiguous mapping')
            count+=1
    return count


def _snapshot(root):
    """Actual role-input bytes, not mtimes, across one serialized operation."""
    paths=set()
    for base in (root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime'):
        for pattern in ('*/frame-*.json','*/frame-*.png','*/events.jsonl'):
            paths.update(base.glob(pattern))
    paths.update((root/archive.BLOBS).glob('*.tar.xz'))
    return {p.relative_to(root).as_posix():_hash(archive.plain(root,p.relative_to(root)))
            for p in paths}


def _eligible(root,directory):
    from .capture_retention import diagnostic_groups
    groups=diagnostic_groups(root,directory,recent=8,raw_only=False)
    return [{p.relative_to(root).as_posix() for p,_,_ in group} for group in groups]


def reclaim(root,*,directory=None,max_containers=1):
    """Bounded deletion of already answered unreferenced cold diagnostics.

    Caller owns the existing controller lease. Whole causal components and all
    normal pending/review/state/model/source/report guards remain mandatory.
    """
    if type(max_containers) is not int or not 1<=max_containers<=8:
        raise ValueError('Cold retirement batch must contain one to eight containers')
    root=Path(root).resolve();before_size=workspace.size(root);retired={};rewrites=0
    with archive.verified_reads(),archive.deferred_progress():
        recover(root)
        snapshot=_snapshot(root);groups=_eligible(root,directory);index=archive.load_index(root)
        containers={}
        for name,entry in index['members'].items():containers.setdefault(entry['archive'],{})[name]=entry
        for blob,entries in containers.items():
            if not archive.plain(root,blob).is_file():continue  # Opt-in vault is read-only here.
            names=set(entries)
            remove=set().union(*(g for g in groups if g<=names)) if groups else set()
            if not remove:continue
            # An unfinished lossless retirement still owns its physical original.
            if any(archive.plain(root,name).exists() for name in names):continue
            _verify(root,entries)
            survivors={name:deepcopy(e) for name,e in entries.items() if name not in remove}
            body=b'';new_blob=None;new_sha=None
            if survivors:
                output=io.BytesIO();seen=set()
                with tarfile.open(fileobj=output,mode='w:xz',preset=6) as stream:
                    for entry in survivors.values():
                        member=entry['sha256']+'.png'
                        if member in seen:continue
                        seen.add(member);pixels=archive.archived_bytes(root,entry)
                        item=tarfile.TarInfo(member);item.size=len(pixels);stream.addfile(item,io.BytesIO(pixels))
                body=output.getvalue();new_sha=archive.sha(body)
                new_blob=archive.BLOBS+'/'+new_sha+'.tar.xz'
                for entry in survivors.values():entry.update(archive=new_blob,archive_sha256=new_sha)
            old=archive.plain(root,blob)
            if len(body)>=old.stat().st_size:continue
            # Verify unchanged role inputs and fresh strong references before
            # publishing. No pending-review lossless exemption is used here.
            if _snapshot(root)!=snapshot:raise ValueError('Cold diagnostic role inputs changed')
            from .capture_retention import _reference_keep
            protected=_reference_keep(root)
            if any(archive.plain(root,n) in protected or archive.plain(root,n).with_suffix('.json') in protected
                    for n in remove):continue
            current=archive.load_index(root)
            if current!=index:raise ValueError('Cold index changed during retirement')
            row=dict(operation=uuid.uuid4().hex,stage='intent',old_archive=blob,
                     new_archive=new_blob,new_sha256=new_sha,before=entries,after=survivors,
                     role='unreferenced_intermediate_capture',role_inputs_sha256=archive.sha(_encoded(snapshot)))
            updated=deepcopy(index)
            for name in entries:updated['members'].pop(name)
            updated['members'].update(survivors)
            index_bytes=len((json.dumps(updated,sort_keys=True,indent=2)+'\n').encode())
            receipt_bytes=len(_encoded(dict(record=row,sha256=archive.sha(_encoded(row)))))+2048
            if (old.stat().st_size-len(body)+archive.plain(root,archive.INDEX).stat().st_size
                    -index_bytes-receipt_bytes)<=0:continue
            required=len(body)+len(_encoded(row))*2+index_bytes+2_000_000+32768
            try:workspace.require_space(root,required)
            except ValueError:continue
            _append(root,row)
            try:
                if new_blob:
                    destination=archive.plain(root,new_blob)
                    if destination.exists():
                        if _hash(destination)!=new_sha:raise ValueError('Staged cold container changed')
                    else:
                        with destination.open('xb') as stream:
                            stream.write(body);stream.flush();os.fsync(stream.fileno())
                    _verify(root,survivors)
                archive._publish(root,updated);_verify(root,survivors)
                protected=_reference_keep(root)
                if any(archive.plain(root,n) in protected or archive.plain(root,n).with_suffix('.json') in protected
                        for n in remove):raise ValueError('New reference after cold publication')
                if _hash(old)!=next(iter(entries.values()))['archive_sha256']:
                    raise ValueError('Old cold container changed before unlink')
                # All role-input originals are still identical at this boundary;
                # the only addition since the snapshot is our new immutable blob.
                actual=_snapshot(root)
                if new_blob and new_blob not in snapshot:actual.pop(new_blob,None)
                if actual!=snapshot:raise ValueError('Cold proof changed before unlink')
                if archive.load_index(root)!=updated:raise ValueError('Published cold index changed')
                old.unlink()
                _append(root,dict(operation=row['operation'],stage='committed'))
            except Exception:
                recover(root)
                raise
            retired.update({n:entries[n]['sha256'] for n in remove});rewrites+=1;index=updated
            snapshot.pop(blob)
            if new_blob:snapshot[new_blob]=new_sha
            archive.completed_cold_retirement()
            if rewrites>=max_containers:break
    return dict(passed=True,retired=retired,containers=rewrites,freed_bytes=before_size-workspace.size(root),
                workspace_bytes=workspace.size(root),input_sent=False)
