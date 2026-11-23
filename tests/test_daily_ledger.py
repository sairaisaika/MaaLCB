"""The day's schedule is worked once per server day, resumed after an interruption.

This is the bookkeeping for hosting the app around the clock. The reset defaults are
stated values, not measurements, so the tests pin the arithmetic, not the game.
"""
from datetime import datetime, timedelta, timezone

import pytest

from maalimbus.daily_ledger import DailyLedger, checked, server_day, server_week, wanted

KST = timezone(timedelta(hours=9))
SCHEDULE = dict(experience=2, thread=1, mirror_runs=3, mirror_weekdays=(1, 5), rewards=True, stamina=False)


def kst(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=KST)


def test_the_server_day_turns_at_six_korea_time_not_at_midnight():
    assert server_day(kst(24, 5, 59)) == '2026-11-23'
    assert server_day(kst(24, 6, 0)) == '2026-11-24'
    # The same instant read from another timezone is the same server day.
    assert server_day(kst(24, 6, 0).astimezone(timezone.utc)) == '2026-11-24'
    with pytest.raises(ValueError):
        server_day(datetime(2026, 11, 24, 6, 0))


def test_the_server_week_starts_on_thursday():
    assert server_week(kst(25, 12)) == '2026-11-19'      # Wednesday belongs to last Thursday's week
    assert server_week(kst(26, 5)) == '2026-11-19'       # Thursday before the reset hour still does
    assert server_week(kst(26, 6)) == '2026-11-26'
    assert server_week(kst(26, 6), start=0) == '2026-11-23'


def test_the_mirror_runs_are_owed_only_on_the_chosen_weekdays():
    tuesday, wednesday = kst(24, 12), kst(25, 12)
    assert wanted(SCHEDULE, tuesday) == dict(rewards=1, stamina=0, experience=2, thread=1, mirror=3)
    assert wanted(SCHEDULE, wednesday)['mirror'] == 0
    # 03:00 on Wednesday is still the server's Tuesday.
    assert wanted(SCHEDULE, kst(25, 3))['mirror'] == 3


def test_a_day_is_worked_in_order_and_nothing_is_done_twice(tmp_path):
    ledger = DailyLedger(tmp_path / 'daily.json')
    now = kst(24, 12)
    assert [row['item'] for row in ledger.owed(SCHEDULE, now)] == ['rewards', 'experience', 'thread', 'mirror']
    ledger.book('rewards', now)
    ledger.book('experience', now)
    assert ledger.next_item(SCHEDULE, now) == dict(item='experience', left=1, wanted=2, done=1, failed=0, given_up=False)
    # A new process reads the same bookings: an interrupted day resumes, it does not restart.
    resumed = DailyLedger(tmp_path / 'daily.json')
    resumed.book('experience', now + timedelta(hours=1))
    resumed.book('thread', now + timedelta(hours=1))
    resumed.book('mirror', now + timedelta(hours=2), count=3)
    assert resumed.owed(SCHEDULE, now + timedelta(hours=3)) == []
    assert resumed.summary(SCHEDULE, now + timedelta(hours=3))['finished'] is True


def test_the_next_server_day_owes_everything_again_and_keeps_the_week(tmp_path):
    ledger = DailyLedger(tmp_path / 'daily.json')
    ledger.book('experience', kst(24, 12), count=2)
    tomorrow = kst(25, 12)
    assert [row['item'] for row in ledger.owed(SCHEDULE, tomorrow)] == ['rewards', 'experience', 'thread']
    ledger.book('experience', tomorrow)
    assert ledger.data['day'] == '2026-11-25' and ledger.data['done']['experience'] == 1
    assert ledger.data['week_done']['experience'] == 3
    assert ledger.data['history'][-1] == dict(day='2026-11-24', done=dict(rewards=0, stamina=0, experience=2,
                                                                         thread=0, mirror=0),
                                              failed=dict(rewards=0, stamina=0, experience=0, thread=0, mirror=0))
    # Thursday starts a new week.
    ledger.book('thread', kst(26, 12))
    assert ledger.data['week'] == '2026-11-26' and ledger.data['week_done'] == dict(
        rewards=0, stamina=0, experience=0, thread=1, mirror=0)


def test_a_failing_item_is_retried_then_left_without_blocking_the_others(tmp_path):
    ledger = DailyLedger(tmp_path / 'daily.json')
    now = kst(24, 12)
    ledger.book('rewards', now)
    assert ledger.fail('experience', now, 'lux_navigation_successor_requires_verification') is False
    assert ledger.next_item(SCHEDULE, now)['item'] == 'experience'
    assert ledger.fail('experience', now, 'lux_navigation_successor_requires_verification') is True
    assert ledger.next_item(SCHEDULE, now)['item'] == 'thread'
    summary = ledger.summary(SCHEDULE, now)
    row = next(item for item in summary['items'] if item['item'] == 'experience')
    assert row['error'] == 'lux_navigation_successor_requires_verification' and summary['finished'] is False
    # A success clears the failures; the next server day starts clean either way.
    ledger.book('experience', now)
    assert ledger.data['failed']['experience'] == 0 and 'experience' not in ledger.data['last_error']
    ledger.fail('thread', now, 'x')
    assert ledger.owed(SCHEDULE, kst(25, 12))[1]['failed'] == 0


@pytest.mark.parametrize('schedule, field', [
    (dict(experience=-1), 'experience'), (dict(thread=21), 'thread'), (dict(mirror_runs='3'), 'mirror_runs'),
    (dict(mirror_weekdays=(7,)), 'mirror_weekdays'), (dict(mirror_weekdays=(1, 1)), 'mirror_weekdays'),
    (dict(rewards=1), 'rewards'), (dict(daily=True), 'daily')])
def test_a_schedule_that_is_out_of_range_is_refused_by_name(schedule, field):
    with pytest.raises(ValueError, match=field):
        checked(schedule)


def test_an_empty_schedule_owes_nothing(tmp_path):
    ledger = DailyLedger(tmp_path / 'daily.json')
    assert ledger.owed({}, kst(24, 12)) == [] and ledger.next_item(None, kst(24, 12)) is None
    with pytest.raises(ValueError):
        ledger.book('lunch', kst(24, 12))
