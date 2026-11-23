"""One small row per finished task, kept after the task's frames are gone.

`run_report` reads every stored run's journal, so its picture only reaches back as far
as the journals do. This module writes the same numbers down once, when a task ends, as
one line of `user-run-history.jsonl` in the data folder. The file grows by about 2 kB
per task and is what a trend is drawn from: per-floor time across the runs of one game
run, where tasks stop, how often the program waited or re-read, how much storage a task
moved out.

A row names no account, device or local path: a task is identified by its run folder's
name and a game run by the first eight characters of its id, so a history file can be
shared when asking for help.

Pure functions except `append` and `load`. Nothing here reads a frame or the device,
and nothing here decides anything about the game.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from . import run_report

NAME = 'user-run-history.jsonl'
#: The public goal's first sign: no floor slower than this (Wiki 9, public-goal, G1).
FLOOR_TARGET_SECONDS = 600
#: Event names counted as "the program waited instead of acting".
WAITS = ('loop_waited', 'window_unknown_wait', 'window_transition_wait', 'window_loading_wait')
#: Event names counted as "one read was not enough".
REREADS = ('capture_profile_full_reread', 'unknown_reread_recovered')
#: A history file past this many rows keeps reporting; `trend` reads the newest ones.
TREND_ROWS = 400


def _seconds(rows):
    """Program seconds of a journal: its gaps, without the ones spent waiting for a person."""
    total, last, first = 0.0, None, None
    for row in rows:
        now = run_report._stamp(row)
        if now is None:
            continue
        first = first or now
        if last is not None:
            gap = (now - last).total_seconds()
            if 0 <= gap < run_report.IDLE_GAP:
                total += gap
        last = now
    return total, first, last


def checkpoints(rows, floors):
    """Counted observations of one task: how it spent effort, not whether it was right.

    Every value is a count or a list read straight off the journal, so two tasks can be
    compared and a change in the program shows up as a change in these numbers.
    """
    events = collections.Counter(row.get('event') for row in rows if row.get('event'))
    refused = sum(n for name, n in events.items() if 'refused' in name)
    # A reading the program asked for and did not get: `map_party_unread`, `battle_frame_unreadable`, ...
    unread = sum(n for name, n in events.items() if name.endswith('_unread') or 'unreadable' in name)
    return dict(
        waits=sum(events[name] for name in WAITS),
        rereads=sum(events[name] for name in REREADS),
        refusals=refused,
        unread=unread,
        inputs=events['window_intent'],
        observations=events['step_observation'],
        steps=events['step_finished'],
        battle_turns=events['battle_turn_advanced'],
        purchases=events['shop_purchase_confirmed'],
        floors_over_target=sorted(floor for floor, seconds in floors.items() if seconds > FLOOR_TARGET_SECONDS))


def summary(run, rows, *, task=None, result=None, storage=None):
    """The history row of one finished task. `run` is the run folder's name."""
    result = result or {}
    time = run_report.run_time(rows)
    seconds, first, last = _seconds(rows)
    floors = {int(floor): round(value, 1) for floor, value in time['floors'].items()}
    row = dict(
        version=1, run=str(run), task=task or result.get('task'),
        scope=(time['scope'] or '')[:8] or None,
        started=first.isoformat() if first else None, ended=last.isoformat() if last else None,
        program_seconds=round(seconds, 1),
        passed=bool(result.get('passed')), reason=result.get('reason'),
        floors=floors,
        battle={int(floor): round(value, 1) for floor, value in time['battle'].items()},
        pages={page: round(value, 1) for page, value in time['pages'].items()},
        steps=dict(time['steps']),
        checkpoints=checkpoints(rows, floors),
        events=dict(collections.Counter(row.get('event') for row in rows if row.get('event'))))
    if storage and not storage.get('skipped'):
        row['storage'] = {key: storage.get(key) for key in (
            'moved', 'moved_bytes', 'after_bytes', 'archive_bytes', 'reached', 'over_line', 'seconds')}
    return row


def append(directory, row):
    """Add one row to the history file in the data folder; return the file's path."""
    path = Path(directory) / NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    return path


def load(directory):
    """Every readable row of the history file, oldest first. A damaged line is skipped."""
    path = Path(directory) / NAME
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('version') == 1:
            rows.append(value)
    return rows


