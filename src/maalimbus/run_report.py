"""Many runs in, one picture out: where the program's time went and where it stopped.

Pure functions over journal rows (``events.jsonl``). Nothing here reads a frame, a
ledger or the device, and nothing in the result names an account, a device or a local
path: a run is identified by its directory name only, so a report can be shared.

The time of a run is the sum of the gaps between its consecutive journal rows. A gap
longer than ``IDLE_GAP`` seconds is not program time (the app sat stopped waiting for a
person) and is left out. Each gap is attributed to the floor the run had reached
(``page_checkpoint.progress.cleared_floors``) and to the page of the last finished step.
"""
from __future__ import annotations

import collections
from datetime import datetime

#: A gap longer than this is the app waiting for someone, not the program working.
IDLE_GAP = 120.0
#: Pages that belong to a fight: commands, animation, loading and its result.
BATTLE_PAGES = ('BATTLE_HUD', 'UNKNOWN', 'LOADING', 'BATTLE_RESULT', 'BATTLE_VICTORY')
#: Ends that are a bound the caller set, not a fault of the run.
BOUNDS = ('the_budget_could_not_pay_for_another_step', 'loop_deadline_exceeded', 'step_limit_reached')


def _stamp(row):
    value = row.get('utc')
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def run_time(rows):
    """Seconds per floor and per page, steps per page, and the run's stop, for one run."""
    floors = collections.Counter()
    battle = collections.Counter()
    pages = collections.Counter()
    steps = collections.Counter()
    floor, page, last = None, None, None
    scope, stop = None, None
    for row in rows:
        event = row.get('event')
        if event == 'mirror_loop_start':
            scope = row.get('run_scope') or scope
        if event == 'page_checkpoint':
            cleared = (row.get('progress') or {}).get('cleared_floors')
            if cleared is not None:
                # With five floors cleared the run is being paid out, not played: that time
                # belongs to no floor. It used to be booked as a "floor 6".
                floor = len(cleared) + 1 if len(cleared) < 5 else None
        now = _stamp(row)
        if now is not None:
            if last is not None:
                gap = (now - last).total_seconds()
                if 0 <= gap < IDLE_GAP:
                    if floor is not None:
                        floors[floor] += gap
                        if page in BATTLE_PAGES:
                            battle[floor] += gap
                    if page is not None:
                        pages[page] += gap
            last = now
        if event == 'step_finished':
            page = row.get('page')
            if page is not None:
                steps[page] += 1
        if event == 'mirror_loop_stopped':
            stop = dict(reason=row.get('reason'), page=page, floor=floor,
                        clicks=row.get('clicks_sent'), passed=bool(row.get('passed')))
    return dict(scope=scope, floors=dict(floors), battle=dict(battle), pages=dict(pages),
                steps=dict(steps), stop=stop)


def combine(runs):
    """One report for many runs. ``runs`` is an iterable of ``(name, rows)``."""
    floors = collections.Counter()
    battle = collections.Counter()
    pages = collections.Counter()
    steps = collections.Counter()
    stops = collections.Counter()
    where = collections.defaultdict(collections.Counter)
    names = []
    for name, rows in runs:
        one = run_time(rows)
        if not one['pages'] and one['stop'] is None:
            continue
        names.append(name)
        floors.update(one['floors'])
        battle.update(one['battle'])
        pages.update(one['pages'])
        steps.update(one['steps'])
        stop = one['stop']
        if stop and not stop['passed'] and stop['reason'] not in BOUNDS:
            stops[stop['reason']] += 1
            where[stop['reason']][(stop['floor'], stop['page'])] += 1
    total = sum(pages.values())
    return dict(
        runs=len(names), first=names[0] if names else None, last=names[-1] if names else None,
        program_minutes=round(total / 60, 1),
        floors=[dict(floor=floor, minutes=round(floors[floor] / 60, 1), battle_minutes=round(battle[floor] / 60, 1))
                for floor in sorted(floors)],
        slowest_floor_minutes=round(max(floors.values()) / 60, 1) if floors else None,
        pages=[dict(page=page, steps=steps[page], minutes=round(seconds / 60, 1),
                    seconds_per_step=round(seconds / steps[page], 1) if steps[page] else None,
                    share=round(seconds / total, 3) if total else None)
               for page, seconds in pages.most_common()],
        stops=[dict(reason=reason, count=count,
                    where=[dict(floor=floor, page=page, count=n) for (floor, page), n in where[reason].most_common(3)])
               for reason, count in stops.most_common()])


def lines(report, *, top=12):
    """The report as text, for a terminal."""
    out = ['runs %s (%s .. %s), program time %s min' % (report['runs'], report['first'], report['last'],
                                                         report['program_minutes'])]
    out.append('slowest floor: %s min' % report['slowest_floor_minutes'])
    for row in report['floors']:
        out.append('  floor %s: %5.1f min, of which battle %5.1f' % (row['floor'], row['minutes'], row['battle_minutes']))
    out.append('pages by time:')
    for row in report['pages'][:top]:
        out.append('  %-20s %4d steps %6.1f min %5s s/step %5.1f%%' % (
            row['page'], row['steps'], row['minutes'],
            '-' if row['seconds_per_step'] is None else row['seconds_per_step'], 100 * (row['share'] or 0)))
    out.append('stops by reason (%d):' % sum(row['count'] for row in report['stops']))
    for row in report['stops'][:top]:
        place = ', '.join('floor %s %s x%d' % (w['floor'], w['page'], w['count']) for w in row['where'])
        out.append('  %2d  %s  [%s]' % (row['count'], row['reason'], place))
    return out
