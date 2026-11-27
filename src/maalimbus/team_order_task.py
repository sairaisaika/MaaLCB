"""One press: read the deployment order off the team page and save it for that team.

The order a team deploys in is printed on the game's own team screen, one number on each
of the twelve cards. A run that "follows the game" already reads it at its first battle
(`team_order_record`). This task does the same reading on demand, on whatever team
screen the player has open, and *saves* the result as the team's order, so the settings
do not have to be typed and the order is fixed before a run starts.

It reads one frame and sends no input. Three things must be read, and each failure says
which one was missing: the cards (the page shows the twelve), every number (a complete
1..12 with no repeat), and which saved team the page shows (``TEAMS #n``). Nothing is
saved on a partial reading: a guessed position would deploy the wrong sinner first.

The team page inside a dungeon prints no ``TEAMS #n``: the run's team is fixed there.
Replayed on eight such frames of pi-20261126-233844, all twelve numbers were read and
the team number was not. On that page the team is the one the run in progress entered
with, which the ledger names, so the order is saved for it. Saving does not disturb the
run: what is saved is what the game already shows.
"""
from dataclasses import replace

from . import team_order_record
from .storage import SINNERS, ProfileStore, Team, read_json
from .team_order import order_from_badges

#: Why a set of numbers is not an order, in the player's words.
WHY = dict(badge_count='卡片数量不足十二张', badge_missing='有卡片的编号没读到',
           badge_range='读到了 1–12 以外的编号', badge_duplicate='两张卡读成了同一个编号')


def read(directory, record, controls, frame, *, team_state):
    """Save the order `record` shows; returns the task result with a `message` for the log.

    `team_state` is ``runner.team_state``: the same reading the run itself uses.
    """
    team = team_state(record, controls)
    numbers = (team or {}).get('numbers') or []
    if team is None or not any(type(number) is int for number in numbers):
        return dict(passed=False, reason='team_order_cards_not_visible', input_sent=False,
                    message='这一帧上没有读到带编号的人格卡。请先在游戏里打开编队界面（能看到十二张卡和上面的出战编号），再运行本任务。')
    order, reason = order_from_badges(numbers)
    if order is None:
        unread = [index + 1 for index, number in enumerate(numbers) if type(number) is not int]
        return dict(passed=False, reason='team_order_numbers_unread', input_sent=False, numbers=list(numbers),
                    detail=reason, unread_cards=unread,
                    message='编号没有读全，没有保存：%s%s。十二张卡都要有编号（先在游戏里把十二人都点上顺序）。'
                            % (WHY.get(reason, reason), ('（第 %s 张卡）' % '、'.join(map(str, unread))) if unread else ''))
    slot = team.get('saved_team')
    ledger = directory / 'user-run-ledger.json'
    active = read_json(ledger).get('active') if ledger.exists() else None
    source = 'page'
    if type(slot) is not int and active and type(active.get('team')) is int:
        slot, source = active['team'], 'run_in_progress'
    if type(slot) is not int or not 1 <= slot <= 40:
        return dict(passed=False, reason='team_order_team_number_unread', input_sent=False, numbers=list(numbers),
                    message='读到了完整的出战编号，但这一页没有显示 TEAMS #几，也没有正在进行的镜牢可以对应，'
                            '所以不知道该存给哪支队伍，没有保存。请在镜牢外的编队界面（左侧有 TEAMS 列表）运行。')
    deployment = tuple(SINNERS[position - 1] for position in order)
    names = '、'.join(team_order_record.DISPLAY[position - 1] for position in order)
    store = ProfileStore(directory / 'user-team-profiles.json')
    teams = list(store.load()) if store.path.exists() else []
    old = next((saved for saved in teams if saved.slot == slot), None)
    if old is not None and tuple(old.deployment) == deployment:
        return dict(passed=True, reason='team_order_unchanged', input_sent=False, slot=slot, order=list(deployment),
                    slot_source=source,
                    message='队伍 %d 的出战顺序与已保存的一致：%s。' % (slot, names))
    new = replace(old or Team(slot, frozenset()), deployment=deployment)
    if old is None:
        teams.append(new)
    else:
        teams[teams.index(old)] = new
    store.save(teams)
    team_order_record.record(directory, slot, numbers, frame)
    where = '（这一页没有显示队伍编号，按正在进行的这一局所用的队伍保存）' if source == 'run_in_progress' else ''
    return dict(passed=True, reason='team_order_saved', input_sent=False, slot=slot, order=list(deployment),
                slot_source=source, previous=list(old.deployment) if old is not None else [],
                message='已把队伍 %d 的出战顺序保存为：%s%s。总设置里该队伍的「出战顺序」保持「不变」即会使用它。'
                        % (slot, names, where))
