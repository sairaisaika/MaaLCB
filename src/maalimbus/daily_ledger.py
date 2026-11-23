"""What today's schedule still owes, booked per server day so nothing is done twice.

This is the bookkeeping half of hosting the app around the clock. It decides nothing
about the game: it turns "experience dungeon twice a day, thread dungeon once, Mirror
Dungeon on Tuesday and Saturday, three runs" plus the clock into the list of items still
owed, remembers what was done and what failed, and starts over when the server day
turns. The tasks themselves, and what counts as one of them being done, belong to the
task that runs.

The server day is not the calendar day. The defaults below (a day that turns at 06:00
Korea time, a week that starts on Thursday) are the commonly stated reset times and
have **not** been measured against the game by this project; the game's own notice page
stays the authority (see AGENTS.md, "game time and content windows"). Both are
parameters so a measured value can replace them without touching the arithmetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .storage import read_json, write_json

VERSION = 1
#: Hours ahead of UTC of the clock the game's reset is stated in (Korea).
RESET_UTC_OFFSET = 9
#: Local hour of that clock at which a server day turns.
RESET_HOUR = 6
#: Weekday (Monday is 0) on which a server week starts.
WEEK_START = 3
#: The order a day is worked in: the cheap dailies first, the long run last.
ITEMS = ('rewards', 'stamina', 'experience', 'thread', 'mirror')
#: A failing item is tried this many times in one server day, then left for tomorrow.
FAILURES_PER_DAY = 2

DEFAULT_SCHEDULE = dict(experience=0, thread=0, mirror_runs=0, mirror_weekdays=(), rewards=False, stamina=False)


def server_date(now, *, offset=RESET_UTC_OFFSET, hour=RESET_HOUR):
    """The server day ``now`` belongs to, as a date."""
    if now.tzinfo is None:
        raise ValueError('A timezone-aware time is required')
    local = now.astimezone(timezone(timedelta(hours=offset)))
    return (local - timedelta(hours=hour)).date()


def server_day(now, **reset):
    return server_date(now, **reset).isoformat()


def server_week(now, *, start=WEEK_START, **reset):
    """The date the current server week started on, as text."""
    day = server_date(now, **reset)
    return (day - timedelta(days=(day.weekday() - start) % 7)).isoformat()


def checked(schedule):
    """A schedule with every field present and in range, or ValueError naming the field."""
    value = dict(DEFAULT_SCHEDULE, **(schedule or {}))
    unknown = sorted(set(value) - set(DEFAULT_SCHEDULE))
    if unknown:
        raise ValueError('Unknown schedule field: %s' % ', '.join(unknown))
    for name in ('experience', 'thread', 'mirror_runs'):
        if type(value[name]) is not int or not 0 <= value[name] <= 20:
            raise ValueError('Schedule count %s must be an integer from 0 to 20' % name)
    days = tuple(value['mirror_weekdays'])
    if any(type(day) is not int or not 0 <= day <= 6 for day in days) or len(set(days)) != len(days):
        raise ValueError('Schedule mirror_weekdays must be distinct weekdays 0 (Monday) to 6')
    for name in ('rewards', 'stamina'):
        if type(value[name]) is not bool:
            raise ValueError('Schedule switch %s must be true or false' % name)
    value['mirror_weekdays'] = tuple(sorted(days))
    return value


def wanted(schedule, now, **reset):
    """How many of each item the schedule asks for on the server day of ``now``."""
    plan = checked(schedule)
    weekday = server_date(now, **reset).weekday()
    return dict(rewards=1 if plan['rewards'] else 0, stamina=1 if plan['stamina'] else 0,
                experience=plan['experience'], thread=plan['thread'],
                mirror=plan['mirror_runs'] if weekday in plan['mirror_weekdays'] else 0)


def fresh(now, **reset):
    return dict(version=VERSION, day=server_day(now, **reset), week=server_week(now, **reset),
                done={name: 0 for name in ITEMS}, failed={name: 0 for name in ITEMS},
                last_error={}, week_done={name: 0 for name in ITEMS}, history=[])


class DailyLedger:
    """The day's bookings on disk; every change is written before it is reported."""

    def __init__(self, path, **reset):
        self.path = path
        self.reset = reset
        self.data = read_json(path) if path.exists() else None

    def _current(self, now):
        """Today's bookings, starting a new day (and week) when the server clock turned."""
        data = self.data
        day, week = server_day(now, **self.reset), server_week(now, **self.reset)
        if data is None or data.get('version') != VERSION:
            data = fresh(now, **self.reset)
        elif data['day'] != day:
            closed = dict(day=data['day'], done=data['done'], failed=data['failed'])
            history = (data.get('history') or [])[-13:] + [closed]
            week_done = data['week_done'] if data.get('week') == week else {name: 0 for name in ITEMS}
            data = dict(fresh(now, **self.reset), week_done=week_done, history=history)
        self.data = data
        return data

    def owed(self, schedule, now):
        """Items still owed today, in working order, with how many are left of each."""
        data = self._current(now)
        want = wanted(schedule, now, **self.reset)
        rows = []
        for name in ITEMS:
            left = want[name] - data['done'][name]
            if left > 0:
                rows.append(dict(item=name, left=left, wanted=want[name], done=data['done'][name],
                                 failed=data['failed'][name],
                                 given_up=data['failed'][name] >= FAILURES_PER_DAY))
        return rows

    def next_item(self, schedule, now):
        """The first owed item that has not been given up on today, or None."""
        return next((row for row in self.owed(schedule, now) if not row['given_up']), None)

    def book(self, item, now, *, count=1, proof=None):
        """Record ``count`` finished units of ``item`` for the server day of ``now``."""
        if item not in ITEMS or type(count) is not int or count < 1:
            raise ValueError('Unknown item or count')
        data = self._current(now)
        data['done'][item] += count
        data['week_done'][item] += count
        data['failed'][item] = 0
        data['last_error'].pop(item, None)
        if proof:
            data.setdefault('proofs', {}).setdefault(item, []).append(str(proof))
        write_json(self.path, data)
        return data['done'][item]

    def fail(self, item, now, reason):
        """Record that ``item`` did not finish; it is retried, then left for tomorrow."""
        if item not in ITEMS:
            raise ValueError('Unknown item')
        data = self._current(now)
        data['failed'][item] += 1
        data['last_error'][item] = dict(reason=str(reason), at=now.astimezone(timezone.utc).isoformat())
        write_json(self.path, data)
        return data['failed'][item] >= FAILURES_PER_DAY

    def summary(self, schedule, now):
        """What a person wants to see: asked, done, left and why something stopped."""
        data = self._current(now)
        want = wanted(schedule, now, **self.reset)
        return dict(day=data['day'], week=data['week'],
                    items=[dict(item=name, wanted=want[name], done=data['done'][name],
                                left=max(0, want[name] - data['done'][name]),
                                failed=data['failed'][name], error=(data['last_error'].get(name) or {}).get('reason'))
                           for name in ITEMS if want[name] or data['done'][name]],
                    finished=not self.owed(schedule, now))
