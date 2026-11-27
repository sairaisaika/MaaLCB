"""Read the deployment order of the first N saved teams off the game's team screen.

The order a team deploys in is printed on the game's own team screen, one number on each
of the twelve cards. The player opens that screen, says how many teams to read, and the
task goes down the ``TEAMS`` list from #1: it selects a team, reads its twelve numbers
and records them for that team -- team 1's reading under team 1, and so on
(`team_order_record`, ``user-team-order-records.json``). A team's settings can then
choose "use the recorded order" (`global_settings`, ``RECORD``).

The user asked for it in this shape (2026-11-27) after the first version, which read one
frame and wrote the order straight into the team's profile: read in the task, choose in
the settings.

What it sends: one press on a row of the ``TEAMS`` list per team, and a drag of that list
when the row is not on screen (`team_navigation.browse`, the search the run itself uses
to find its team). Nothing on a card is pressed and nothing is saved by the game.

A team is recorded only when the page says it shows that team (``TEAMS #n`` in the
header) and all twelve numbers read as a complete 1..12. Anything less records nothing
for that team and the result says which team and why; the others are still read.

The team page inside a dungeon has no list and prints no ``TEAMS #n``: the run's team is
fixed there (replayed on eight frames of pi-20261126-233844: twelve numbers, no team
number). On that page the one team shown is the run's, which the ledger names, and it
is recorded for that team whatever number was asked for.
"""
from . import team_navigation, team_order_record
from .storage import read_json
from .team_order import order_from_badges
from .vision import Text

#: Why a set of numbers is not an order, in the player's words.
WHY = dict(badge_count='卡片数量不足十二张', badge_missing='有卡片的编号没读到',
           badge_range='读到了 1–12 以外的编号', badge_duplicate='两张卡读成了同一个编号')
#: Why a team could not be reached or read.
FAILED = dict(
    team_order_numbers_unread='编号没有读全',
    team_order_row_press_did_not_select='点了列表里的这一行，但页面没有切到这支队伍',
    team_sidebar_rows_not_read='没读到左侧的 TEAMS 列表',
    team_list_search_stalled='在列表里上下都找过了，没有这一行',
    team_list_search_budget_exhausted='在列表里找这一行用完了次数',
    saved_team_slot_invalid='队伍编号无效')
#: How often one team may be looked at before it is given up: reads, presses and drags together.
TRIES = 16
#: How often the header may show the team with numbers that do not make an order.
UNREAD = 2
#: How often a row may be pressed without the header following.
PRESSES = 3


def _names(order):
    return '、'.join(team_order_record.DISPLAY[position - 1] for position in order)


def _texts(record):
    return [Text(item['text'], tuple(item['box']), item['score']) for item in (record or {}).get('ocr') or []]


def read(directory, count, *, observe, press, drag, team_state, frame, browse=team_navigation.browse):
    """Record the orders of teams 1..`count`; returns the task result with a `message`.

    `observe()` gives a fresh frame record, `team_state(record)` is the run's own reading
    of the team page, `press(box)` and `drag(start_box, to_point)` send the two inputs
    and return the frame that followed, and `frame()` names the frame file a record
    points at.
    """
    if type(count) is not int or not 1 <= count <= 40:
        raise ValueError('The number of teams to read must be 1..40')
    recorded, failed, inputs = [], [], 0
    record = observe()
    team = team_state(record) or {}
    numbers = team.get('numbers') or []
    size = tuple((record or {}).get('size') or (1920, 1080))
    if not any(type(number) is int for number in numbers):
        return dict(passed=False, reason='team_order_cards_not_visible', input_sent=False, recorded=[], failed=[],
                    message='这一帧上没有读到带编号的人格卡。请先在游戏里打开编队界面（能看到十二张卡和上面的出战编号），再运行本任务。')
    if team.get('saved_team') is None and not team_navigation.sidebar_rows(_texts(record), size):
        # Inside a dungeon: one team, no list, no number on the page.
        ledger = directory / 'user-run-ledger.json'
        active = read_json(ledger).get('active') if ledger.exists() else None
        order, reason = order_from_badges(numbers)
        if not active or type(active.get('team')) is not int:
            return dict(passed=False, reason='team_order_team_number_unread', input_sent=False, recorded=[], failed=[],
                        message='这一页没有 TEAMS 列表，也没有显示 TEAMS #几，又没有正在进行的镜牢可以对应，'
                                '不知道读到的顺序属于哪支队伍，没有录入。请在镜牢外的编队界面（左侧有 TEAMS 列表）运行。')
        if order is None:
            return dict(passed=False, reason='team_order_numbers_unread', input_sent=False, recorded=[], failed=[],
                        numbers=list(numbers), message='编号没有读全，没有录入：%s。' % WHY.get(reason, reason))
        slot = active['team']
        team_order_record.record(directory, slot, numbers, frame())
        return dict(passed=True, reason='team_orders_recorded', input_sent=False, slot_source='run_in_progress',
                    recorded=[dict(slot=slot, positions=list(order))], failed=[],
                    message='这一页是镜牢里的编队页，只有正在进行的这一局所用的队伍 %d：已录入 %s。' % (slot, _names(order)))
    for slot in range(1, count + 1):
        state, unread, presses, outcome = {}, 0, 0, None
        for _ in range(TRIES):
            team = team_state(record) or {}
            numbers = team.get('numbers') or []
            if team.get('saved_team') == slot:
                order, reason = order_from_badges(numbers)
                if order is not None:
                    team_order_record.record(directory, slot, numbers, frame())
                    outcome = dict(slot=slot, positions=list(order))
                    break
                unread += 1
                if unread >= UNREAD:
                    outcome = dict(slot=slot, reason='team_order_numbers_unread', detail=reason, numbers=list(numbers))
                    break
                record = observe()      # the page may still be drawing the cards of the team just selected
                continue
            step = browse(_texts(record), tuple(record.get('size') or size), slot, state)
            if step.get('target'):
                if presses >= PRESSES:
                    outcome = dict(slot=slot, reason='team_order_row_press_did_not_select')
                    break
                presses += 1
                inputs += 1
                record = press(step['target'])
            elif step.get('start'):
                inputs += 1
                record = drag(step['start'], step['to'])
            else:
                outcome = dict(slot=slot, reason=step.get('reason') or 'team_sidebar_rows_not_read')
                break
        if outcome is None:
            outcome = dict(slot=slot, reason='team_list_search_budget_exhausted')
        (recorded if 'positions' in outcome else failed).append(outcome)
    lines = ['队伍 %d：%s' % (one['slot'], _names(one['positions'])) for one in recorded]
    missed = ['队伍 %d（%s%s）' % (one['slot'], FAILED.get(one['reason'], one['reason']),
                                 '：' + WHY.get(one['detail'], one['detail']) if one.get('detail') else '')
              for one in failed]
    message = ('已录入 %d 支队伍的出战顺序。%s' % (len(recorded), '；'.join(lines)) if recorded else '没有录入任何队伍。')
    if missed:
        message += ' 没读到：%s。' % '、'.join(missed)
    if recorded:
        message += ' 要使用，请在总设置里该队伍的「出战顺序」选「使用录入记录」。'
    reason = ('team_orders_recorded' if not failed else
              'team_orders_partly_recorded' if recorded else failed[0]['reason'])
    return dict(passed=not failed, reason=reason, input_sent=inputs > 0, clicks_sent=inputs, asked=count,
                recorded=recorded, failed=failed, message=message)
