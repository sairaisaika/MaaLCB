"""Copy the Lix-origin game bitmaps from a reference checkout the user supplies.

The ``gifts``, ``themes`` and ``battle`` icons (and one theme-page clip) are unmodified
files of LixAssistantLimbusCompany at the pinned commit.  They are not in this
repository.  Clone that project yourself into ``sources/upstream/`` (a git-ignored
directory), check out the pinned commit, then run:

  python tools/import_lix_assets.py

Every file is compared with the SHA-256 the manifest records before it is written, so a
different revision or an edited file is refused and named.  The catalogs
(``gift-catalog.json`` and friends) are not rewritten.  The tool reads the local
checkout only: it does not clone, download or upload.  Exit status 0 when every
Lix-origin file is in place, 2 otherwise.
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))

from maalimbus import local_assets  # noqa: E402
import pinned_lalc  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    manifest = local_assets.load(args.root)
    rows = [row for row in manifest['files'] if row['origin'] == 'lix']
    base = args.root / manifest['root']
    upstream_dir = args.root / manifest['lix']['local_checkout']
    if not upstream_dir.is_dir() and not upstream_dir.with_name(upstream_dir.name + '.source.zip').is_file():
        print('No reference checkout at %s.' % manifest['lix']['local_checkout'])
        print('Clone %s there yourself and check out %s; see %s.'
              % (manifest['lix']['repository'], manifest['lix']['commit'], local_assets.GUIDE))
        return 2
    copied, kept, refused = 0, 0, []
    with pinned_lalc.checkout(args.root, manifest['lix']['commit']) as upstream:
        for row in rows:
            source = upstream / row['source']
            target = base / row['path']
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == row['sha256']:
                kept += 1
                continue
            if not source.is_file():
                refused.append((row['path'], 'absent from the reference checkout'))
                continue
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                refused.append((row['path'], 'reference file differs from the recorded SHA-256'))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            copied += 1
    print('copied %d, already present %d, refused %d of %d Lix-origin files'
          % (copied, kept, len(refused), len(rows)))
    for path, reason in refused:
        print('  %s: %s' % (path, reason))
    return 2 if refused else 0


if __name__ == '__main__':
    raise SystemExit(main())
