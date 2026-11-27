"""What deployment order the game showed for a team, written down with its screenshot.

A team's order can simply follow the game: the player arranges it on the game's own team
screen, which is the natural twelve-portrait picker, and the run deploys what is there.
The settings cannot show that order back (the app does not load saved state into its
fields), so the run records what it read: the order, when, and the frame it was read
from. The record is what a player checks ("did it use the order I set?") and the frame
is kept because the record names it.

The order is read from the numbers printed on the twelve cards (`team_order`), never
guessed. Nothing here sends input or decides anything.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage import SINNERS, read_json, write_json
from .team_order import order_from_badges

NAME = 'user-team-order-records.json'
#: Display names for the log line, in roster order.
DISPLAY = ('李箱', '浮士德', '堂吉诃德', '良秀', '默尔索', '鸿璐', '希斯克利夫', '以实玛利', '罗佳', '辛克莱', '奥提斯', '格里高尔')


def record(directory, slot, badges, frame, *, now=None):
    """Save the order the team page shows for `slot`; return the record, or None if unreadable.

    `badges[i]` is the number printed on card `i`. An incomplete or contradictory set of
    numbers is not an order and nothing is written.
    """
    order, _reason = order_from_badges(badges or ())
    if order is None or type(slot) is not int:
        return None
    now = now or datetime.now(timezone.utc)
    entry = dict(order=[SINNERS[position - 1] for position in order], positions=list(order),
                 frame=str(frame) if frame else None, at=now.astimezone(timezone.utc).isoformat())
    path = Path(directory) / NAME
    data = read_json(path) if path.exists() else {}
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('teams'), dict):
        data = dict(version=1, teams={})
    previous = data['teams'].get(str(slot)) or {}
    # The same order again only refreshes nothing: the first frame it was seen on stays the record.
    if previous.get('positions') == entry['positions']:
        return dict(previous, changed=False)
    data['teams'][str(slot)] = entry
    write_json(path, data)
    return dict(entry, changed=True)


def line(slot, entry):
    """The task-log line for a recorded order."""
    names = '、'.join(DISPLAY[position - 1] for position in entry['positions'])
    frame = Path(entry['frame']).stem if entry.get('frame') else '无'
    return '镜牢队伍 %s 的出战顺序跟随游戏：%s（已记录，截图 %s）' % (slot, names, frame)
