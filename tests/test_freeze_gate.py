"""A stale frozen app must refuse a live run, not quietly test old code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_freeze import runnable  # noqa: E402


def test_a_current_bundle_may_run():
    assert runnable({'state': 'current'})['run'] is True


def test_a_stale_bundle_is_refused_by_default():
    gate = runnable({'state': 'stale', 'frozen': 'abc', 'head': 'def'})
    assert gate['run'] is False
    assert gate['reason'] == 'the_frozen_app_predates_the_source_being_tested'


def test_a_missing_bundle_is_refused_too():
    assert runnable({'state': 'missing'})['run'] is False


def test_the_escape_hatch_says_so_in_the_record():
    gate = runnable({'state': 'stale'}, allow_stale=True)
    assert gate['run'] is True and gate['reason'] == 'stale_build_allowed_explicitly'


def test_a_test_only_commit_does_not_invalidate_the_artifact(tmp_path, monkeypatch):
    """The gate asks 'does the artifact carry this source', not 'is HEAD identical'."""
    import check_freeze
    import json
    import subprocess
    from maalimbus.build_fingerprint import source_snapshot
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'src').mkdir()
    module=tmp_path/'src/core.py';module.write_text('value=1')
    info=tmp_path/'build-info.json'
    info.write_text(json.dumps({'source_commit':'old','source_snapshot':source_snapshot(tmp_path)}))
    monkeypatch.setattr(check_freeze,'ROOT',tmp_path)
    monkeypatch.setattr(check_freeze,'BUILD_INFO',info)
    monkeypatch.setattr(check_freeze,'head',lambda:'test-only-new')
    (tmp_path/'notes.md').write_text('documentation changed')
    report=check_freeze.verdict()
    assert report['state']=='current' and report['source_snapshot_verified']
    module.write_text('value=2')
    assert check_freeze.verdict()['state']=='stale'
