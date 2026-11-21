"""Cut recognition templates out of the user's own screenshots.

The templates in the ``navigation``, ``reward``, ``event`` and ``map`` groups are small
crops of game pages.  They are not in the repository.  This tool writes them into
``assets/resource/base/image/`` from files the user already has on this machine:

  python tools/import_local_templates.py --frame SHOT.png --template image/navigation/tutorial-back.png
      crop the rectangle the manifest records for that template out of a 1920x1080
      screenshot of the same page.

  python tools/import_local_templates.py --bitmap CROP.png --template image/event/odds_high.png
      take a crop the user cut by hand, for a template whose rectangle was never
      recorded.  The crop must have the pixel size the manifest lists.

The output is re-encoded, so no metadata of the source file is carried over.  The tool
reads local files only; it does not download, upload or invent a bitmap.  Exit status 0
on success, 2 when the input does not fit the manifest.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import local_assets  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--frame', type=Path, help='your own full screenshot of the page')
    source.add_argument('--bitmap', type=Path, help='a crop you cut by hand')
    parser.add_argument('--template', required=True, action='append',
                        help='manifest path, e.g. image/navigation/tutorial-back.png; repeatable with --frame')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--force', action='store_true', help='replace a template that already exists')
    args = parser.parse_args(argv)

    import cv2

    manifest = local_assets.load(args.root)
    rows = {row['path']: row for row in manifest['files']}
    base = args.root / manifest['root']
    path = args.frame or args.bitmap
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        print('Cannot read %s as an image.' % path)
        return 2
    height, width = image.shape[:2]
    if args.bitmap is not None and len(args.template) != 1:
        print('--bitmap supplies exactly one template.')
        return 2
    written = []
    for name in args.template:
        row = rows.get(name)
        if row is None or row['origin'] != 'own-capture':
            print('%s is not an own-capture template in %s.' % (name, local_assets.MANIFEST))
            return 2
        target = base / name
        if target.exists() and not args.force:
            print('%s already exists; pass --force to replace it.' % name)
            return 2
        if args.frame is not None:
            if 'crop' not in row:
                print('%s has no recorded rectangle; cut it by hand (%dx%d px) and pass --bitmap.'
                      % (name, *row['size']))
                return 2
            if [width, height] != row['frame_size']:
                print('%s needs a %dx%d screenshot; this one is %dx%d.'
                      % (name, *row['frame_size'], width, height))
                return 2
            x, y, w, h = row['crop']
            crop = image[y:y + h, x:x + w]
        else:
            if [width, height] != row['size']:
                print('%s must be %dx%d px; this bitmap is %dx%d.' % (name, *row['size'], width, height))
                return 2
            crop = image
        target.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode('.png', crop)
        if not ok:
            print('Cannot encode %s.' % name)
            return 2
        target.write_bytes(encoded.tobytes())
        written.append(name)
    for name in written:
        print('wrote %s' % name)
    print('Run python tools/check_local_assets.py to see what is still missing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
