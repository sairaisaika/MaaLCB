"""Local game assets: the bitmaps a checkout needs and the repository does not carry.

The game's artwork belongs to its rights holder and nothing establishes that it may be
redistributed, so no game bitmap is tracked, packaged or uploaded.  The manifest
``assets/resource/base/local-assets.json`` records what each one is for, its reference
SHA-256 and its pixel size.  A user supplies the files on their own machine (see
``docs/local-assets.md``); this module only reads what is there and names what is not.

Nothing here downloads, uploads or fabricates a bitmap.  A missing file is reported as
missing: the callers stop with the group's name instead of running with a recogniser that
silently matches nothing.
"""
import hashlib
import json
import struct
from pathlib import Path

MANIFEST = 'assets/resource/base/local-assets.json'
GUIDE = 'docs/local-assets.md'
_PNG = b'\x89PNG\r\n\x1a\n'


class MissingLocalAssets(FileNotFoundError):
    """A local game asset is absent; the message names the group and the guide."""


def missing(relative):
    """The error for one absent bitmap: it names the file, the check tool and the guide."""
    return MissingLocalAssets('Game bitmap %s is not installed. Game assets are supplied locally, not '
                              'shipped: run python tools/check_local_assets.py and see %s'
                              % (relative, GUIDE))


def load(root):
    manifest = json.loads((Path(root) / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('version') != 1:
        raise ValueError('Unsupported local asset manifest')
    return manifest


def png_size(data):
    """(width, height) of PNG bytes, or None when they are not a PNG."""
    if len(data) < 24 or data[:8] != _PNG or data[12:16] != b'IHDR':
        return None
    return list(struct.unpack('>II', data[16:24]))


def inventory(root, manifest=None):
    """Per group: which files are present, missing, or present with the wrong content.

    ``origin == 'lix'`` files are unmodified copies, so their bytes must hash to the
    recorded value.  ``origin == 'own-capture'`` files are cropped from the user's own
    screenshots: their bytes legitimately differ, so only the pixel size is checked and
    the file is counted as ``unverified`` unless it happens to match the reference.
    """
    root = Path(root)
    manifest = load(root) if manifest is None else manifest
    base = root / manifest['root']
    groups = {name: dict(feature=group['feature'], import_tool=group['import_tool'], total=0,
                         verified=0, unverified=0, missing=[], invalid=[])
              for name, group in manifest['groups'].items()}
    for row in manifest['files']:
        group = groups[row['group']]
        group['total'] += 1
        path = base / row['path']
        if not path.is_file():
            group['missing'].append(row['path'])
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == row['sha256']:
            group['verified'] += 1
        elif row['origin'] == 'own-capture' and png_size(data) == row['size']:
            group['unverified'] += 1
        else:
            group['invalid'].append(row['path'])
    return groups


def incomplete(groups):
    """The groups that cannot be used: a file is missing or has the wrong content."""
    return {name: group for name, group in groups.items() if group['missing'] or group['invalid']}


def describe(groups):
    """One line per unusable group, without any file content."""
    lines = []
    for name, group in sorted(incomplete(groups).items()):
        lines.append('%s: %d of %d missing, %d invalid -- needed for %s; supply with %s'
                     % (name, len(group['missing']), group['total'], len(group['invalid']),
                        group['feature'], group['import_tool']))
    return lines


def require(root, names=None):
    """Raise ``MissingLocalAssets`` naming every unusable group among ``names``."""
    groups = inventory(root)
    if names is not None:
        groups = {name: groups[name] for name in names}
    lines = describe(groups)
    if lines:
        raise MissingLocalAssets('Local game assets are not installed (%s). %s'
                                 % ('; '.join(lines), 'See ' + GUIDE))
    return groups


#: The team editor's portraits are game images encoded into this source file.
EDITOR_ARTWORK = 'teamArtwork.ts'


def packaged_game_assets(app):
    """Game artwork inside a folder that is about to be published, as relative paths.

    Importing assets is a local act; publishing them is not allowed.  A package folder
    assembled on a machine that holds the bitmaps would carry them into the release
    archive, so the export asks here first.  Reported are any bitmap under the image
    directory, the editor artwork source, and a nested source archive that contains
    either.  An empty list means the folder carries none.
    """
    import zipfile

    app = Path(app)
    found = []
    images = app / 'assets/resource/base/image'
    if images.is_dir():
        found.extend(path.relative_to(app).as_posix() for path in sorted(images.rglob('*.png')))
    found.extend(path.relative_to(app).as_posix() for path in sorted(app.rglob(EDITOR_ARTWORK)))
    for archive in sorted(app.rglob('*.zip')):
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                member = name.replace(chr(92), '/')
                if (member.rsplit('/', 1)[-1] == EDITOR_ARTWORK
                        or ('assets/resource/base/image/' in member and member.lower().endswith('.png'))):
                    found.append('%s!%s' % (archive.relative_to(app).as_posix(), member))
    return found
