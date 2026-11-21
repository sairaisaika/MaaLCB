"""Report which local game assets this checkout has, and which it lacks.

Usage: ``python tools/check_local_assets.py [--json] [--root DIR]``

Exit status: 0 every group is complete; 2 at least one group has a missing or invalid
file.  The report names groups, counts and repository-relative paths only.  It reads
files; it never downloads, writes or uploads anything.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import local_assets  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='print the full inventory as JSON')
    parser.add_argument('--root', type=Path, default=ROOT, help='checkout or app folder to inspect')
    args = parser.parse_args(argv)
    groups = local_assets.inventory(args.root)
    bad = local_assets.incomplete(groups)
    if args.json:
        print(json.dumps(dict(complete=not bad, groups=groups), ensure_ascii=False, indent=1))
    else:
        for name, group in sorted(groups.items()):
            state = 'MISSING' if name in bad else 'ok'
            print('%-10s %-7s %3d/%d present (%d match the reference, %d own captures), %d invalid'
                  % (name, state, group['total'] - len(group['missing']), group['total'],
                     group['verified'], group['unverified'], len(group['invalid'])))
        for line in local_assets.describe(groups):
            print('  ' + line)
        if bad:
            print('Game assets are not part of this repository. Follow %s to supply them locally.'
                  % local_assets.GUIDE)
        else:
            print('All local game asset groups are present.')
    return 2 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