def trend(rows, *, last=TREND_ROWS):
    """What the recorded tasks say together.

    A floor is usually played across several tasks (a task stops, the next one resumes
    the same game run), so a floor's time is the sum over the tasks of one game run.
    """
    rows = list(rows)[-last:]
    tasks = collections.Counter()
    passed = collections.Counter()
    stops = collections.Counter()
    totals = collections.Counter()
    per_scope = collections.defaultdict(collections.Counter)
    pages = collections.Counter()
    moved = 0
    for row in rows:
        task = row.get('task') or 'unknown'
        tasks[task] += 1
        if row.get('passed'):
            passed[task] += 1
        elif row.get('reason'):
            stops[row['reason']] += 1
        for name, value in (row.get('checkpoints') or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[name] += value
        for floor, seconds in (row.get('floors') or {}).items():
            if row.get('scope'):
                per_scope[row['scope']][int(floor)] += seconds
        for page, seconds in (row.get('pages') or {}).items():
            pages[page] += seconds
        moved += (row.get('storage') or {}).get('moved_bytes') or 0
    game_runs = []
    for scope, floors in per_scope.items():
        slowest = max(floors, key=floors.get)
        game_runs.append(dict(scope=scope, floors={floor: round(floors[floor] / 60, 1) for floor in sorted(floors)},
                              slowest_floor=slowest, slowest_minutes=round(floors[slowest] / 60, 1),
                              within_target=floors[slowest] <= FLOOR_TARGET_SECONDS))
    program = sum(row.get('program_seconds') or 0 for row in rows)
    page_total = sum(pages.values())
    return dict(
        tasks=len(rows), first=rows[0].get('started') if rows else None, last=rows[-1].get('ended') if rows else None,
        program_minutes=round(program / 60, 1),
        by_task=[dict(task=task, count=count, passed=passed[task]) for task, count in tasks.most_common()],
        game_runs=game_runs,
        slowest_floor_minutes=max((run['slowest_minutes'] for run in game_runs), default=None),
        floor_target_minutes=FLOOR_TARGET_SECONDS / 60,
        pages=[dict(page=page, minutes=round(seconds / 60, 1), share=round(seconds / page_total, 3))
               for page, seconds in pages.most_common(8)] if page_total else [],
        stops=[dict(reason=reason, count=count) for reason, count in stops.most_common()],
        checkpoints=dict(totals),
        storage_moved_bytes=moved)


def lines(report):
    """The trend as text, for a terminal."""
    out = ['tasks %s (%s .. %s), program time %s min' % (
        report['tasks'], report['first'], report['last'], report['program_minutes'])]
    for row in report['by_task']:
        out.append('  %-12s %3d tasks, %d passed' % (row['task'], row['count'], row['passed']))
    out.append('slowest floor: %s min (target %s)' % (report['slowest_floor_minutes'], report['floor_target_minutes']))
    for run in report['game_runs']:
        floors = ', '.join('%s: %s' % (floor, minutes) for floor, minutes in run['floors'].items())
        out.append('  game run %s  floors (min) %s' % (run['scope'], floors))
    out.append('pages by time:')
    for row in report['pages']:
        out.append('  %-20s %6.1f min %5.1f%%' % (row['page'], row['minutes'], 100 * row['share']))
    out.append('stops by reason (%d):' % sum(row['count'] for row in report['stops']))
    for row in report['stops']:
        out.append('  %2d  %s' % (row['count'], row['reason']))
    out.append('checkpoints: ' + ', '.join('%s=%s' % item for item in sorted(report['checkpoints'].items())))
    out.append('storage moved to the archive: %.2f GB' % (report['storage_moved_bytes'] / 1e9))
    return out


def notice(row):
    """One line for the task's own log: what this task's numbers say, or None."""
    slow = (row.get('checkpoints') or {}).get('floors_over_target') or []
    if not slow:
        return None
    worst = max(slow, key=lambda floor: row['floors'][floor])
    return '本次任务内第 %s 层已用 %.0f 分钟，超过每层 %.0f 分钟的目标。' % (
        worst, row['floors'][worst] / 60, FLOOR_TARGET_SECONDS / 60)
