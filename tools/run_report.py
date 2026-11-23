"""Where the program's time went and where it stopped, over many stored runs.

    python tools/run_report.py                 # every stored run of the installed app and the harness
    python tools/run_report.py --scope a84a    # only runs of the game run whose id starts with a84a
    python tools/run_report.py --last 20 --json
    python tools/run_report.py --history       # the rows each finished task wrote, frames or no frames

Read-only: it opens ``events.jsonl`` of each run and nothing else. Runs are found under
``evidence/runtime/packaged-mirror-*`` (harness) and ``dist/MaaLimbus/evidence/runtime/pi-*``
(the installed app started from MXU). The output names runs by directory name only.

``--history`` reads ``user-run-history.jsonl`` instead: one row per finished task, written
by the task itself, in the installed app's data folder (or ``--data`` for another folder).
It reaches back further than the journals do and needs no stored run.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from maalimbus import run_history, run_report  # noqa: E402

SOURCES = (('evidence/runtime', 'packaged-mirror-*'), ('dist/MaaLimbus/evidence/runtime', 'pi-*'))


def stored_runs(root=ROOT):
    found = [path for folder, pattern in SOURCES for path in (root / folder).glob(pattern)
             if (path / 'events.jsonl').is_file()]
    return sorted(found, key=lambda path: path.name.split('-', 1)[-1])


def load(run):
    rows = []
    for line in (run / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def history_folders(root=ROOT):
    """Where a history file can be: the installed app's data folder, then the checkout's."""
    return [root / 'dist/MaaLimbus/config', root / 'config']


def history(args):
    folders = [args.data] if args.data else history_folders()
    rows = next((found for found in (run_history.load(folder) for folder in folders) if found), [])
    if args.scope:
        rows = [row for row in rows if (row.get('scope') or '').startswith(args.scope[:8])]
    if args.last:
        rows = rows[-args.last:]
    if not rows:
        print('no recorded tasks')
        return 1
    report = run_history.trend(rows)
    print(json.dumps(report, ensure_ascii=False, indent=1) if args.json else '\n'.join(run_history.lines(report)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scope', help='only runs whose game-run id starts with this')
    parser.add_argument('--last', type=int, help='only the most recent N stored runs')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--history', action='store_true', help='read the per-task history file instead')
    parser.add_argument('--data', type=pathlib.Path, help='data folder holding the history file')
    args = parser.parse_args(argv)
    if args.history:
        return history(args)
    runs = stored_runs()
    if args.last:
        runs = runs[-args.last:]
    loaded = []
    for run in runs:
        rows = load(run)
        if args.scope:
            scopes = {row.get('run_scope') for row in rows if row.get('event') == 'mirror_loop_start'}
            if not any(scope and scope.startswith(args.scope) for scope in scopes):
                continue
        loaded.append((run.name, rows))
    report = run_report.combine(loaded)
    if not report['runs']:
        print('no stored runs')
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=1) if args.json else '\n'.join(run_report.lines(report)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
