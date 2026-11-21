"""Increment an immutable closed-report archive without losing original bytes.

The caller explicitly selects sealed direct build reports with expected hashes.
Runtime captures, account state and review queues never move. The installed
version1 reader remains unchanged. Default CLI operation is a read-only plan.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from maalimbus import capture_retention, evidence_reports as reports, workspace
from restore_report_snapshot import reconstruct


def digest(body):
    return hashlib.sha256(body).hexdigest()


def encoded(value):
    return json.dumps(value, indent=2, ensure_ascii=True).encode('utf8')


def operation_bytes(value):
    return encoded(dict(record=value, sha256=digest(encoded(value))))


def write(root, path, body):
    workspace.reserve_output(path, len(body) + 8192, application_root=root)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def recipe(body, path, members):
    rows = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for info in archive.infolist():
            row = {key: getattr(info, key) for key in (
                'filename', 'date_time', 'compress_type', 'create_system',
                'create_version', 'extract_version', 'reserved', 'flag_bits',
                'volume', 'internal_attr', 'external_attr')}
            row.update(extra=base64.b64encode(info.extra).decode(),
                       comment=base64.b64encode(info.comment).decode(),
                       sha256=digest(members[info.filename]))
            rows.append(row)
        value = dict(version=1, kind='report_snapshot_recipe', path=path,
                     bytes=len(body), sha256=digest(body),
                     comment=base64.b64encode(archive.comment).decode(), members=rows)
    if reconstruct(value, members) != body:
        raise ValueError('Old archive cannot be reconstructed byte-exactly')
    return value


def select(root, selection):
    if (not isinstance(selection, dict) or selection.get('version') != 1
            or selection.get('kind') != 'closed_report_selection'
            or selection.get('sealed') is not True
            or not isinstance(selection.get('reports'), list)
            or not 1 <= len(selection['reports']) <= reports.MAX_MEMBERS):
        raise ValueError('Explicit sealed report selection required')
    rows = selection['reports']
    names = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid report selection row')
        path = reports._plain(root, row.get('path'), '.json')
        if (path.name in ('evidence-report-archive.json', 'evidence-report-roles.json')
                or path.name.endswith('-recipe.json') or 'rollover' in path.name
                or path.name.endswith('-cases.json') or row['path'] in names
                or type(row.get('bytes')) is not int
                or not 0 <= row['bytes'] <= reports.MAX_MEMBER_BYTES
                or not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64):
            raise ValueError('Duplicate, administrative or invalid report selection')
        names.add(row['path'])
    return rows


def prepare(root, selection, archive_name, recipe_name):
    root = Path(root).resolve()
    rows = select(root, selection)
    target = reports._plain(root, archive_name, '.zip')
    snapshot = reports._plain(root, recipe_name, '.json')
    old = reports.load_index(root)
    if old is None or old['archive'] == target or snapshot.name in {
            'evidence-report-archive.json', 'evidence-report-roles.json'}:
        raise ValueError('Distinct existing archive and snapshot path required')
    if not old['archive'].is_file() or old['archive'].stat().st_size > reports.MAX_TOTAL_BYTES:
        raise ValueError('Old archive missing or oversized')
    old_body = old['archive'].read_bytes()
    members = dict(reports._verified_members(old_body, old['value']))
    old_recipe = recipe(old_body, old['value']['archive'], members)
    recipe_body = encoded(old_recipe)
    if len(recipe_body) > 1_000_000:
        raise ValueError('Old-container recipe is oversized')
    if snapshot.exists() and snapshot.stat().st_size > 1_000_000:
        raise ValueError('Existing snapshot recipe is oversized')
    if snapshot.exists() and snapshot.read_bytes() != recipe_body:
        raise ValueError('Existing old-container recipe differs')
    for row in rows:
        if row['path'] in members or root / row['path'] == snapshot:
            raise ValueError('Selected report already archived or is a control file')
        path = root / row['path']
        if path.stat().st_size != row['bytes']:
            raise ValueError('Selected sealed report size changed')
        body = path.read_bytes()
        if len(body) != row['bytes'] or digest(body) != row['sha256']:
            raise ValueError('Selected sealed report changed')
        if not isinstance(json.loads(body), dict):
            raise ValueError('Only closed object reports can be archived')
        members[row['path']] = body
    if len(members) > reports.MAX_MEMBERS or sum(map(len, members.values())) > reports.MAX_TOTAL_BYTES:
        raise ValueError('Archive exceeds existing reader bounds')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body, compress_type=info.compress_type, compresslevel=9)
    new_body = buffer.getvalue()
    index = dict(version=1, kind='evidence_report_archive', archive=archive_name,
                 sha256=digest(new_body), members=[dict(path=name, bytes=len(body), sha256=digest(body))
                                                  for name, body in sorted(members.items())])
    assert dict(reports._verified_members(new_body, index)) == members
    operation = dict(version=1, kind='closed_report_rollover', phase='prepared',
                     selection_sha256=digest(encoded(selection)), selection=selection,
                     old_index_sha256=old['index_sha256'], old_index=old['value'],
                     new_index=index, recipe_path=recipe_name, old_recipe=old_recipe)
    operation = json.loads(encoded(operation))  # Stable tuples/lists across restart.
    required = len(new_body) + len(encoded(index)) + len(recipe_body) + 2 * len(operation_bytes(operation)) + 65536
    if target.exists():
        if target.stat().st_size > reports.MAX_TOTAL_BYTES or target.read_bytes() != new_body:
            raise ValueError('Existing candidate archive differs')
    workspace.require_space(root, required, budget=workspace.BUDGET_BYTES)
    return operation, new_body


def rollover(root, selection, archive_name, recipe_name, operation_name, *, fault=None):
    root = Path(root).resolve()
    operation_path = reports._plain(root, operation_name, '.json')
    if operation_path.name in ('evidence-report-archive.json', 'evidence-report-roles.json', recipe_name.split('/')[-1]):
        raise ValueError('Operation path collides with storage controls')
    fault = fault or (lambda phase: None)
    rows = select(root, selection)
    if operation_path.exists():
        if operation_path.stat().st_size > 1_000_000:
            raise ValueError('Storage operation is oversized')
        envelope = json.loads(operation_path.read_bytes())
        operation = envelope['record']
        if envelope.get('sha256') != digest(encoded(operation)):
            raise ValueError('Storage operation checksum differs')
        if (operation.get('version') != 1 or operation.get('kind') != 'closed_report_rollover'
                or operation.get('selection_sha256') != digest(encoded(selection))
                or operation.get('selection') != selection
                or operation['new_index']['archive'] != archive_name
                or operation['recipe_path'] != recipe_name):
            raise ValueError('Storage operation differs; preserve all files')
    else:
        operation, _ = prepare(root, selection, archive_name, recipe_name)
        write(root, operation_path, operation_bytes(operation))
    target = reports._plain(root, archive_name, '.zip')
    snapshot = reports._plain(root, recipe_name, '.json')
    index_path = root / reports.INDEX
    before_refs = capture_retention._reference_keep(root)
    current_body = index_path.read_bytes()
    new_index_body = encoded(operation['new_index'])
    if current_body != new_index_body:
        if digest(current_body) != operation['old_index_sha256']:
            raise ValueError('Active archive changed; no retirement permitted')
        refreshed, candidate = prepare(root, selection, archive_name, recipe_name)
        if refreshed != {**operation, 'phase': 'prepared'}:
            raise ValueError('Prepared storage inputs changed')
        write(root, target, candidate)
        write(root, snapshot, encoded(operation['old_recipe']))
        fault('before_index')
        write(root, index_path, new_index_body)
        fault('after_index')
    active = reports.load_index(root)
    if active is None or active['value'] != operation['new_index']:
        raise ValueError('New archive is not active')
    members = dict(reports._verified_members(target.read_bytes(), active['value']))
    # A missing recipe cannot authorize deleting either raw reports or the old ZIP.
    if snapshot.read_bytes() != encoded(operation['old_recipe']):
        raise ValueError('Old-container reconstruction recipe changed')
    old_bytes = reconstruct(operation['old_recipe'], members)
    if (digest(old_bytes) != operation['old_index']['sha256']
            or capture_retention._reference_keep(root) != before_refs):
        raise ValueError('Archive reference set or historical bytes changed')
    # Validate the entire surviving raw selection before the first retirement.
    for row in rows:
        path = reports._plain(root, row['path'], '.json')
        if path.exists() and (path.stat().st_size != row['bytes']
                              or digest(path.read_bytes()) != row['sha256']):
            raise ValueError('Raw report changed; preserve changed file')
    removed = []
    for row in rows:
        if row['path'] not in members or digest(members[row['path']]) != row['sha256']:
            raise ValueError('Selected report absent from verified archive')
        path = reports._plain(root, row['path'], '.json')
        if path.exists():
            if len(path.read_bytes()) != row['bytes'] or digest(path.read_bytes()) != row['sha256']:
                raise ValueError('Raw report changed; preserve changed file')
            if index_path.read_bytes() != new_index_body:
                raise ValueError('Active archive changed during retirement')
            path.unlink()
            removed.append(row['path'])
            fault('after_report')
    if capture_retention._reference_keep(root) != before_refs:
        raise ValueError('Retired report references differ; preserve old container')
    old_path = reports._plain(root, operation['old_index']['archive'], '.zip')
    if old_path.exists():
        if old_path.read_bytes() != old_bytes:
            raise ValueError('Old container changed; preserve both archives')
        if index_path.read_bytes() != new_index_body:
            raise ValueError('Active archive changed before old-container retirement')
        old_path.unlink()
    fault('after_old_archive')
    operation['phase'] = 'completed'
    write(root, operation_path, operation_bytes(operation))
    return dict(passed=True, archived_reports=len(members), selected_reports=len(rows),
                raw_reports_removed_now=len(removed), old_container_reconstructible=True,
                references_unchanged=True, game_inputs=0, workspace_bytes=workspace.size(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.selection.stat().st_size > 1_000_000:
        parser.error('Selection is oversized')
    selection = json.loads(args.selection.read_bytes())
    from maalimbus.controller_lease import ControllerLease
    from maalimbus.update_install import closed_app
    lease = ControllerLease.acquire(ROOT / 'build/controller.lock')
    try:
        closed_app(ROOT / 'dist/MaaLimbus')
        if args.apply:
            result = rollover(ROOT, selection, args.archive, args.recipe, args.operation)
        else:
            operation, body = prepare(ROOT, selection, args.archive, args.recipe)
            result = dict(plan_only=True, selected_reports=len(selection['reports']),
                          archive_reports=len(operation['new_index']['members']), archive_bytes=len(body),
                          raw_report_bytes=sum(r['bytes'] for r in selection['reports']), game_inputs=0)
    finally:
        lease.close()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
