"""Cold images retain exact FrameRef identity and fail closed on damaged storage."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from maalimbus import native_image_archive as archive
from maalimbus.native_evidence import frame_reference
from test_observation_frame import capture


def batch(tmp_path,monkeypatch):
    path,raw=capture(tmp_path/'evidence/runtime/closed')
    original=path.with_suffix('.png').read_bytes()
    # Include repeated inert padding in a valid PNG's trailing bytes: compressible
    # encoded bytes, not a re-encoded image or a changed capture identity.
    original+=b'padding'*10000
    path.with_suffix('.png').write_bytes(original)
    raw['image_sha256']=hashlib.sha256(original).hexdigest();path.write_text(json.dumps(raw))
    entry=dict(path=path.with_suffix('.png').relative_to(tmp_path).as_posix(),bytes=len(original),
               sha256=raw['image_sha256'],record_sha256=archive.sha(path.read_bytes()))
    monkeypatch.setattr(archive,'candidates',lambda root:[entry])
    return path,entry,original


def test_readback_preserves_original_capture_time_json_hash_and_pixels(tmp_path,monkeypatch):
    path,entry,original=batch(tmp_path,monkeypatch);before=frame_reference(path)[0]
    result=archive.compact(tmp_path)
    assert result['files']==1 and result['freed']>0
    assert path.exists() and not path.with_suffix('.png').exists()
    assert archive.read_png(path.with_suffix('.png'))==original
    assert frame_reference(path)[0]==before
    assert archive.verify_all(tmp_path)==dict(passed=True,images=1,containers=1,input_sent=False)


def test_publication_failure_keeps_every_original(tmp_path,monkeypatch):
    path,entry,original=batch(tmp_path,monkeypatch)
    def crash(*args):raise OSError('interrupted before index')
    monkeypatch.setattr(archive,'_publish',crash)
    with pytest.raises(OSError):archive.compact(tmp_path)
    assert path.with_suffix('.png').read_bytes()==original
    assert not (tmp_path/archive.INDEX).exists()


def test_published_index_survives_retirement_interruption_and_resumes(tmp_path,monkeypatch):
    path,entry,original=batch(tmp_path,monkeypatch);retire=archive.retire
    monkeypatch.setattr(archive,'retire',lambda *a:0)
    archive.compact(tmp_path)
    assert path.with_suffix('.png').exists()
    assert retire(tmp_path,[entry['path']])==len(original)
    assert retire(tmp_path,[entry['path']])==0
    assert archive.read_png(path.with_suffix('.png'))==original


def test_new_reference_after_compression_keeps_raw(tmp_path,monkeypatch):
    from maalimbus import capture_retention
    path,entry,original=batch(tmp_path,monkeypatch)
    monkeypatch.setattr(capture_retention,'_reference_keep',lambda root:{path})
    assert archive.compact(tmp_path)['retired_bytes']==0
    assert path.with_suffix('.png').read_bytes()==original


def test_space_refusal_is_before_publication_or_retirement(tmp_path,monkeypatch):
    path,entry,original=batch(tmp_path,monkeypatch)
    def refuse(*a,**kw):raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(archive.workspace,'require_space',refuse)
    with pytest.raises(ValueError,match='budget'):archive.compact(tmp_path)
    assert path.with_suffix('.png').read_bytes()==original
    assert not (tmp_path/archive.INDEX).exists()


@pytest.mark.parametrize('fault',['archive','raw','record','index'])
def test_changed_bytes_are_not_hidden_by_another_copy(tmp_path,monkeypatch,fault):
    path,entry,original=batch(tmp_path,monkeypatch);archive.compact(tmp_path)
    index=archive.load_index(tmp_path);member=index['members'][entry['path']]
    if fault=='archive':(tmp_path/member['archive']).write_bytes(b'changed')
    elif fault=='raw':path.with_suffix('.png').write_bytes(b'changed')
    elif fault=='record':
        value=json.loads(path.read_bytes());value['image_sha256']='0'*64;path.write_text(json.dumps(value))
    else:(tmp_path/archive.INDEX).write_text('{broken')
    with pytest.raises((ValueError,OSError)):frame_reference(path)


@pytest.mark.parametrize('name',['../escape.png','/outside.png','evidence/runtime/x/../../escape.png'])
def test_unsafe_index_never_reads_outside_workspace(tmp_path,name):
    path=tmp_path/archive.INDEX;path.parent.mkdir();path.write_text(json.dumps(dict(version=1,members={name:{}})))
    with pytest.raises(ValueError):archive.load_index(tmp_path)


def test_link_or_duplicate_tar_member_is_rejected(tmp_path):
    blob=io.BytesIO();body=b'image';name=archive.sha(body)+'.png'
    with tarfile.open(fileobj=blob,mode='w:xz') as handle:
        for _ in range(2):
            member=tarfile.TarInfo(name);member.size=len(body);handle.addfile(member,io.BytesIO(body))
    path=tmp_path/archive.BLOBS/'duplicate.tar.xz';path.parent.mkdir(parents=True);path.write_bytes(blob.getvalue())
    entry=dict(archive=path.relative_to(tmp_path).as_posix(),archive_sha256=archive.sha(blob.getvalue()),
               sha256=archive.sha(body),bytes=len(body))
    with pytest.raises(ValueError,match='Unsafe'):archive.archived_bytes(tmp_path,entry)


def test_closed_first_tail_bytes_can_archive_but_recent_and_strong_pins_stay_raw(tmp_path):
    import os
    paths=[]
    for n in range(7):
        path,_=capture(tmp_path/f'evidence/runtime/run-{n}')
        events=path.parent/'events.jsonl'
        events.write_text(json.dumps(dict(event='mirror_loop_stopped'))+'\n')
        os.utime(events,(n+100,n+100));paths.append(path)
    config=tmp_path/'config';config.mkdir()
    (config/'pending.json').write_text(json.dumps(dict(pending=str(paths[0]))))
    eligible=archive.candidates(tmp_path)
    assert [e['path'] for e in eligible]==[paths[1].with_suffix('.png').relative_to(tmp_path).as_posix()]
    assert all(p.with_suffix('.png').exists() for p in paths)


@pytest.mark.parametrize('restriction', [None, 'unclosed', 'active', 'installed_review', 'vault_full', 'not_enabled'])
def test_optional_vault_only_moves_verified_closed_historical_originals(tmp_path, monkeypatch, restriction):
    from maalimbus import native_cold_vault, workspace

    root = tmp_path / 'project'
    path, entry, original = batch(root, monkeypatch)
    rows = [dict(event='mirror_loop_start', run_scope='old')]
    if restriction != 'unclosed':
        rows.append(dict(event='mirror_loop_stopped'))
    (path.parent / 'events.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf8')
    archive.compact(root)
    index_path = root / archive.INDEX
    index_bytes = index_path.read_bytes()
    record_bytes = path.read_bytes()
    blob = root / archive.load_index(root)['members'][entry['path']]['archive']
    if restriction == 'active':
        config = root / 'config'
        config.mkdir()
        ledger = dict(active=dict(id='old', entry=dict(before=str(path), before_sha256=archive.sha(record_bytes))))
        (config / 'user-run-ledger.json').write_text(json.dumps(ledger), encoding='utf8')
    if restriction == 'installed_review':
        review = root / 'dist/MaaLimbus/build/learning-review/frames/example'
        review.mkdir(parents=True)
        (review / 'proposal.json').write_text(json.dumps(dict(native_record=str(path))), encoding='utf8')
    if restriction != 'not_enabled':
        native_cold_vault.enable(root, budget=100 if restriction == 'vault_full' else archive.MAX_VAULT_BYTES)
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root) + 100)
    result = native_cold_vault.offload(root, target_free=200)
    assert result['containers'] == int(restriction is None)
    assert path.read_bytes() == record_bytes and index_path.read_bytes() == index_bytes
    assert blob.is_file() == (restriction is not None)
    assert archive.read_png(path.with_suffix('.png')) == original
    assert archive.verify_all(root)['images'] == 1
    if restriction is None:
        assert result['vault_bytes'] <= result['vault_budget_bytes']
        destination = archive.archive_file(root, blob.relative_to(root).as_posix())
        destination.write_bytes(b'tampered archive')
        with pytest.raises(ValueError, match='hash changed'):
            archive.read_png(path.with_suffix('.png'))


def test_preflight_archives_only_closed_nonactive_native_logs(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    import os
    from maalimbus import native_cold_vault,workspace

    root=tmp_path/'project'
    def log(name,scope,closed=True):
        run=root/'evidence/runtime'/name
        path=run/'debug/debug/maafw.log'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'framework diagnostics\r\n'*400)
        os.utime(path,(1000,1000))
        events=[dict(event='mirror_loop_start',run_scope=scope)]
        if closed:
            events.append(dict(event='mirror_loop_stopped'))
        (run/'events.jsonl').write_text('\n'.join(map(json.dumps,events)),encoding='utf-8')
        return path

    historical=log('closed','old')
    active=log('same-scope','current')
    running=log('no-terminal','another',closed=False)
    original=historical.read_bytes()
    journal=historical.parents[2]/'events.jsonl'
    journal_bytes=journal.read_bytes()
    native_cold_vault.enable(root)
    monkeypatch.setattr(native_cold_vault,'_active_boundary',lambda root:({'current'},datetime.fromtimestamp(2000,timezone.utc)))
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(root)+100)
    result=native_cold_vault.offload_framework_logs(root,target_free=200)
    vault,_=archive.vault_policy(root)
    assert result==dict(framework_logs=1,framework_log_bytes=len(original))
    assert not historical.exists() and active.exists() and running.exists()
    assert (vault/'framework-logs'/historical.relative_to(root)).read_bytes()==original
    assert journal.read_bytes()==journal_bytes
    transfers=[json.loads(line) for line in (vault/'framework-log-transfers.jsonl').read_text().splitlines()]
    assert [row['stage'] for row in transfers]==['intent','committed']
    assert transfers[-1]['sha256']==hashlib.sha256(original).hexdigest()
    assert native_cold_vault.offload_framework_logs(root,target_free=200)['framework_logs']==0


@pytest.mark.parametrize('raw_state', ['identical', 'different', 'changes_during_transfer'])
def test_vault_move_preserves_a_retained_raw_copy(tmp_path, monkeypatch, raw_state):
    from maalimbus import native_cold_vault, workspace

    root = tmp_path / 'project'
    path, entry, original = batch(root, monkeypatch)
    (path.parent / 'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped')), encoding='utf8')
    archive.compact(root)
    index_path = root / archive.INDEX
    index_bytes = index_path.read_bytes()
    mapping = archive.load_index(root)['members'][entry['path']]
    local = root / mapping['archive']
    png = path.with_suffix('.png')
    altered = original[:-1] + b'!'
    png.write_bytes(altered if raw_state == 'different' else original)
    native_cold_vault.enable(root)
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root) + 100)
    if raw_state == 'changes_during_transfer':
        rename = native_cold_vault.os.rename

        def mutate_after_move(src, dst):
            rename(src, dst)
            if src == local:
                png.write_bytes(altered)

        monkeypatch.setattr(native_cold_vault.os, 'rename', mutate_after_move)
        with pytest.raises(ValueError, match='Raw copy differs'):
            native_cold_vault.offload(root, target_free=200)
    else:
        result = native_cold_vault.offload(root, target_free=200)
        assert result['containers'] == result['raw_copies_retained'] == int(raw_state == 'identical')
    assert local.is_file() == (raw_state != 'identical')
    assert index_path.read_bytes() == index_bytes
    assert png.read_bytes() == (original if raw_state == 'identical' else altered)
    assert archive.archived_bytes(root, mapping) == original


def test_vault_budget_changes_only_when_explicit_and_never_below_existing_usage(tmp_path):
    from maalimbus import native_cold_vault, workspace

    root = tmp_path / 'project'
    root.mkdir()
    project_limit = workspace.BUDGET_BYTES
    native_cold_vault.enable(root)
    vault, budget = archive.vault_policy(root)
    assert budget == 512_000_000
    vault.mkdir()
    preserved = vault / 'existing'
    preserved.write_bytes(b'existing local data')
    native_cold_vault.enable(root, budget=768_000_000)
    marker = root / archive.VAULT_POLICY
    changed = marker.read_bytes()
    native_cold_vault.enable(root)
    assert archive.vault_policy(root) == (vault, 768_000_000)
    with pytest.raises(ValueError, match='already exceeds'):
        native_cold_vault.enable(root, budget=1)
    with pytest.raises(ValueError, match='outside the supported range'):
        native_cold_vault.enable(root, budget=768_000_001)
    assert marker.read_bytes() == changed
    assert preserved.read_bytes() == b'existing local data'
    assert workspace.BUDGET_BYTES == project_limit


def test_runtime_pressure_uses_opt_in_vault_and_invalidates_the_unsent_plan(tmp_path, monkeypatch):
    from maalimbus import capture_retention, native_cold_vault, workspace

    root = tmp_path / 'project'
    path, _, original = batch(root, monkeypatch)
    (path.parent / 'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped')), encoding='utf8')
    archive.compact(root)
    native_cold_vault.enable(root)
    current = root / 'evidence/runtime/current'
    current.mkdir()
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root) + 100)
    result = capture_retention.reserve(current, 200, application_root=root)
    assert result['sufficient'] and result['storage_maintenance']
    assert result['vault_containers'] == 1 and result['vault_project_bytes_freed'] > 0
    assert archive.read_png(path.with_suffix('.png')) == original


def test_unwritable_vault_uses_existing_local_retention_without_moving_originals(tmp_path, monkeypatch):
    from maalimbus import capture_retention, native_cold_vault, workspace

    root = tmp_path / 'project'
    path, entry, original = batch(root, monkeypatch)
    (path.parent / 'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped')), encoding='utf8')
    archive.compact(root)
    blob = root / archive.load_index(root)['members'][entry['path']]['archive']
    native_cold_vault.enable(root)
    current = root / 'evidence/runtime/current'
    current.mkdir()
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root) + 100)
    original_open = Path.open

    def deny_append(path, mode='r', *args, **kwargs):
        if path.name == 'transfers.jsonl' and mode == 'ab':
            raise PermissionError('external journal access refused')
        return original_open(path,mode,*args,**kwargs)

    monkeypatch.setattr(Path, 'open', deny_append)
    ordinary_plans = []

    def local_plan(*args, **kwargs):
        ordinary_plans.append(True)
        return dict(sufficient=True,files=[])

    monkeypatch.setattr(capture_retention, 'plan', local_plan)
    result = capture_retention.reserve(current, 200, application_root=root)
    assert result['sufficient'] and result['vault_unavailable'] and ordinary_plans
    assert not result.get('storage_maintenance') and blob.is_file()
    assert archive.read_png(path.with_suffix('.png')) == original


def test_failed_vault_commit_returns_the_verified_blob_to_its_original_location(tmp_path, monkeypatch):
    from maalimbus import native_cold_vault, workspace

    root = tmp_path / 'project'
    path, entry, original = batch(root, monkeypatch)
    (path.parent / 'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped')), encoding='utf8')
    archive.compact(root)
    blob = root / archive.load_index(root)['members'][entry['path']]['archive']
    native_cold_vault.enable(root)
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(root) + 100)
    append = native_cold_vault._append

    def fail_commit(journal, data):
        if data['stage'] == 'committed':
            raise OSError('failed audit write')
        append(journal, data)

    monkeypatch.setattr(native_cold_vault, '_append', fail_commit)
    with pytest.raises(OSError, match='failed audit write'):
        native_cold_vault.offload(root, target_free=200)
    assert blob.is_file()
    assert archive.read_png(path.with_suffix('.png')) == original
