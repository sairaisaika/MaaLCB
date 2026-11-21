"""Compression must retain original bytes, reference pins and failure visibility."""
from pathlib import Path
import hashlib
import json
import zipfile

import pytest

from maalimbus import capture_retention, evidence_reports as reports


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def archive(root, members, *, zip_members=None):
    build = root / 'build'
    build.mkdir(exist_ok=True)
    target = build / 'historical-run-reports.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as out:
        for name, body in (zip_members or list(members.items())):
            out.writestr(name, body)
    index = dict(version=1, kind='evidence_report_archive',
        archive='build/historical-run-reports.zip', sha256=_sha(target.read_bytes()),
        members=[dict(path=name, bytes=len(body), sha256=_sha(body)) for name, body in members.items()])
    path = root / reports.INDEX
    path.write_text(json.dumps(index), encoding='utf-8')
    return target, path, index


def test_archived_report_bytes_and_all_original_frame_pins_survive_raw_retirement(tmp_path):
    report = tmp_path / 'build/old-run.json'
    report.parent.mkdir()
    original = b'{"frame":"evidence/runtime/old-run/frame-0001.json", "steps":[]}\r\n'
    report.write_bytes(original)
    before = capture_retention._reference_keep(tmp_path)
    assert (tmp_path / 'evidence/runtime/old-run/frame-0001.png') in before
    archive(tmp_path, {'build/old-run.json': original})
    report.unlink()
    assert reports.read_report_bytes('build/old-run.json', root=tmp_path) == original
    assert capture_retention._reference_keep(tmp_path) == before


def test_missing_archive_aborts_reclamation_instead_of_discarding_reference_pins(tmp_path):
    target, _, _ = archive(tmp_path, {'build/old.json': b'{"frame":"evidence/runtime/old/frame-0001.json"}'})
    target.unlink()
    with pytest.raises(ValueError, match='archive missing'):
        capture_retention._reference_keep(tmp_path)


def test_archive_byte_changes_are_not_hidden_by_reference_cache_or_unchanged_timestamp(tmp_path):
    target, _, _ = archive(tmp_path, {'build/old.json': b'{"frame":"evidence/runtime/old/frame-0001.json"}'})
    capture_retention._reference_keep(tmp_path)
    old_stat = target.stat()
    body = bytearray(target.read_bytes())
    body[-1] ^= 1
    target.write_bytes(body)
    import os
    os.utime(target, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    with pytest.raises(ValueError, match='archive bytes changed'):
        capture_retention._reference_keep(tmp_path)


def test_index_changes_cannot_reuse_cached_member_trust(tmp_path):
    _, path, index = archive(tmp_path, {'build/old.json': b'{"steps":[]}'})
    capture_retention._reference_keep(tmp_path)
    index['members'][0]['sha256'] = '0' * 64
    path.write_text(json.dumps(index), encoding='utf-8')
    with pytest.raises(ValueError, match='member hash changed'):
        capture_retention._reference_keep(tmp_path)


def test_duplicate_zip_members_are_refused_even_when_zip_digest_matches(tmp_path):
    data = b'{"steps":[]}'
    with pytest.warns(UserWarning, match='Duplicate name'):
        archive(tmp_path, {'build/old.json': data},
                zip_members=[('build/old.json', data), ('build/old.json', data)])
    with pytest.raises(ValueError, match='changed or duplicated'):
        reports.read_report_bytes('build/old.json', root=tmp_path)


@pytest.mark.parametrize('name', ['../old.json', 'build/../old.json', '/build/old.json',
                                 'config/user-run-ledger.json', 'build/old.png', reports.INDEX])
def test_archive_cannot_address_private_state_escape_paths_or_recursively_archive_its_index(tmp_path, name):
    archive(tmp_path, {name: b'{}'})
    with pytest.raises(ValueError):
        reports.load_index(tmp_path)


def test_declared_oversized_report_is_refused_before_expansion(tmp_path):
    _, path, index = archive(tmp_path, {'build/old.json': b'{}'})
    index['members'][0]['bytes'] = reports.MAX_MEMBER_BYTES + 1
    path.write_text(json.dumps(index), encoding='utf-8')
    with pytest.raises(ValueError, match='size or digest'):
        reports.load_index(tmp_path)


def test_current_raw_report_and_missing_unknown_report_keep_their_distinct_meanings(tmp_path):
    target = tmp_path / 'build/current.json'
    target.parent.mkdir()
    target.write_bytes(b'{"current":true}')
    assert reports.read_report_bytes(target, root=tmp_path) == target.read_bytes()
    with pytest.raises(FileNotFoundError):
        reports.read_report_bytes('build/unknown.json', root=tmp_path)


def test_archive_symlink_member_is_not_treated_as_a_report(tmp_path):
    target, path, index = archive(tmp_path, {'build/old.json': b'{}'})
    with zipfile.ZipFile(target, 'w') as out:
        info = zipfile.ZipInfo('build/old.json')
        info.external_attr = (0o120777 << 16)
        out.writestr(info, b'{}')
    index['sha256'] = _sha(target.read_bytes())
    path.write_text(json.dumps(index), encoding='utf-8')
    with pytest.raises(ValueError, match='type or size changed'):
        reports.read_report_bytes('build/old.json', root=tmp_path)
