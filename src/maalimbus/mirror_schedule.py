"""The Mirror task asks the day's ledger whether it still owes a run today.

Hosting the app on a timer means "Start" is pressed many times a day. Without a schedule
the Mirror task plays every time it is started. With one, it plays only on the chosen
weekdays and only until the day's number of complete runs is booked; a start on another
day, or after the day's runs are done, ends at once without touching the game.

The schedule lives in the Mirror task's own options (which days, how many runs), so no
second "daily" entry repeats the task's settings. The bookings live in the day ledger
(`daily_ledger`), per server day. A run is booked only when the loop reports it complete:
five floors, the reward claimed and the lobby reached (`runner._verified_runs`).

Nothing here reads a frame or sends input.
"""
from __future__ import annotations

import json
from pathlib import Path

from .daily_ledger import DailyLedger

#: Option value -> weekdays, Monday = 0. `off` means the task is not scheduled.
DAYS = {
    'off': None,
    'every_day': (0, 1, 2, 3, 4, 5, 6),
    'weekdays': (0, 1, 2, 3, 4),
    'weekend': (5, 6),
    'mon_wed_fri': (0, 2, 4),
    'tue_thu_sat': (1, 3, 5),
}
RUNS = (1, 2, 3, 5)
LEDGER = 'user-daily-ledger.json'
#: The rewards task's result for a run it finished itself: reward claimed and lobby reached.
PAYOUT_REASON = 'mirror_payout_and_home_verified'


def collect(get_node):
    """(days, runs) from the task's option nodes; a pipeline built before them has neither.

    A caller with no node reader at all (a context that carries no pipeline) is not scheduled.
    """
    if get_node is None:
        return 'off', 1
    try:
        days = get_node('MirrorSchedule').get('attach', {}).get('days', 'off')
        runs = get_node('MirrorRunsPerDay').get('attach', {}).get('runs', 1)
    except KeyError:
        return 'off', 1
    if days not in DAYS:
        raise ValueError('Unknown Mirror schedule')
    if type(runs) is not int or runs not in RUNS:
        raise ValueError('Mirror runs per day must be one of %s' % (RUNS,))
    return days, runs


def gate(directory, days, runs, now):
    """What today still owes, or None when the task is not scheduled.

    `left` is the number of complete runs this start may play. Zero comes with the
    reason: the day is not one of the chosen days, or its runs are already booked.
    """
    if DAYS[days] is None:
        return None
    schedule = dict(mirror_runs=runs, mirror_weekdays=DAYS[days])
    ledger = DailyLedger(Path(directory) / LEDGER)
    row = next((item for item in ledger.summary(schedule, now)['items'] if item['item'] == 'mirror'), None)
    wanted = row['wanted'] if row else 0
    done = row['done'] if row else 0
    left = max(0, wanted - done)
    reason = None
    if not left:
        reason = 'mirror_schedule_done_today' if wanted else 'mirror_not_scheduled_today'
    return dict(days=days, runs_per_day=runs, day=ledger.data['day'], wanted=wanted, done=done, left=left,
                reason=reason)


def run_count(asked, left):
    """The loop's run count for this start: never more than the day still owes."""
    asked = int(asked or 0)
    return min(asked, left) if asked > 0 else left


def book_result(directory, run_directory, now):
    """Book the complete runs this start delivered; return how many were booked.

    Reads the task's own result file: the Mirror loop reports how many runs it completed,
    and the rewards task reports the one run it finished by claiming its reward. A result
    that names no complete run books nothing: a stop halfway is not a run, and the day
    keeps owing it.
    """
    try:
        result = json.loads((Path(run_directory) / 'agent-result.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 0
    completed = (result.get('verified_runs') or {}).get('completed')
    if type(completed) is not int or completed < 1:
        if result.get('passed') is not True or result.get('reason') != PAYOUT_REASON:
            return 0
        completed = 1
    DailyLedger(Path(directory) / LEDGER).book('mirror', now, count=completed, proof=Path(run_directory).name)
    return completed
