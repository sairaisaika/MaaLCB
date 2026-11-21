"""Move only sealed historical image containers into the opt-in local vault."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from . import native_image_archive as archive, workspace
from .runtime_paths import data_directory
from .storage import read_json, write_json


class VaultUnavailable(PermissionError):
    """The optional external destination is currently unwritable."""


def enable(root, budget=None):
    """Opt in or explicitly change the local ceiling under the controller lease."""
    root = Path(root).resolve()
    if budget is not None and (type(budget) is not int or not 0 < budget <= archive.MAX_VAULT_BYTES):
        raise ValueError('Local image vault budget is outside the supported range')
    policy = archive.vault_policy(root)
    if policy is None:
        vault = archive.plain(root.parent, root.name + '-cold-archive')
        if vault.exists() and any(vault.iterdir()):
            raise ValueError('Local image vault directory already contains files')
        if budget is None:
            budget = archive.DEFAULT_VAULT_BYTES
    else:
        vault, current = policy
        if budget is None or budget == current:
            return
        if vault.exists() and workspace.size(vault) > budget:
            raise ValueError('Local image vault already exceeds the requested budget')
    workspace.require_space(root, 4096)
    write_json(root / archive.VAULT_POLICY, dict(version=1, budget_bytes=budget))


def _date(record):
    value = datetime.fromisoformat(record['utc'])
    if value.tzinfo is None:
        raise ValueError('Native capture time requires a timezone')
    return value


def _active_boundary(root):
    configs = {data_directory(app).resolve() for app in (root, root / 'dist/MaaLimbus')}
    supported = {root / 'config', root / 'dist/MaaLimbus/config'}
    if configs - supported:
        raise ValueError('Local image vault requires a known protected configuration root')
    scopes, times = set(), []
    for config in configs:
        path = archive.plain(root, config / 'user-run-ledger.json')
        if not path.is_file():
            continue
        active = read_json(path).get('active')
        if active is not None:
            entry = active.get('entry') or {}
            if not entry.get('before'):
                raise ValueError('Active entry has no original proof for archive separation')
            before = archive.plain(root, entry['before'])
            body = before.read_bytes()
            if archive.sha(body) != entry['before_sha256']:
                raise ValueError('Active entry proof changed before vault selection')
            scopes.add(active['id'])
            times.append(_date(json.loads(body)))
    return scopes, min(times) if times else None


def _closed_scope(run):
    from .capture_retention import CLOSED_EVENTS

    journal = archive.plain(run, 'events.jsonl')
    if journal.stat().st_size > 16_000_000:
        return False, frozenset(), None
    body = journal.read_bytes()
    rows = [json.loads(line) for line in body.splitlines() if line.strip()]
    end = next((i for i in range(len(rows) - 1, -1, -1)
                if rows[i]['event'] in CLOSED_EVENTS), None)
    closed = end is not None and not any(row.get('input_sent') is True for row in rows[end + 1:])
    scopes = frozenset(row[key] for row in rows for key in ('run_scope', 'scope', 'episode')
                       if isinstance(row.get(key), str))
    return closed, scopes, archive.sha(body)


def _raw_duplicate(image, entry):
    """A retained workspace copy must still match the archived original."""
    if workspace._linked(image):
        raise ValueError('Linked raw copy is not an indexed original')
    if not image.exists():
        return False
    if (not image.is_file() or image.stat().st_size != entry['bytes']
            or _digest(image) != entry['sha256']):
        raise ValueError('Raw copy differs from its indexed original')
    return True


def _eligible(root, index, boundary, protected):
    scopes, cutoff = boundary
    groups = defaultdict(list)
    for name, entry in index['members'].items():
        groups[entry['archive']].append((name, entry))
    closed = {}
    for name, entries in groups.items():
        blob = archive.plain(root, name)
        if (not blob.is_file() or not re.fullmatch(r'[0-9a-f]{64}\.tar\.xz', blob.name)
                or any(entry['archive_sha256'] != blob.name[:-7] for _, entry in entries)):
            continue
        try:
            journal_hashes = {}
            raw_copies = set()
            for logical_name, entry in entries:
                image = archive.plain(root, logical_name)
                record = image.with_suffix('.json')
                if {image, record} & protected:
                    break
                if image.parent not in closed:
                    closed[image.parent] = _closed_scope(image.parent)
                terminal, recorder_scopes, journal_hash = closed[image.parent]
                body = record.read_bytes()
                if not terminal or scopes & recorder_scopes or archive.sha(body) != entry['record_sha256']:
                    break
                if cutoff is not None and _date(json.loads(body)) >= cutoff:
                    break
                if _raw_duplicate(image, entry):
                    raw_copies.add(image)
                journal_hashes[image.parent / 'events.jsonl'] = journal_hash
            else:
                yield blob, entries, journal_hashes, raw_copies
        except (OSError, KeyError, ValueError, TypeError, AttributeError):
            continue


def _digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _append(journal, payload):
    body = json.dumps(payload, separators=(',', ':')).encode() + b'\n'
    try:
        stream = journal.open('ab')
    except PermissionError as error:
        raise VaultUnavailable('Local vault transfer journal is unwritable') from error
    with stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def offload(root, *, target_free, max_containers=1):
    """Move complete immutable blobs under the sole controller lease."""
    if type(target_free) is not int or not 0 <= target_free <= workspace.BUDGET_BYTES:
        raise ValueError('Local image vault target is outside the workspace bound')
    if type(max_containers) is not int or not 1 <= max_containers <= 64:
        raise ValueError('Local image vault batch must be bounded')
    root = Path(root).resolve()
    policy = archive.vault_policy(root)
    before = workspace.size(root)
    if policy is None or before + target_free <= workspace.BUDGET_BYTES:
        return dict(containers=0, freed_bytes=0)
    from .cold_retention import recover

    recover(root)
    vault, budget = policy
    try:
        vault.mkdir(exist_ok=True)
    except PermissionError as error:
        raise VaultUnavailable('Local vault directory is unwritable') from error
    journal = archive.plain(vault, 'transfers.jsonl')
    boundary = _active_boundary(root)
    protected = workspace.protected_evidence(root)
    index = archive.load_index(root)
    moved = 0
    preserved_raw = 0
    with archive.verified_reads():
        for blob, entries, journal_hashes, raw_copies in _eligible(root, index, boundary, protected):
            if moved >= max_containers or workspace.size(root) + target_free <= workspace.BUDGET_BYTES:
                break
            destination = archive.plain(vault, blob.name)
            size = blob.stat().st_size
            if destination.exists() or workspace.size(vault) + size + 4096 > budget:
                continue
            digest = blob.name[:-7]
            for _, entry in entries:
                archive.archived_bytes(root, entry)
            current_records = [(archive.plain(root, name), entry) for name, entry in entries]
            if (any(_raw_duplicate(image, entry) != (image in raw_copies)
                    or _digest(image.with_suffix('.json')) != entry['record_sha256']
                    for image, entry in current_records)
                    or any(_digest(path) != expected for path, expected in journal_hashes.items())):
                raise ValueError('Closed image vault evidence changed before transfer')
            if (_active_boundary(root) != boundary or workspace.protected_evidence(root) != protected
                    or archive.load_index(root) != index or _digest(blob) != digest):
                raise ValueError('Local image vault selection changed before transfer')
            row = dict(archive=blob.relative_to(root).as_posix(), sha256=digest,
                       bytes=size, logical_members=len(entries), raw_copies_retained=len(raw_copies))
            workspace.require_space(vault, size + 4096, budget=budget)
            _append(journal, dict(stage='intent', **row))
            try:
                os.rename(blob, destination)
            except PermissionError as error:
                raise VaultUnavailable('Local vault container could not be moved') from error
            try:
                if archive.archive_file(root, row['archive']) != destination or _digest(destination) != digest:
                    raise ValueError('Local image vault readback differs')
                if any(_raw_duplicate(image, entry) != (image in raw_copies)
                       for image, entry in current_records):
                    raise ValueError('Raw copy changed during vault transfer')
                _append(journal, dict(stage='committed', **row))
            except BaseException:
                os.rename(destination, blob)
                raise
            moved += 1
            preserved_raw += len(raw_copies)
    return dict(containers=moved, freed_bytes=before - workspace.size(root),
                raw_copies_retained=preserved_raw,
                vault_bytes=workspace.size(vault), vault_budget_bytes=budget, input_sent=False)


def offload_framework_logs(root, *, target_free):
    """Move sealed Maa debug text before a run, under the existing controller lease."""
    if type(target_free) is not int or not 0 <= target_free <= workspace.BUDGET_BYTES:
        raise ValueError('Local framework log target is outside the workspace bound')
    root = Path(root).resolve()
    policy = archive.vault_policy(root)
    free = workspace.BUDGET_BYTES - workspace.size(root)
    result = dict(framework_logs=0, framework_log_bytes=0)
    if policy is None or free >= target_free:
        return result
    vault, budget = policy
    boundary = _active_boundary(root)
    active, cutoff = boundary
    protected = workspace.protected_evidence(root)
    candidates = []
    for base in ('evidence/runtime','dist/MaaLimbus/evidence/runtime'):
        for path in archive.plain(root,base).glob('*/debug/debug/maafw.log'):
            if path in protected or workspace._linked(path):
                continue
            try:
                source = archive.plain(root,path.relative_to(root))
                updated = datetime.fromtimestamp(source.stat().st_mtime,timezone.utc)
                closed,scopes,journal_sha = _closed_scope(source.parents[2])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if closed and scopes and not active & scopes and (cutoff is None or updated < cutoff):
                candidates.append((updated,source,scopes,journal_sha))

    if not candidates:
        return result
    journal = archive.plain(vault,'framework-log-transfers.jsonl')
    vault.mkdir(exist_ok=True)
    for _,source,scopes,journal_sha in sorted(candidates)[:32]:
        if free >= target_free:
            break
        name = source.relative_to(root)
        destination = archive.plain(vault,Path('framework-logs')/name)
        size = source.stat().st_size
        if destination.exists() or workspace.size(vault)+size+4096 > budget:
            continue
        body_hash = _digest(source)
        if (_active_boundary(root) != boundary or source in workspace.protected_evidence(root)
                or _closed_scope(source.parents[2]) != (True,scopes,journal_sha)):
            raise ValueError('Historical framework log ownership changed before transfer')
        destination.parent.mkdir(parents=True,exist_ok=True)
        row = dict(path=name.as_posix(),sha256=body_hash,bytes=size,journal_sha256=journal_sha)
        _append(journal,dict(stage='intent',**row))
        os.rename(source,destination)
        try:
            if _digest(destination) != body_hash:
                raise ValueError('Historical framework log readback differs')
            _append(journal,dict(stage='committed',**row))
        except BaseException:
            os.rename(destination,source)
            raise
        result['framework_logs'] += 1
        result['framework_log_bytes'] += size
        free += size
    return result
