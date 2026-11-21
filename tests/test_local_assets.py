"""Local game assets: absent files are named, never tolerated or invented.

Everything here is synthetic.  The bitmaps are arrays built in the test; no game image
is read, so this module runs on a public checkout and in CI.
"""
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from maalimbus import local_assets
from maalimbus.gift_vision import GiftCatalog
from maalimbus.theme_vision import ThemeCatalog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import check_local_assets  # noqa: E402
import import_lix_assets  # noqa: E402
import import_local_templates  # noqa: E402


def png(width, height, seed=0):
    pixels = np.random.default_rng(seed).integers(0, 255, (height, width, 3), dtype=np.uint8)
    ok, data = cv2.imencode('.png', pixels)
    assert ok
    return data.tobytes()


@pytest.fixture
def checkout(tmp_path):
    """A stand-in checkout that has the manifest and the catalogs, and no bitmap."""
    base = tmp_path / 'assets/resource/base'
    base.mkdir(parents=True)
    for name in ('local-assets.json', 'gift-catalog.json', 'gift-observed-catalog.json', 'theme-catalog.json'):
        shutil.copyfile(ROOT / 'assets/resource/base' / name, base / name)
    return tmp_path


def rows(origin):
    return [row for row in local_assets.load(ROOT)['files'] if row['origin'] == origin]


def test_the_manifest_lists_every_bitmap_once_and_only_bitmaps():
    manifest = local_assets.load(ROOT)
    paths = [row['path'] for row in manifest['files']]
    assert len(paths) == len(set(paths)) == 360
    for row in manifest['files']:
        assert row['path'].startswith('image/%s/' % row['group']) and row['path'].endswith('.png')
        assert row['group'] in manifest['groups'] and len(row['sha256']) == 64
        assert row['origin'] in ('lix', 'own-capture') and ('source' in row) == (row['origin'] == 'lix')
    assert {name: sum(row['group'] == name for row in manifest['files']) for name in manifest['groups']} == dict(
        gifts=332, themes=5, battle=4, navigation=10, reward=4, event=4, map=1)


def test_the_catalogs_and_the_manifest_name_the_same_icons():
    """A catalog entry without a manifest row would be a bitmap nobody is told to supply."""
    base = ROOT / 'assets/resource/base'
    listed = {row['path']: row['sha256'] for row in local_assets.load(ROOT)['files']}
    gifts = json.loads((base / 'gift-catalog.json').read_text(encoding='utf-8'))
    for gift in gifts['gifts']:
        for icon in gift['icons']:
            assert listed[icon['path']] == icon['sha256']
    for name in ('theme-catalog.json', 'battle-catalog.json'):
        for glyph in json.loads((base / name).read_text(encoding='utf-8'))['glyphs'].values():
            assert listed[glyph['path']] == glyph['sha256']


