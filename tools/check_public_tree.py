"""Check that a tree or a package carries only what may be published.

  python tools/check_public_tree.py                  # the files git tracks in this checkout
  python tools/check_public_tree.py --dir DIR        # every file under a directory
  python tools/check_public_tree.py --archive FILE   # a .zip, .whl, .tar.gz or .tar

Tracking, ignoring and packaging are separate facts, so each published form is checked
on its own: a file can be ignored and still sit in an archive.  The check refuses

  private_path     a path under a local-only directory (config/, evidence/, logs/, ...)
  game_asset       a path the local-asset rules cover (game bitmaps, the editor artwork)
  binary           an image, model, archive or executable that is not on the short list
  unknown_type     a file type nobody has classified yet
  embedded_image   an image encoded into a text file
  image_metadata   a PNG chunk beyond the pixels (text, EXIF, provenance blobs)
  private_text     a local user path, player or device identifier, or credential

It prints the category and the member path, never the matched text.  Exit status 0 when
nothing is found, 1 otherwise.  It reads; it changes nothing.
"""
import argparse
import io
import re
import struct
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import public_privacy  # noqa: E402

PRIVATE_PREFIXES = ('config/', 'evidence/', 'logs/', 'runs/', 'build/', 'dist/', 'sources/',
                    '.codex/', '.research/', '.scratch/', '.venv/', 'tests/local/', 'tools/local/')
PRIVATE_NAMES = ('PROJECT.md',)
GAME_BITMAP_PREFIXES = ('assets/resource/base/image/', 'tests/fixtures/frames/',
                        'tests/fixtures/floor-gift-ocr-drift/')
GAME_FILES = ('desktop/mxu/teamArtwork.ts', 'yolo11n.pt')
#: The only binaries that are published, each with its provenance in THIRD_PARTY_NOTICES.
ALLOWED_BINARIES = ('assets/misc/Don-Quixote.png',
                    'assets/resource/base/model/ocr/det.onnx',
                    'assets/resource/base/model/ocr/rec.onnx')
BINARY_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.svg', '.tif', '.tiff',
                   '.pt', '.pth', '.onnx', '.npy', '.npz', '.wav', '.mp3', '.ogg', '.mp4', '.webm',
                   '.zip', '.7z', '.xz', '.gz', '.tar', '.exe', '.dll', '.pyd', '.so', '.pdf'}
TEXT_SUFFIXES = public_privacy.TEXT | {'.mjs', '.gitignore', '.gitattributes'}
TEXT_NAMES = {'LICENSE', '.gitignore', '.gitattributes'}
#: Files a build adds beside the sources; they are text and are scanned like the rest.
PACKAGING_NAMES = {'PKG-INFO', 'METADATA', 'WHEEL', 'RECORD', 'SOURCES.txt', 'top_level.txt',
                   'requires.txt', 'dependency_links.txt', 'setup.cfg', 'entry_points.txt'}
PNG_PIXEL_CHUNKS = {'IHDR', 'IDAT', 'IEND', 'PLTE', 'tRNS'}
EMBEDDED_IMAGE = re.compile(rb'data:image/[a-z+.-]+;base64,[A-Za-z0-9+/=]{200,}')


def png_extra_chunks(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return ['not-a-png']
    extra, offset = set(), 8
    while offset + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[offset:offset + 8])
        kind = kind.decode('latin-1')
        if kind not in PNG_PIXEL_CHUNKS:
            extra.add(kind)
        offset += 12 + length
    return sorted(extra)


def examine(name, read):
    """Findings for one member: ``name`` is repository-relative, ``read()`` its bytes."""
    path = PurePosixPath(name)
    suffix = path.suffix.lower()
    found = []
    if (name.startswith(PRIVATE_PREFIXES) or path.name in PRIVATE_NAMES
            or not public_privacy.public_member(path) and suffix != '.jsonl'):
        return [('private_path', name)]
    if name in GAME_FILES or (name.startswith(GAME_BITMAP_PREFIXES) and suffix == '.png'):
        return [('game_asset', name)]
    if suffix in BINARY_SUFFIXES:
        if name not in ALLOWED_BINARIES:
            return [('binary', name)]
        if suffix == '.png':
            extra = png_extra_chunks(read())
            if extra:
                found.append(('image_metadata', '%s (%s)' % (name, ' '.join(extra))))
        return found
    if suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES | PACKAGING_NAMES:
        return [('unknown_type', name)]
    data = read()
    if EMBEDDED_IMAGE.search(data):
        found.append(('embedded_image', name))
    for row in public_privacy.text_findings(name, data):
        found.append(('private_text', '%s line %d (%s)' % (name, row['line'], row['category'])))
    return found


def tracked(root):
    names = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True,
                           check=True).stdout.decode('utf-8').split('\0')
    return [(name, (root / name).read_bytes) for name in names if name]


def walked(root):
    return [(path.relative_to(root).as_posix(), path.read_bytes)
            for path in sorted(root.rglob('*')) if path.is_file() and '.git' not in path.relative_to(root).parts]


def unpacked(archive):
    """Members of an archive, with the single top-level directory of a source archive removed."""
    members = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                if not info.is_dir():
                    members.append((info.filename, source.read(info)))
    else:
        with tarfile.open(archive) as source:
            for info in source:
                if info.isfile():
                    members.append((info.name, source.extractfile(info).read()))
    tops = {name.split('/', 1)[0] for name, _ in members}
    if len(tops) == 1 and all('/' in name for name, _ in members):
        members = [(name.split('/', 1)[1], data) for name, data in members]
    return [(name, (lambda data=data: data)) for name, data in members]


def check(members):
    findings = []
    for name, read in members:
        findings.extend(examine(name, read))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--dir', type=Path, help='check every file under this directory')
    source.add_argument('--archive', type=Path, help='check the members of this archive or wheel')
    parser.add_argument('--root', type=Path, default=ROOT, help='checkout whose tracked files are checked')
    args = parser.parse_args(argv)
    if args.archive is not None:
        members, label = unpacked(args.archive), args.archive.name
    elif args.dir is not None:
        members, label = walked(args.dir.resolve()), str(args.dir)
    else:
        members, label = tracked(args.root.resolve()), 'tracked files'
    findings = check(members)
    for category, detail in findings:
        print('%-15s %s' % (category, detail))
    counts = {}
    for category, _ in findings:
        counts[category] = counts.get(category, 0) + 1
    print('%s: %d members, %d finding(s)%s' % (label, len(members), len(findings),
                                              ''.join(' %s=%d' % row for row in sorted(counts.items()))))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
