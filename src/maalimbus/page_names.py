"""What the program says in the task log about the screen it recognised.

The journal (`events.jsonl`) has always held every page the loop read, but the log a
person watches in the app showed a line only when an input was sent on a new page, and
for most pages it printed the internal identifier. A user watching a task could not see
that the program was recognising each screen (reported 2026-11-23). This module gives
every registered page a name a player would use and decides when a step is worth a line.

Nothing here reads a frame or decides anything about the game.
"""
from __future__ import annotations

#: Page identifier -> the name a player would use. Every page in `pages.PAGES` has one
#: (`tests/test_page_names.py`).
NAMES = {
    'TITLE': '标题画面', 'HOME': '大厅', 'DRIVE': '驾驶席（副本列表）', 'MIRROR_ENTRY': '镜牢入口',
    'ENTRY_CONFIRM': '进入镜牢的确认', 'RESUME_DIALOG': '继续旧局的询问', 'EXPIRED_SESSION': '旧局已过期的提示',
    'WINDOW_RESET': '每周重置的提示', 'RESOURCE_DIALOG': '资源下载提示', 'TUTORIAL': '教学提示',
    'LOADING': '加载中', 'CUTSCENE': '过场剧情', 'UNKNOWN': '未识别的画面', 'UNKNOWN_DIALOG': '未识别的弹窗',
    'STAR_GRACES': '星光增益选择', 'STAR_CONFIRM': '星光增益确认', 'INITIAL_GIFTS': '初始藏品选择',
    'GIFT_SEARCH': '藏品搜索', 'GIFT_SEARCH_FORGO': '放弃藏品搜索的确认', 'GIFT_WARNING': '藏品提示',
    'TEAM_LIBRARY': '编队列表', 'DUNGEON_TEAM': '镜牢编队选择', 'DEPLOYMENT': '出战安排',
    'DEPLOYMENT_RESET': '重置出战安排的确认', 'PRE_BATTLE_TEAM': '战前编队（出战顺序）',
    'THEME_PACKS': '主题包选择（下一层）', 'MAP': '地图', 'NODE_PANEL': '节点详情', 'NODE_PREVIEW': '节点预览',
    'DUNGEON_PROGRESS': '镜牢进度面板', 'LEVEL_WARNING': '等级提示',
    'BATTLE_HUD': '战斗中', 'BATTLE_PLANNING': '战斗配卡', 'BATTLE_TIP': '战斗提示', 'BATTLE_RESULT': '战斗结算',
    'BATTLE_VICTORY': '战斗胜利', 'BATTLE_DEFEAT': '战斗失败', 'DEFEAT': '镜牢失败',
    'REWARD_CARD': '战后奖励卡选择', 'REWARD_SETTLE': '战后奖励结算', 'EGO_GIFT_POPUP': '获得藏品的弹窗',
    'FLOOR_GIFTS': '楼层藏品选择', 'GIFT_PICK': '藏品选择', 'GIFT_GET': '藏品到账',
    'EVENT_DIALOG': '事件对话', 'EVENT_CHOICE': '事件选项', 'EVENT_CHECK': '事件判定',
    'EVENT_CHECK_READY': '事件判定准备', 'EVENT_CHECK_RESULT': '事件判定结果', 'EVENT_RESULT': '事件结果',
    'EVENT_RESULT_READY': '事件结果（可继续）',
    'SHOP': '商店', 'SHOP_PURCHASE': '商店购买确认', 'SHOP_LEAVE': '离开商店的确认',
    'HEAL_SINNERS': '治疗罪人', 'REVIVE_PICK': '选择复活的罪人', 'REVIVE_DONE': '复活完成',
    'EXPLORATION_COMPLETE': '探索完成', 'RUN_CLAIM': '通关结算', 'RUN_REWARD_DIALOG': '通关奖励（领取／放弃）',
    'RUN_REWARD_CONFIRM': '领取奖励的确认', 'RUN_REWARD_BONUS': '使用每周加成的确认', 'PASS_LEVEL_UP': '通行证升级',
}
#: A page the loop keeps waiting on gets another line every this many steps, with the count.
REPEAT_EVERY = 10


def name(page):
    """The player's name for a page, with the identifier kept for looking it up."""
    if not page:
        return '未识别的画面'
    label = NAMES.get(page)
    return '%s（%s）' % (label, page) if label else str(page)


def step_line(memory, step, page, *, input_sent=False, waiting=False, stopped=None):
    """The log line for one finished step, or None when it would only repeat the last one.

    `memory` is a dict the caller keeps for one task. A line is written when the page
    changes, when an input was sent, when the step stopped the task, and every
    `REPEAT_EVERY` steps while the program keeps looking at the same page.
    """
    same = memory.get('page') == page
    count = memory.get('count', 0) + 1 if same else 1
    memory.update(page=page, count=count)
    if stopped:
        what = '在此停止'
    elif input_sent:
        what = '已操作'
    elif waiting:
        what = '观察等待'
    else:
        what = '已识别'
    if same and not input_sent and not stopped and count % REPEAT_EVERY:
        return None
    line = '第 %s 步 · 画面：%s · %s' % (step, name(page), what)
    if same and count > 1 and not input_sent and not stopped:
        line += '（同一画面已连续 %d 步）' % count
    return line
