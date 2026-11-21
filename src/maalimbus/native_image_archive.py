"""Lossless cold storage for unreferenced, closed native diagnostics.

Canonical JSON and encoded PNG bytes retain their identity. Publication precedes
retirement; an interrupted operation leaves readable originals or duplicates.
This layer never judges an input, settles a transaction, or changes a label.
"""
from pathlib import Path
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import io
import json
import os
import re
import tarfile

from . import workspace

INDEX = 'evidence/native-image-index.json'
BLOBS = 'evidence/native-image-blobs'
VAULT_POLICY = 'evidence/native-image-vault.json'
DEFAULT_VAULT_BYTES = 512_000_000
MAX_VAULT_BYTES = 768_000_000
MAX_MEMBER = 25_000_000
MAX_BATCH = 16_000_000
MAX_EXPANDED = 128_000_000
READ_CACHE_BYTES = 64_000_000
DEFERRED_PROGRESS_STAGES = 8
_reads = ContextVar('original_image_reads', default=None)


class _ReadSession:
    def __init__(self, max_bytes, on_progress=None, on_activity=None):
        self.max_bytes=max_bytes;self.bytes=0;self.peak_bytes=0
        self.members=OrderedDict();self.indexes=OrderedDict();self.shapes=OrderedDict()
        self.images=OrderedDict()
        self.streams=0;self.index_validations=0;self.retired_captures=0
        self.on_progress=on_progress
        self.on_activity=on_activity
        self.defer_depth=0;self.pending_progress=OrderedDict();self.retired_containers=0

    def remember(self, key, body):
        if key in self.members:self.bytes-=len(self.members.pop(key))
        if len(body)>self.max_bytes:return
        while self.bytes+len(body)>self.max_bytes:
            self.bytes-=len(self.members.popitem(last=False)[1])
        self.members[key]=body;self.bytes+=len(body)
        self.peak_bytes=max(self.peak_bytes,self.bytes)


@contextmanager
def verified_reads(*, max_bytes=None, on_progress=None, on_activity=None):
    """Share verified work only within one operation; never trust file metadata.

    The bound covers retained encoded PNG payload, not process RSS. Temporary
    container/member buffers retain the existing MAX_EXPANDED/MAX_MEMBER bounds.
    Index snapshots (at most two, each <=4MB encoded) and 4096 decoded sizes have
    separate fixed bounds. At most4096 decoded image identities may outlive the
    payload LRU in this operation; every reuse rehashes the actual container.
    Nested retention operations reuse their parent's scope.
    """
    if max_bytes is not None and (type(max_bytes) is not int or not 0<=max_bytes<=READ_CACHE_BYTES):
        raise ValueError('Invalid original image read cache bound')
    current=_reads.get()
    if current is not None:
        if max_bytes is not None and max_bytes!=current.max_bytes:
            raise ValueError('Nested original image read cache bound differs')
        previous=current.on_progress;previous_activity=current.on_activity
        if on_progress is not None:current.on_progress=on_progress
        if on_activity is not None:current.on_activity=on_activity
        try:yield current
        finally:current.on_progress=previous;current.on_activity=previous_activity
        return
    current=_ReadSession(READ_CACHE_BYTES if max_bytes is None else max_bytes,on_progress,on_activity)
    token=_reads.set(current)
    try:yield current
    finally:
        _reads.reset(token)
        current.members.clear();current.indexes.clear();current.shapes.clear();current.images.clear();current.bytes=0
        current.pending_progress.clear()


def _progress(session,milestone):
    if session.defer_depth:
        # The activity callback must be memory-only. Persistent observers would
        # otherwise mutate the very journal bytes their caller is guarding.
        if session.on_activity is not None:session.on_activity()
        if session.on_progress is not None:
            key=(id(session.on_progress),milestone['stage'])
            session.pending_progress[key]=(session.on_progress,dict(milestone))
            session.pending_progress.move_to_end(key)
            while len(session.pending_progress)>DEFERRED_PROGRESS_STAGES:
                session.pending_progress.popitem(last=False)
    elif session.on_progress is not None:session.on_progress(milestone)
    elif session.on_activity is not None:session.on_activity()