def test_no_game_bitmap_is_tracked_and_every_local_path_is_ignored():
    if not (ROOT / '.git').exists():
        pytest.skip('not a git checkout: tracking cannot be read from an unpacked source archive')
    tracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, check=True
                             ).stdout.decode('utf-8').split('\0')
    images = [path for path in tracked if path.lower().endswith(
        ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.pt'))]
    assert images == ['assets/misc/Don-Quixote.png']
    manifest = local_assets.load(ROOT)
    for row in manifest['files'][::40]:
        path = manifest['root'] + '/' + row['path']
        assert subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', '--', path]).returncode == 0, path


def test_an_empty_checkout_names_all_seven_groups(checkout):
    groups = local_assets.inventory(checkout)
    assert set(local_assets.incomplete(groups)) == set(groups) and len(groups) == 7
    lines = local_assets.describe(groups)
    assert len(lines) == 7 and all('missing' in line and 'tools/import_' in line for line in lines)
    assert groups['gifts']['total'] == len(groups['gifts']['missing']) == 332
    with pytest.raises(local_assets.MissingLocalAssets, match='docs/local-assets.md'):
        local_assets.require(checkout)
    with pytest.raises(local_assets.MissingLocalAssets, match='reward'):
        local_assets.require(checkout, ['reward'])


def test_an_own_capture_is_accepted_by_size_and_a_wrong_size_is_invalid(checkout):
    base = checkout / 'assets/resource/base'
    reward = [row for row in rows('own-capture') if row['group'] == 'reward']
    for row in reward[:-1]:
        (base / row['path']).parent.mkdir(parents=True, exist_ok=True)
        (base / row['path']).write_bytes(png(*row['size']))
    last = reward[-1]
    (base / last['path']).write_bytes(png(last['size'][0] + 1, last['size'][1]))
    group = local_assets.inventory(checkout)['reward']
    assert group['unverified'] == len(reward) - 1 and group['verified'] == 0
    assert group['invalid'] == [last['path']] and group['missing'] == []
    (base / last['path']).write_bytes(png(*last['size']))
    assert 'reward' not in local_assets.incomplete(local_assets.inventory(checkout))
    assert local_assets.require(checkout, ['reward'])['reward']['unverified'] == len(reward)


def test_a_lix_file_with_other_bytes_is_invalid_not_present(checkout):
    row = rows('lix')[0]
    target = checkout / 'assets/resource/base' / row['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png(*row['size']))
    group = local_assets.inventory(checkout)[row['group']]
    assert group['invalid'] == [row['path']] and group['verified'] == 0


def test_bytes_that_are_not_a_png_have_no_size():
    assert local_assets.png_size(b'not an image') is None
    assert local_assets.png_size(png(7, 3)) == [7, 3]


def test_the_gift_and_theme_catalogs_name_the_missing_bitmap(checkout):
    with pytest.raises(local_assets.MissingLocalAssets, match='image/gifts/.*check_local_assets'):
        GiftCatalog(checkout / 'assets/resource/base')
    with pytest.raises(local_assets.MissingLocalAssets, match='image/themes/.*docs/local-assets.md'):
        ThemeCatalog(checkout / 'assets/resource/base')


def test_the_check_tool_exits_2_and_reports_without_file_content(checkout, capsys):
    assert check_local_assets.main(['--root', str(checkout)]) == 2
    text = capsys.readouterr().out
    assert text.count('MISSING') == 7 and 'docs/local-assets.md' in text
    assert check_local_assets.main(['--root', str(checkout), '--json']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['complete'] is False and len(report['groups']['map']['missing']) == 1


def test_a_template_is_cut_from_a_screenshot_the_user_supplies(checkout, tmp_path, capsys):
    shot = tmp_path / 'shot.png'
    shot.write_bytes(png(1920, 1080, seed=3))
    name = 'image/navigation/tutorial-back.png'
    assert import_local_templates.main(['--root', str(checkout), '--frame', str(shot), '--template', name]) == 0
    written = checkout / 'assets/resource/base' / name
    frame = cv2.imread(str(shot))
    assert np.array_equal(cv2.imread(str(written)), frame[50:92, 111:175])
    group = local_assets.inventory(checkout)['navigation']
    assert group['unverified'] == 1 and name not in group['missing']
    # A second run does not silently replace what the user put there.
    assert import_local_templates.main(['--root', str(checkout), '--frame', str(shot), '--template', name]) == 2
    assert 'already exists' in capsys.readouterr().out


@pytest.mark.parametrize('arguments, said', [
    (['--frame', 'small', '--template', 'image/navigation/tutorial-back.png'], 'needs a 1920x1080 screenshot'),
    (['--frame', 'full', '--template', 'image/event/odds_high.png'], 'no recorded rectangle'),
    (['--bitmap', 'small', '--template', 'image/event/odds_high.png'], 'must be 100x35'),
    (['--frame', 'full', '--template', 'image/gifts/unknown.png'], 'not an own-capture template'),
])
def test_an_input_that_does_not_fit_the_manifest_is_refused(checkout, tmp_path, capsys, arguments, said):
    (tmp_path / 'full.png').write_bytes(png(1920, 1080))
    (tmp_path / 'small.png').write_bytes(png(64, 64))
    arguments = [str(tmp_path / (value + '.png')) if value in ('full', 'small') else value for value in arguments]
    assert import_local_templates.main(['--root', str(checkout), *arguments]) == 2
    assert said in capsys.readouterr().out
    assert not list((checkout / 'assets/resource/base').rglob('*.png'))


def test_a_hand_cut_bitmap_of_the_listed_size_is_taken(checkout, tmp_path):
    crop = tmp_path / 'crop.png'
    crop.write_bytes(png(100, 35, seed=5))
    name = 'image/event/odds_high.png'
    assert import_local_templates.main(['--root', str(checkout), '--bitmap', str(crop), '--template', name]) == 0
    assert local_assets.inventory(checkout)['event']['unverified'] == 1


def test_the_lix_import_says_where_the_reference_checkout_goes(checkout, capsys):
    assert import_lix_assets.main(['--root', str(checkout)]) == 2
    text = capsys.readouterr().out
    assert 'sources/upstream/LixAssistantLimbusCompany' in text and 'Clone' in text
    assert not list((checkout / 'assets/resource/base').rglob('*.png'))


def test_the_lix_import_copies_only_bytes_that_match_the_manifest(checkout, tmp_path, monkeypatch, capsys):
    """A synthetic manifest and a synthetic reference tree: one file matches, one was edited."""
    good, edited = png(9, 9, seed=1), png(9, 9, seed=2)
    manifest = local_assets.load(checkout)
    manifest['files'] = [
        dict(path='image/gifts/%s.png' % name, group='gifts', origin='lix', source='img/%s.png' % name,
             size=[9, 9], sha256=hashlib.sha256(good).hexdigest()) for name in 'abc']
    (checkout / local_assets.MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')
    reference = tmp_path / 'reference'
    (reference / 'img').mkdir(parents=True)
    (reference / 'img/a.png').write_bytes(good)
    (reference / 'img/b.png').write_bytes(edited)
    (checkout / 'sources/upstream/LixAssistantLimbusCompany').mkdir(parents=True)

    @contextlib.contextmanager
    def checked_out(root, revision, *, required=()):
        assert revision == manifest['lix']['commit']
        yield reference
    monkeypatch.setattr(import_lix_assets.pinned_lalc, 'checkout', checked_out)
    assert import_lix_assets.main(['--root', str(checkout)]) == 2
    text = capsys.readouterr().out
    assert 'copied 1, already present 0, refused 2 of 3' in text
    assert 'b.png: reference file differs' in text and 'c.png: absent' in text
    base = checkout / 'assets/resource/base/image/gifts'
    assert (base / 'a.png').read_bytes() == good and not (base / 'b.png').exists()


def test_the_input_preflight_stops_before_the_lease_when_assets_are_missing(checkout, monkeypatch, capsys):
    pytest.importorskip('maa')
    sys.path.insert(0, str(ROOT / 'agent'))
    import recognition

    events = []
    journal = SimpleNamespace(record=lambda name, **fields: events.append((name, fields)))

    class Lease:
        @staticmethod
        def acquire(path):
            raise AssertionError('the controller lease was taken although assets are missing')
    monkeypatch.setattr(recognition, 'ROOT', checkout)
    monkeypatch.setattr(recognition, 'ControllerLease', Lease)
    action = recognition.InputPreflight(SimpleNamespace(journal=journal, input_validator=None))
    assert action.run(SimpleNamespace(), SimpleNamespace()) is False
    (name, fields), = events
    assert name == 'preflight_failed' and fields['reason'] == 'local_game_assets_missing'
    assert len(fields['groups']) == 7 and fields['guide'] == 'docs/local-assets.md'
    assert 'local game assets are not installed' in capsys.readouterr().out
