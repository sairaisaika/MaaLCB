"""The stale-freeze trap is a guard test, not a habit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import check_freeze  # noqa: E402


def test_a_current_freeze_is_accepted():
    report = check_freeze.verdict(head_sha='a' * 40, frozen_sha='a' * 40)
    assert report['state'] == 'current' and report['reason'] is None


def test_a_missing_build_names_the_repair():
    report = check_freeze.verdict(head_sha='a' * 40, frozen_sha=None)
    assert report['state'] == 'missing'
    assert 'refreeze' in report['reason']


def test_a_stale_freeze_is_reported_with_the_gap():
    report = check_freeze.verdict(head_sha='b' * 40, frozen_sha='a' * 40)
    assert report['state'] == 'stale'
    assert report['frozen'] == 'a' * 40 and report['head'] == 'b' * 40
    assert 'old code' in report['reason']


def test_a_folder_that_is_not_a_git_checkout_has_no_head(tmp_path, monkeypatch):
    """A downloaded source archive has no ``.git``; asking for HEAD answers None, not an error."""
    monkeypatch.setattr(check_freeze, 'ROOT', tmp_path)
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))
    assert check_freeze.head() is None


def test_without_a_git_checkout_the_freeze_is_missing_not_stale():
    report = check_freeze.verdict(head_sha=None, frozen_sha=None)
    assert report['state'] == 'missing' and 'refreeze' in report['reason']
    report = check_freeze.verdict(head_sha=None, frozen_sha='a' * 40)
    assert report['state'] == 'missing' and 'not a git checkout' in report['reason']


def test_the_repository_is_current_right_now():
    """Skips instead of failing when the checkout is not a full git history."""
    report = check_freeze.verdict()
    if report['state'] == 'missing':
        import pytest
        pytest.skip(report['reason'])
    assert report['state'] in {'current', 'stale'}