@contextmanager
def deferred_progress():
    """Keep byte-guarded inputs unchanged; deliver bounded reports afterwards.

    Only genuine completed work can touch the memory-only activity callback.
    A failed scope discards reports; it does not clear any business pending or
    relax the underlying byte guard. Nested scopes flush at the outer boundary.
    """
    session=_reads.get()
    if session is None:raise ValueError('Deferred progress requires a verified read session')
    session.defer_depth+=1;failed=False
    try:yield
    except BaseException:
        failed=True;session.pending_progress.clear();raise
    finally:
        session.defer_depth-=1
        if not session.defer_depth:
            pending=list(session.pending_progress.values());session.pending_progress.clear()
            if not failed:
                for callback,milestone in pending:callback(milestone)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def completed_retention_check():
    """Record completed proof work without mutating the journal being verified."""
    session = _reads.get()
    if session is not None and session.on_activity is not None:
        session.on_activity()


def completed_capture_retirement():
    """Report only after the caller's unlink and durable receipt both succeeded.

    Reuses the current storage-work observer; neither a cache hit nor a plan is
    completed retirement. This does not grant deletion or game-input authority.
    """
    session=_reads.get()
    if session is not None:
        session.retired_captures+=1
        _progress(session,dict(stage='reclaimed_native_capture',captures=session.retired_captures))


def completed_cold_retirement():
    """Called only after the existing cold commit receipt is durable."""
    session=_reads.get()
    if session is not None:
        session.retired_containers+=1
        _progress(session,dict(stage='reclaimed_cold_container',containers=session.retired_containers))


def plain(root, name):
    root=Path(root).resolve();path=root/name
    if not path.resolve().is_relative_to(root) or path==root:
        raise ValueError('Image archive path outside workspace')
    for part in (path,*path.parents):
        if workspace._linked(part):raise ValueError('Linked image archive path')
        if part==root:break
    return path


def vault_policy(root):
    """An explicitly opted-in fixed sibling directory, with a separate byte limit."""
    root=Path(root).resolve()
    marker=plain(root,VAULT_POLICY)
    if not marker.is_file():return None
    if marker.stat().st_size>1024:raise ValueError('Invalid native image vault policy')
    value=json.loads(marker.read_bytes())
    if (not isinstance(value,dict) or set(value)!={'version','budget_bytes'}
            or type(value['version']) is not int or value['version']!=1
            or type(value['budget_bytes']) is not int
            or not 0<value['budget_bytes']<=MAX_VAULT_BYTES):
        raise ValueError('Invalid native image vault policy')
    return plain(root.parent,root.name+'-cold-archive'),value['budget_bytes']


def archive_file(root, name):
    """Read through the existing digest index, preferring the workspace original."""
    local=plain(root,name)
    if local.exists():return local
    policy=vault_policy(root)
    if policy is not None and re.fullmatch(re.escape(BLOBS)+r'/[0-9a-f]{64}\.tar\.xz',name):
        return plain(policy[0],local.name)
    return local


def load_index(root):
    path=plain(root,INDEX)
    if not path.exists():return dict(version=1,members={})
    body=path.read_bytes();session=_reads.get();key=(str(path),sha(body))
    if session is not None and key in session.indexes:
        session.indexes.move_to_end(key)
        return deepcopy(session.indexes[key])
    value=json.loads(body)
    if session is not None:session.index_validations+=1
    if (not isinstance(value,dict) or value.get('version')!=1
            or not isinstance(value.get('members'),dict)):
        raise ValueError('Invalid native image archive index')
    for name,entry in value['members'].items():
        p=Path(name)
        if (p.is_absolute() or '..' in p.parts or p.as_posix()!=name
                or not (name.startswith('evidence/runtime/')
                        or name.startswith('dist/MaaLimbus/evidence/runtime/'))
                or p.suffix!='.png' or not isinstance(entry,dict)):
            raise ValueError('Invalid native image archive member')
        plain(root,name)
        archive=entry.get('archive','')
        if not archive.startswith(BLOBS+'/') or not archive.endswith('.tar.xz'):
            raise ValueError('Invalid native image archive container')
        plain(root,archive)
        for field in ('sha256','archive_sha256','record_sha256'):
            digest=entry.get(field)
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid native image archive digest')
        if type(entry.get('bytes')) is not int or not 0<entry['bytes']<=MAX_MEMBER:
            raise ValueError('Invalid native image archive size')
    if session is not None and len(body)<=4_000_000:
        session.indexes[key]=deepcopy(value)
        while len(session.indexes)>2:session.indexes.popitem(last=False)
    return value


