"""Repeated starts reuse identical bytes; capacity/corruption fail before swap."""
from pathlib import Path

import pytest

from maalimbus import launcher_cache


def setup(root):
    app=root/'dist/MaaLimbus';source=app/'launcher';source.mkdir(parents=True)
    (source/'MaaLimbusLauncher.exe').write_bytes(b'executable')
    (source/'lib').mkdir();(source/'lib/runtime.dll').write_bytes(b'runtime')
    return source,app


def test_repeated_start_reuses_exact_same_external_bundle(tmp_path):
    source,app=setup(tmp_path)
    first=launcher_cache.stage_launcher(source,app)
    before={p:p.stat().st_mtime_ns for p in first.rglob('*') if p.is_file()}
    for _ in range(3):assert launcher_cache.stage_launcher(source,app)==first
    assert before=={p:p.stat().st_mtime_ns for p in first.rglob('*') if p.is_file()}
    assert list(app.parent.glob('.maalimbus-launcher-*'))==[first]


def test_new_version_does_not_overwrite_running_old_bundle(tmp_path):
    source,app=setup(tmp_path);old=launcher_cache.stage_launcher(source,app)
    (source/'MaaLimbusLauncher.exe').write_bytes(b'updated')
    new=launcher_cache.stage_launcher(source,app)
    assert new!=old and (old/'MaaLimbusLauncher.exe').read_bytes()==b'executable'
    assert (new/'MaaLimbusLauncher.exe').read_bytes()==b'updated'


def test_bad_cached_bytes_are_not_overwritten(tmp_path):
    source,app=setup(tmp_path);cached=launcher_cache.stage_launcher(source,app)
    (cached/'lib/runtime.dll').write_bytes(b'damaged')
    with pytest.raises(ValueError,match='Cached launcher'):
        launcher_cache.stage_launcher(source,app)
    assert (cached/'lib/runtime.dll').read_bytes()==b'damaged'


def test_no_room_fails_before_copy(tmp_path,monkeypatch):
    source,app=setup(tmp_path)
    def reject(root,needed):
        assert root==tmp_path and needed==len(b'executable')+len(b'runtime')+4096
        raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(launcher_cache,'require_space',reject)
    with pytest.raises(ValueError,match='budget exceeded'):launcher_cache.stage_launcher(source,app)
    assert not list(app.parent.glob('.maalimbus-launcher-*'))


def test_failed_partial_copy_leaves_no_cache_or_staging(tmp_path,monkeypatch):
    source,app=setup(tmp_path)
    def fail(source,target):
        target.mkdir();(target/'partial').write_bytes(b'partial')
        raise OSError('injected failure')
    monkeypatch.setattr(launcher_cache.shutil,'copytree',fail)
    with pytest.raises(OSError,match='injected failure'):launcher_cache.stage_launcher(source,app)
    assert not list(app.parent.glob('.maalimbus-launcher-*'))
    assert (source/'MaaLimbusLauncher.exe').read_bytes()==b'executable'
