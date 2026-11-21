"""Read pinned public reference source from checkout or bounded reference snapshot.

No runtime evidence, account state or game controller enters this cache. Import
tools extract archived source into one temporary directory, removed on return.
"""
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile


NAME='LixAssistantLimbusCompany'
MAX_SOURCE_BYTES=300_000_000


def git_hash(kind,body):
    return hashlib.sha1(kind.encode()+b' '+str(len(body)).encode()+b'\0'+body).hexdigest()


def verified_blob(row,body):
    canonical=body.replace(b'\r\n',b'\n') if row.get('windows_crlf') is True else body
    return (git_hash('blob',canonical)==row['sha1']
            and (not row.get('checkout_sha256')
                 or hashlib.sha256(body).hexdigest()==row['checkout_sha256']))


def source_tree(files):
    tree={};seen=set()
    for row in files:
        path=PurePosixPath(row['path'])
        if (path.is_absolute() or '..' in path.parts or '\\' in row['path']
                or ':' in row['path'] or not path.parts or path.as_posix()!=row['path']
                or any(part.rstrip('. ')!=part for part in path.parts)
                or row['mode'] not in ('100644','100755')):
            raise ValueError('Unsafe source snapshot member')
        if row['path'].casefold() in seen:raise ValueError('Duplicate Windows source path')
        seen.add(row['path'].casefold())
        branch=tree
        for part in path.parts[:-1]:
            branch=branch.setdefault(part,{})
            if not isinstance(branch,dict):raise ValueError('Source member path collision')
        if path.name in branch:raise ValueError('Duplicate source snapshot member')
        branch[path.name]=(row['mode'],row['sha1'])
    def digest(branch):
        entries=[]
        for name,value in branch.items():
            mode='40000' if isinstance(value,dict) else value[0]
            sha=digest(value) if mode=='40000' else value[1]
            entries.append((name,mode,sha))
        entries.sort(key=lambda row:row[0].encode()+ (b'/' if row[1]=='40000' else b''))
        body=b''.join(mode.encode()+b' '+name.encode()+b'\0'+bytes.fromhex(sha)
                      for name,mode,sha in entries)
        return git_hash('tree',body)
    return digest(tree)


def verify_snapshot(archive,manifest,revision):
    archive=Path(archive)
    if archive.is_symlink() or archive.stat().st_size>MAX_SOURCE_BYTES:
        raise ValueError('Invalid source snapshot archive')
    commit=bytes.fromhex(manifest['commit_object_hex'])
    if git_hash('commit',commit)!=revision or manifest.get('revision')!=revision:
        raise ValueError('Source snapshot commit differs from pin')
    expected=commit.splitlines()[0].decode().removeprefix('tree ')
    files=manifest['files']
    if source_tree(files)!=expected:raise ValueError('Source snapshot tree differs from commit')
    names=manifest.get('retained_paths',[row['path'] for row in files])
    lookup={row['path']:row for row in files}
    if len(names)!=len(set(names)) or any(name not in lookup for name in names):
        raise ValueError('Invalid retained source subset')
    retained=[lookup[name] for name in names]
    with archive.open('rb') as handle:sha=hashlib.file_digest(handle,'sha256').hexdigest()
    if sha!=manifest['archive_sha256']:raise ValueError('Source snapshot archive changed')
    with zipfile.ZipFile(archive) as source:
        members=source.infolist()
        if (len(members)!=len(retained) or len({m.filename for m in members})!=len(members)
                or {m.filename for m in members}!={r['path'] for r in retained}
                or sum(m.file_size for m in members)>MAX_SOURCE_BYTES):
            raise ValueError('Source snapshot member inventory differs')
        for row in retained:
            member=source.getinfo(row['path'])
            if member.file_size!=row['bytes'] or not 0<=member.file_size<=64_000_000:
                raise ValueError('Source snapshot expansion budget exceeded')
            if not verified_blob(row,source.read(member)):
                raise ValueError('Source snapshot blob differs from pinned tree')
    return retained


@contextmanager
def checkout(root,revision,*,required=()):
    base=Path(root)/'sources/upstream';directory=base/NAME
    if directory.is_dir():
        actual=subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'],text=True).strip()
        if actual!=revision:raise ValueError('Review changed upstream before importing')
        if any(not any(p.is_file() for p in directory.glob(pattern)) for pattern in required):
            raise ValueError('Required source dependency absent')
        yield directory
        return
    archive=base/(NAME+'.source.zip');metadata=base/(NAME+'.source.json')
    manifest=json.loads(metadata.read_text(encoding='utf8'))
    files=verify_snapshot(archive,manifest,revision)
    retained={row['path'] for row in files}
    for pattern in required:
        expected={row['path'] for row in manifest['files'] if PurePosixPath(row['path']).match(pattern)}
        if not expected or not expected<=retained:raise ValueError('Required source dependency absent from snapshot')
    with tempfile.TemporaryDirectory(prefix='maalimbus-public-source-') as work:
        target=Path(work)
        with zipfile.ZipFile(archive) as source:
            for row in files:
                path=target/row['path'];path.parent.mkdir(parents=True,exist_ok=True)
                body=source.read(row['path'])
                if not verified_blob(row,body):raise ValueError('Source changed before extraction')
                path.write_bytes(body)
        yield target


def with_source(root,revision,*,required=()):
    """Pass a verified source directory to an offline import tool."""
    def decorate(main):
        @wraps(main)
        def wrapped(*args,**kwargs):
            with checkout(root,revision,required=required) as upstream:return main(upstream,*args,**kwargs)
        return wrapped
    return decorate