def archived_bytes(root, entry):
    archive=archive_file(root,entry['archive'])
    if archive.stat().st_size>MAX_EXPANDED:raise ValueError('Native image archive exceeds its bound')
    body=archive.read_bytes()
    if sha(body)!=entry['archive_sha256']:raise ValueError('Native image archive hash changed')
    session=_reads.get();wanted=entry['sha256']+'.png'
    key=(str(archive),entry['archive_sha256'],wanted)
    if session is not None and key in session.members:
        found=session.members[key];session.members.move_to_end(key)
        if len(found)!=entry['bytes'] or sha(found)!=entry['sha256']:
            raise ValueError('Native image archive member hash changed')
        return found
    found=None;seen=set();total=0;staged=[];images=[]
    if session is not None:session.streams+=1
    # Streaming visits/decompresses a container once, rather than seeking back
    # through LZMA for each member. Publish cached bytes only after the complete
    # container is validated, so an unsafe later member cannot be hidden.
    with tarfile.open(fileobj=io.BytesIO(body),mode='r|xz') as handle:
        for member in handle:
            total+=member.size
            if (not member.isfile() or member.name in seen or member.size<=0
                    or member.size>MAX_MEMBER or total>MAX_EXPANDED
                    or not member.name.endswith('.png') or len(member.name)!=68
                    or any(c not in '0123456789abcdef' for c in member.name[:-4])):
                raise ValueError('Unsafe native image archive member')
            seen.add(member.name)
            pixels=handle.extractfile(member).read(MAX_MEMBER+1)
            if len(pixels)!=member.size or sha(pixels)+'.png'!=member.name:
                raise ValueError('Native image archive member hash changed')
            if member.name==wanted:found=pixels
            if session is not None:
                # Publish decoded identities only after the complete container
                # validates. Encoded payload eviction must not force provenance
                # readers to decompress unchanged bytes for each consumer again.
                shape=_png_size(pixels)
                images.append(((str(archive),entry['archive_sha256'],member.name,len(pixels)),shape))
                if len(images)>4096:images.pop(0)
                staged.append((member.name,pixels))
                # Do not retain an unbounded provisional container cache.
                while staged and sum(len(v) for _,v in staged)>session.max_bytes:
                    staged.pop(0)
    if found is None or len(found)!=entry['bytes'] or sha(found)!=entry['sha256']:
        raise ValueError('Native image archive member hash changed')
    if session is not None:
        for identity,shape in images:
            session.images[identity]=shape;session.images.move_to_end(identity)
            while len(session.images)>4096:session.images.popitem(last=False)
        for name,pixels in staged:
            session.remember((str(archive),entry['archive_sha256'],name),pixels)
        session.remember(key,found)
        _progress(session,dict(stage='validated_native_archive',streams=session.streams))
    return found


def verify_all(root):
    """Read every immutable container once, then verify all logical bindings."""
    index=load_index(root);groups={}
    for name,entry in index['members'].items():
        groups.setdefault(entry['archive'],[]).append((name,entry))
    for archive,entries in groups.items():
        path=archive_file(root,archive)
        if path.stat().st_size>MAX_EXPANDED:raise ValueError('Native image archive exceeds its bound')
        blob=path.read_bytes();digest=sha(blob);members={};total=0
        with tarfile.open(fileobj=io.BytesIO(blob),mode='r:xz') as handle:
            for member in handle:
                total+=member.size
                if (not member.isfile() or member.name in members or not 0<member.size<=MAX_MEMBER
                        or total>MAX_EXPANDED or len(member.name)!=68
                        or not member.name.endswith('.png')
                        or any(c not in '0123456789abcdef' for c in member.name[:-4])):
                    raise ValueError('Unsafe native image archive member')
                body=handle.extractfile(member).read(MAX_MEMBER+1)
                if sha(body)+'.png'!=member.name:raise ValueError('Native archive member hash changed')
                members[member.name]=len(body)
        for name,entry in entries:
            if digest!=entry['archive_sha256'] or members.get(entry['sha256']+'.png')!=entry['bytes']:
                raise ValueError('Native image archive binding differs')
            if sha(plain(root,name).with_suffix('.json').read_bytes())!=entry['record_sha256']:
                raise ValueError('Native image original JSON changed')
    return dict(passed=True,images=len(index['members']),containers=len(groups),input_sent=False)


def _original_source(path):
    """Resolve safe original storage; an existing raw file always wins."""
    path=Path(path).absolute()
    for parent in (path,*path.parents):
        if workspace._linked(parent):raise ValueError('Linked native image')
    if path.exists():return path,None,None
    for root in path.parents:
        if (root/INDEX).is_file():
            name=path.relative_to(root).as_posix()
            entry=load_index(root)['members'].get(name)
            if entry is not None:return path,root,entry
    raise FileNotFoundError(path)


