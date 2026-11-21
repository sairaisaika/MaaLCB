"""A release never carries game artwork, even when the machine that builds it holds some.

Synthetic throughout: byte strings stand in for bitmaps, and a throwaway git repository
stands in for the checkout.
"""
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from maalimbus import local_assets
from maalimbus.release_package import export_assets
from maalimbus.update_stage import StageError

from test_release_package import candidate, manifest

ROOT = Path(__file__).resolve().parents[1]


def package_tool():
    spec = importlib.util.spec_from_file_location('build_windows_package', ROOT / 'tools/build_windows_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_clean_package_folder_carries_no_game_asset(tmp_path):
    app = tmp_path / 'app'
    candidate(app)
    (app / 'assets/resource/base/image/reward').mkdir(parents=True)
    (app / 'assets/resource/base/image/reward/provenance.json').write_text('{}')
    manifest(app)
    assert local_assets.packaged_game_assets(app) == []
    assert export_assets(app, tmp_path / 'assets')['published'] is False


@pytest.mark.parametrize('planted', ['bitmap', 'editor_artwork', 'nested_bitmap', 'nested_editor_artwork'])
def test_a_package_folder_that_holds_game_artwork_is_not_exported(tmp_path, planted):
    app = tmp_path / 'app'
    candidate(app)
    if planted == 'bitmap':
        target = app / 'assets/resource/base/image/gifts/abc.png'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'stand-in for an imported icon')
        expected = 'assets/resource/base/image/gifts/abc.png'
    elif planted == 'editor_artwork':
        (app / 'desktop').mkdir()
        (app / 'desktop/teamArtwork.ts').write_text('export const SINNER_IMAGES = [];')
        expected = 'desktop/teamArtwork.ts'
    else:
        member = ('MaaLimbus/assets/resource/base/image/themes/pack_search.png' if planted == 'nested_bitmap'
                  else 'mxu/src/utils/teamArtwork.ts')
        with zipfile.ZipFile(app / 'sources/MXU-MaaLimbus-source.zip', 'w') as archive:
            archive.writestr('mxu/README.md', 'source')
            archive.writestr(member, 'stand-in')
        expected = 'sources/MXU-MaaLimbus-source.zip!' + member
    manifest(app)
    assert local_assets.packaged_game_assets(app) == [expected]
    with pytest.raises(StageError, match='game asset'):
        export_assets(app, tmp_path / 'assets')
    assert not (tmp_path / 'assets').exists()


def test_release_resources_come_from_the_commit_not_from_the_working_tree(tmp_path):
    """An imported bitmap and an untracked note sit in the folder; neither is a release input."""
    repo = tmp_path / 'repo'
    (repo / 'assets/resource/base/image/gifts').mkdir(parents=True)
    (repo / 'docs').mkdir()
    (repo / 'assets/resource/base/gift-catalog.json').write_text('{"committed": true}')
    (repo / 'assets/resource/base/trace.jsonl').write_text('{}')
    (repo / 'docs/guide.md').write_text('committed guide')
    (repo / 'README.md').write_text('committed readme')

    def git(*arguments):
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                        *arguments], check=True, capture_output=True)
    git('init', '-q')
    git('add', '-A')
    git('commit', '-q', '-m', 'synthetic')
    # After the commit: a locally imported bitmap, an untracked note and an uncommitted edit.
    (repo / 'assets/resource/base/image/gifts/abc.png').write_bytes(b'stand-in for an imported icon')
    (repo / 'docs/private-note.md').write_text('untracked')
    (repo / 'docs/guide.md').write_text('edited but not committed')

    app = tmp_path / 'app'
    written = package_tool().copy_committed(('assets', 'docs', 'README.md'), app, root=repo)
    files = sorted(path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file())
    assert files == ['README.md', 'assets/resource/base/gift-catalog.json', 'docs/guide.md'] and written == 3
    assert (app / 'docs/guide.md').read_text() == 'committed guide'
    assert local_assets.packaged_game_assets(app) == []


@pytest.mark.parametrize('entry', ['agent/main.py', 'tools/run_native.py'])
def test_a_frozen_entry_points_at_the_packaged_framework_before_importing_it(entry):
    """``maa`` opens its native library at import, and the package keeps it in ``maafw/``.

    The packaged runner lacked this and could not even print its help: the first full
    release build from a clean clone stopped there.
    """
    text = (ROOT / entry).read_text(encoding='utf-8')
    setting = text.index("os.environ['MAAFW_BINARY_PATH']")
    first_import = min(text.index(marker) for marker in ('\nfrom maa.', '\nimport maa') if marker in text)
    assert "getattr(sys, 'frozen', False)" in text[:setting] and setting < first_import


def test_the_package_lists_the_absent_game_assets_as_pending():
    pending = package_tool().pending_items(verified_dungeon_clear=True)
    assert any('game assets are not included' in item and 'docs/local-assets.md' in item for item in pending)
    assert json.dumps(pending)  # plain strings: the list goes into build-info.json as it is


def test_the_published_self_test_carries_no_build_machine_path(tmp_path):
    """build-info.json travels with the package; where it was built is nobody's business."""
    from maalimbus import public_privacy

    app = tmp_path / 'Users' / 'someone' / 'build' / 'MaaLimbus-win-x64'
    (app / 'config').mkdir(parents=True)
    reported = dict(passed=True, application_root=str(app), runner_root=str(app),
                    private_state_directory=str(app / 'config'), locales=['en', 'jp'])
    record = package_tool().portable_self_test(reported, app)
    assert record == dict(passed=True, application_root='.', runner_root='.',
                          private_state_directory='config', locales=['en', 'jp'])
    assert reported['application_root'] == str(app)  # the caller's own record is untouched
    text = json.dumps(dict(self_test=record), indent=2)
    assert public_privacy.text_findings('build-info.json', text.encode()) == []
    with pytest.raises(ValueError):
        package_tool().portable_self_test(dict(application_root=str(tmp_path / 'elsewhere')), app)


def test_the_checksum_file_has_one_plain_line_that_sha256sum_reads(tmp_path):
    """Written on Windows it used to end in CRLF, and `sha256sum -c` then failed to open the file."""
    import hashlib
    app = tmp_path / 'app'
    candidate(app)
    manifest(app)
    exported = export_assets(app, tmp_path / 'assets')
    archive = Path(exported['archive'])
    data = (tmp_path / 'assets' / 'SHA256SUMS').read_bytes()
    assert data == ('%s  %s\n' % (hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name)).encode('ascii')
    assert b'\r' not in data
