"""Read immutable archived build reports without losing their frame references.

Only closed build reports may use this optional storage tier. Runtime captures,
pending transactions, account configuration and human reviews remain in place.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

from . import workspace

INDEX = 'build/evidence-report-archive.json'
MAX_MEMBER_BYTES = 16_000_000
MAX_TOTAL_BYTES = 128_000_000
MAX_MEMBERS = 256


def _plain(root, relative, suffix):
    if not isinstance(relative, str):
        raise ValueError('Archived report path must be a direct build file')
    name = PurePosixPath(relative)
    if ('\\' in relative or name.is_absolute()
            or len(name.parts) != 2 or name.parts[0] != 'build'
            or name.parts[1] in ('', '.', '..') or name.suffix != suffix):
        raise ValueError('Archived report path must be a direct build file')
    path = root.joinpath(*name.parts)
    for parent in (path, *path.parents):
        if workspace._linked(parent):
            raise ValueError('Linked report archive path')
        if parent == root:
            break
    return path


def load_index(root):
    root = Path(root).resolve()
    index_path = _plain(root, INDEX, '.json')
    if not index_path.exists():
        return None
    if index_path.stat().st_size > 1_000_000:
        raise ValueError('Report archive index is oversized')
    body = index_path.read_bytes()
    value = json.loads(body)
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('kind') != 'evidence_report_archive'
            or not isinstance(value.get('members'), list)
            or not 1 <= len(value['members']) <= MAX_MEMBERS):
        raise ValueError('Unverified report archive index')
    archive = _plain(root, value.get('archive'), '.zip')
    if not isinstance(value.get('sha256'), str) or len(value['sha256']) != 64:
        raise ValueError('Report archive digest missing')
    names = set()
    total = 0
    for row in value['members']:
        if not isinstance(row, dict):
            raise ValueError('Invalid report archive member')
        _plain(root, row.get('path'), '.json')
        name = row['path']
        if name == INDEX or name in names:
            raise ValueError('Duplicate or recursive report archive member')
        names.add(name)
        if (type(row.get('bytes')) is not int or not 0 <= row['bytes'] <= MAX_MEMBER_BYTES
                or not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64):
            raise ValueError('Invalid report archive size or digest')
        total += row['bytes']
    if total > MAX_TOTAL_BYTES:
        raise ValueError('Report archive expanded size is oversized')
    return dict(value=value, archive=archive, index_sha256=hashlib.sha256(body).hexdigest())


def _verified_members(body, index):
    if hashlib.sha256(body).hexdigest() != index['sha256']:
        raise ValueError('Report archive bytes changed; preserve referenced captures')
    expected = {row['path']: row for row in index['members']}
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            infos = archive.infolist()
            if len(infos) != len(expected) or {info.filename for info in infos} != set(expected):
                raise ValueError('Report archive members changed or duplicated')
            for info in infos:
                row = expected[info.filename]
                if (info.is_dir() or info.flag_bits & 1
                        or stat.S_ISLNK(info.external_attr >> 16)
                        or info.file_size != row['bytes']):
                    raise ValueError('Report archive member type or size changed')
                content = archive.read(info)
                if len(content) != row['bytes'] or hashlib.sha256(content).hexdigest() != row['sha256']:
                    raise ValueError('Report archive member hash changed')
                json.loads(content)  # The archived representation stays the original JSON bytes.
                yield info.filename, content
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise ValueError('Report archive is unreadable; preserve referenced captures') from error


def references(root, parse, *, context=''):
    """Return the exact lexical references that the original reports protected.

    Missing/changed archives are not silently ignored during reclamation. Both
    index and ZIP bytes participate in the cache identity; every call rereads them.
    """
    root = Path(root).resolve()
    index = load_index(root)
    if index is None:
        return frozenset()
    if not index['archive'].is_file() or index['archive'].stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError('Report archive missing or oversized; preserve referenced captures')
    def collect(body):
        found = set()
        for _, content in _verified_members(body, index['value']):
            found.update(parse(content))
        return found
    return workspace.cached_references(index['archive'], root,
        'archived-report:' + index['index_sha256'] + ':' + context, collect)


def read_report_bytes(path, *, root):
    """Read a current raw report, otherwise a hash-verified immutable archive member."""
    root = Path(root).resolve()
    path = Path(path)
    relative = path.resolve().relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
    path = _plain(root, relative, '.json')
    if path.is_file():
        if path.stat().st_size > MAX_MEMBER_BYTES:
            raise ValueError('Report is oversized')
        return path.read_bytes()
    index = load_index(root)
    if index is None or relative not in {row['path'] for row in index['value']['members']}:
        raise FileNotFoundError(relative)
    if not index['archive'].is_file() or index['archive'].stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError('Report archive missing or oversized')
    result = None
    for name, content in _verified_members(index['archive'].read_bytes(), index['value']):
        if name == relative:
            result = content
    return result