def read_png(path):
    """Read actual raw bytes or the verified original archived member."""
    path,root,entry=_original_source(path)
    return path.read_bytes() if entry is None else archived_bytes(root,entry)


@dataclass(frozen=True)
class PngIdentity:
    sha256: str
    size: tuple[int, int]


def _png_size(pixels):
    import cv2
    import numpy as np
    if not pixels.startswith(b'\x89PNG\r\n\x1a\n'):return None
    try:image=cv2.imdecode(np.frombuffer(pixels,dtype=np.uint8),cv2.IMREAD_COLOR)
    except cv2.error:return None
    return None if image is None else (image.shape[1],image.shape[0])


def _archived_proof(root,entry,session):
    if session is None:return False,None
    container=archive_file(root,entry['archive'])
    if container.stat().st_size>MAX_EXPANDED:raise ValueError('Native image archive exceeds its bound')
    if sha(container.read_bytes())!=entry['archive_sha256']:
        raise ValueError('Native image archive hash changed')
    key=(str(container),entry['archive_sha256'],entry['sha256']+'.png',entry['bytes'])
    if key not in session.images:return False,None
    session.images.move_to_end(key)
    return True,session.images[key]


def verified_sha(path):
    """Encoded-byte identity only; preserve existing hash-only storage predicates."""
    path,root,entry=_original_source(path)
    if entry is None:return sha(path.read_bytes())
    found,_=_archived_proof(root,entry,_reads.get())
    return entry['sha256'] if found else sha(archived_bytes(root,entry))


def verified_png(path):
    """Rehash actual bytes; reuse a fully decoded, archive-bound identity.

    A cold cache hit still reads/hashes the actual index and complete container.
    Only decompression of bytes fully validated in this operation is reused.
    Raw files win even when a valid cold copy exists.
    """
    path,root,entry=_original_source(path);session=_reads.get()
    if entry is not None and session is not None:
        found,shape=_archived_proof(root,entry,session)
        if found:return None if shape is None else PngIdentity(entry['sha256'],shape)
    pixels=path.read_bytes() if entry is None else archived_bytes(root,entry)
    digest=sha(pixels)
    if session is not None and digest in session.shapes:
        session.shapes.move_to_end(digest)
        return PngIdentity(digest,session.shapes[digest])
    shape=_png_size(pixels)
    if shape is None:return None
    if session is not None:
        session.shapes[digest]=shape
        while len(session.shapes)>4096:session.shapes.popitem(last=False)
    return PngIdentity(digest,shape)


def candidates(root):
    """Old closed canonical captures; page semantics cannot grant storage rights.

    Independent raw needs remain. Verified untouched semantic proposals may
    use their shared original-byte reader; archiving grants no review approval.
    """
    from .capture_retention import archive_reference_keep,CLOSED_EVENTS
    from .native_evidence import frame_reference
    root=Path(root).resolve();protected=archive_reference_keep(root);selected=[]
    unprofitable=load_index(root).get('unprofitable',{})
    for base in (root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime'):
        runs=sorted((p for p in base.glob('*') if p.is_dir()),
                    key=lambda p:(p/'events.jsonl').stat().st_mtime if (p/'events.jsonl').is_file() else p.stat().st_mtime)
        for run in runs[:-5]:
            if workspace._linked(run):continue
            events=run/'events.jsonl'
            try:rows=[json.loads(line) for line in events.read_text(encoding='utf8').splitlines()]
            except (OSError,ValueError):continue
            if not any(isinstance(r,dict) and r.get('event') in CLOSED_EVENTS for r in rows):continue
            records=sorted(run.glob('frame-*.json'))
            # Unlike deletion, lossless archiving may include an unreferenced
            # first/tail diagnostic: its complete bytes and logical name remain.
              # Recent sessions and independent raw-required references stay raw.
            for record in records:
                png=record.with_suffix('.png')
                if png in protected or record in protected or not png.is_file():continue
                try:
                    record_body=plain(root,record.relative_to(root)).read_bytes();value=json.loads(record_body)
                    if not isinstance(value,dict):continue
                    body=plain(root,png.relative_to(root)).read_bytes()
                    if not 0<len(body)<=MAX_MEMBER or sha(body)!=value.get('image_sha256'):continue
                    if unprofitable.get(png.relative_to(root).as_posix())==sha(body):continue
                    reference,_=frame_reference(record)
                    if reference.json_sha256!=sha(record_body) or reference.png_sha256!=sha(body):continue
                except (OSError,ValueError,TypeError):continue
                selected.append(dict(path=png.relative_to(root).as_posix(),bytes=len(body),
                                     sha256=sha(body),record_sha256=sha(record_body)))
    return selected


def _publish(root,value):
    path=plain(root,INDEX);temporary=path.with_suffix('.tmp')
    body=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    workspace.require_space(root,len(body)+2_000_000)
    path.parent.mkdir(parents=True,exist_ok=True)
    with temporary.open('wb') as handle:
        handle.write(body);handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,path)


