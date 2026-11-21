"""The public-tree check refuses private paths, game assets and unclassified files.

All inputs are synthetic: byte strings and archives built in the test.
"""
import base64
import io
import struct
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import check_public_tree  # noqa: E402


def png(extra_chunk=None):
    ok, data = cv2.imencode('.png', np.full((4, 4, 3), 200, dtype=np.uint8))
    assert ok
    data = data.tobytes()
    if extra_chunk:
        kind, body = extra_chunk
        chunk = struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        data = data[:33] + chunk + data[33:]  # directly after IHDR
    return data


def categories(name, data=b'plain text\n'):
    return [category for category, _ in check_public_tree.examine(name, lambda: data)]


@pytest.mark.parametrize('name, expected', [
    ('src/maalimbus/runner.py', []),
    ('docs/examples/config/user-task-settings.json', []),
    ('requirements-lock.txt', []),
    ('LICENSE', []),
    ('config/user-run-ledger.json', ['private_path']),
    ('evidence/runtime/run-a/frame-0001.json', ['private_path']),
    ('PROJECT.md', ['private_path']),
    ('logs/agent.log', ['private_path']),
    ('tools/probe.log', ['private_path']),
    ('settings.local.json', ['private_path']),
    ('.env', ['private_path']),
    ('assets/resource/base/image/gifts/abc.png', ['game_asset']),
    ('tests/fixtures/frames/map-1/frame-0001.png', ['game_asset']),
    ('desktop/mxu/teamArtwork.ts', ['game_asset']),
    ('yolo11n.pt', ['game_asset']),
    ('docs/screenshot.png', ['binary']),
    ('assets/misc/other-icon.png', ['binary']),
    ('tools/helper.exe', ['binary']),
    ('notes.docx', ['unknown_type']),
])
def test_each_path_is_classified(name, expected):
    assert categories(name) == expected


def test_the_json_beside_the_bitmaps_is_public():
    assert categories('assets/resource/base/image/reward/provenance.json', b'{}') == []
    assert categories('tests/fixtures/frames/map-1/frame-0001.json', b'{}') == []


def test_the_icon_is_allowed_only_without_metadata():
    assert categories('assets/misc/Don-Quixote.png', png()) == []
    assert categories('assets/misc/Don-Quixote.png', png((b'tEXt', b'Software\x00somewhere'))) == ['image_metadata']
    assert categories('assets/misc/Don-Quixote.png', png((b'caBX', b'x' * 40))) == ['image_metadata']


def test_an_image_encoded_into_source_is_found_and_a_bare_prefix_is_not():
    encoded = b'export const A = "data:image/png;base64,' + base64.b64encode(png() * 4) + b'";\n'
    assert categories('desktop/mxu/other.ts', encoded) == ['embedded_image']
    assert categories('tools/export.py', b"prefix = 'data:image/png;base64,' + value\n") == []


def test_private_text_is_reported_by_category_and_line_only():
    text = 'ok\n' + 'path = r"C:' + chr(92) + 'Users' + chr(92) + 'someone' + chr(92) + 'file"\n'
    findings = check_public_tree.examine('docs/note.md', lambda: text.encode())
    assert findings == [('private_text', 'docs/note.md line 2 (local_user_path)')]
    assert 'someone' not in repr(findings)


def planted():
    return {
        'README.md': b'# readme\n',
        'src/maalimbus/x.py': b'x = 1\n',
        'assets/resource/base/image/gifts/a.png': png(),
        'config/user-team-profiles.json': b'{}',
    }


def test_a_zip_archive_is_checked_under_its_top_level_directory(tmp_path):
    archive = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive, 'w') as target:
        for name, data in planted().items():
            target.writestr('MaaLimbus-abc123/' + name, data)
    findings = check_public_tree.check(check_public_tree.unpacked(archive))
    assert sorted(findings) == [('game_asset', 'assets/resource/base/image/gifts/a.png'),
                                ('private_path', 'config/user-team-profiles.json')]
    assert check_public_tree.main(['--archive', str(archive)]) == 1


def test_a_tarball_is_checked_and_a_clean_one_passes(tmp_path, capsys):
    dirty, clean = tmp_path / 'dirty.tar.gz', tmp_path / 'clean.tar.gz'
    for archive, members in ((dirty, planted()), (clean, dict(list(planted().items())[:2]))):
        with tarfile.open(archive, 'w:gz') as target:
            for name, data in members.items():
                info = tarfile.TarInfo('maalimbus-0.1.2/' + name)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
    assert check_public_tree.main(['--archive', str(dirty)]) == 1
    assert check_public_tree.main(['--archive', str(clean)]) == 0
    assert '2 members, 0 finding(s)' in capsys.readouterr().out


def test_a_directory_is_checked_file_by_file(tmp_path):
    for name, data in planted().items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
    assert check_public_tree.main(['--dir', str(tmp_path)]) == 1


def test_the_files_this_checkout_tracks_are_publishable():
    if not (ROOT / '.git').exists():
        pytest.skip('not a git checkout: tracking cannot be read from an unpacked source archive')
    assert check_public_tree.check(check_public_tree.tracked(ROOT)) == []
