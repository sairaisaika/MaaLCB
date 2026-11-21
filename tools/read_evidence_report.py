"""Inspect a current or archived build report; never modifies a game transaction."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from maalimbus.evidence_reports import read_report_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', help='Original build/report.json path')
    parser.add_argument('--text', action='store_true', help='Print original report text instead of metadata')
    args = parser.parse_args()
    content = read_report_bytes(args.path, root=ROOT)
    document = json.loads(content)
    if args.text:
        print(content.decode('utf-8'), end='')
    else:
        print(json.dumps(dict(path=args.path, bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            keys=sorted(document) if isinstance(document, dict) else None)))


if __name__ == '__main__':
    main()