def retire(root,names):
    """Resume after publication, validating current references and both copies."""
    from .capture_retention import archive_reference_keep
    root=Path(root).resolve();index=load_index(root);freed=0
    # The caller serializes this storage batch with the controller lease.
    # Recompute the complete source/report reference set after publication;
    # additionally reread live state/model/review references before each unlink.
    protected=archive_reference_keep(root)
    for name in names:
        entry=index['members'][name];png=plain(root,name);record=png.with_suffix('.json')
        if not png.exists():continue
        from .review_storage import original_byte_documents
        # Validate only this original's proposal owners again at unlink. Other
        # proposals remain pins in this fresh state view, but must not become
        # false permanent pins for later members of the same batch.
        live=workspace.protected_evidence(root,
            original_byte_documents=original_byte_documents(root,image=png))
        if png in protected or record in protected or png in live or record in live:continue
        if sha(record.read_bytes())!=entry['record_sha256']:
            raise ValueError('Native image record changed before retirement')
        original=png.read_bytes()
        if original!=archived_bytes(root,entry):
            raise ValueError('Native image changed before retirement')
        # No metadata or business state is retired.
        png.unlink();freed+=len(original)
    return freed


def compact(root, *, max_bytes=MAX_BATCH):
    """One bounded batch; caller owns controller lease for the whole operation."""
    root=Path(root).resolve();before=workspace.size(root);index=load_index(root)
    index_before=plain(root,INDEX).stat().st_size if plain(root,INDEX).exists() else 0
    selected=[];total=0
    for entry in candidates(root):
        if total+entry['bytes']>min(max_bytes,MAX_EXPANDED):continue
        selected.append(entry);total+=entry['bytes']
        if len(selected)>=24:break
    if not selected:return dict(passed=True,files=0,freed=0,workspace_bytes=before)
    # The native IPC session owns process TEMP and may put it inside the project.
    # Stage only in memory, as cold rewrites already do. The existing selected
    # input/24-member bounds constrain this buffer, not total process RSS.
    scratch=io.BytesIO();seen=set()
    with tarfile.open(fileobj=scratch,mode='w:xz',preset=6) as handle:
        for entry in selected:
            name=entry['sha256']+'.png'
            body=plain(root,entry['path']).read_bytes()
            if sha(body)!=entry['sha256']:raise ValueError('Native image changed while archiving')
            if name in seen:continue
            seen.add(name);member=tarfile.TarInfo(name);member.size=len(body)
            handle.addfile(member,io.BytesIO(body))
    blob=scratch.getvalue();digest=sha(blob);archive=BLOBS+'/'+digest+'.tar.xz'
    if total-len(blob)<=1000*(len(selected)+1):
        # Remember measured no-gain encoded bytes, keeping every original.
        # Otherwise the same first group starves all later candidates.
        index.setdefault('unprofitable',{}).update({e['path']:e['sha256'] for e in selected})
        _publish(root,index)
        return dict(passed=True,files=0,freed=0,reason='no_lossless_gain')
    workspace.require_space(root,len(blob)+1_000_000+2_000_000)
    destination=plain(root,archive);destination.parent.mkdir(parents=True,exist_ok=True)
    allocated=0
    if not destination.exists():
        destination.write_bytes(blob);allocated=len(blob)
    for entry in selected:
        member=dict(entry);name=member.pop('path');member.update(archive=archive,archive_sha256=digest)
        if name in index['members'] and index['members'][name]!=member:
            raise ValueError('Native image archive identity already published')
        if archived_bytes(root,member)!=plain(root,name).read_bytes():raise ValueError('Archive readback differs')
        index['members'][name]=member
    _publish(root,index)
    retired=retire(root,[entry['path'] for entry in selected])
    after=workspace.size(root)
    freed=retired-allocated-(plain(root,INDEX).stat().st_size-index_before)
    return dict(passed=True,files=len(selected),raw_bytes=total,archive_bytes=len(blob),
                retired_bytes=retired,freed=freed,observed_workspace_delta=before-after,workspace_bytes=after,
                archive_sha256=digest,input_sent=False)
