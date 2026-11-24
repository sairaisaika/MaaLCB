"""Apply the team settings of the app's global section without performing device input.

A team has two settings, and each can be left alone on its own:

- its systems (the gift keywords the run aims for), a choice with "keep" as the default;
- its deployment order, one line of text. "keep" leaves the saved order as it is; "game"
  forgets the saved order, so the run deploys whatever order the game itself shows for
  that team; anything else is the order, written as sinner numbers or names.

Until 2026-11-23 a team took fifteen options: an edit switch, a name nothing read, the
systems and twelve dropdowns, one per deployment position, each listing all twelve
sinners (600 options for 40 teams). The dropdowns defaulted to the roster order, did not
show what was saved, and let the same sinner be chosen twice.

Only fields that are not "keep" replace saved fields. Other team data and the rotation
stay intact. The whole edit is validated before the file is replaced.
"""
from dataclasses import replace
import re

from .policies import Team
from .storage import ProfileStore, SINNERS, KEYWORDS, read_json

KEEP = 'keep'
GAME = 'game'
#: What a player may type instead of the two English words.
KEEP_WORDS = ('', 'keep', '不变', '保持', '保持不变', 'そのまま')
GAME_WORDS = ('game', '游戏', '跟随游戏', 'ゲーム')
#: The names a player may type for each sinner, besides the number and the English name.
ALIASES = {
    'Yi Sang': ('李箱', 'イサン'), 'Faust': ('浮士德', 'ファウスト'),
    'Don Quixote': ('堂吉诃德', '唐吉诃德', 'don', 'ドンキホーテ'), 'Ryoshu': ('良秀',),
    'Meursault': ('默尔索', 'ムルソー'), 'Hong Lu': ('鸿璐', 'ホンル'),
    'Heathcliff': ('希斯克利夫', 'ヒースクリフ'), 'Ishmael': ('以实玛利', 'イシュメール'),
    'Rodion': ('罗佳', 'rodya', 'ロージャ'), 'Sinclair': ('辛克莱', 'シンクレア'),
    'Outis': ('奥提斯', 'ウーティス'), 'Gregor': ('格里高尔', 'グレゴール'),
}


def _names():
    table = {}
    for number, sinner in enumerate(SINNERS, 1):
        for word in (str(number), sinner.replace(' ', ''), *ALIASES[sinner]):
            table[word.casefold()] = sinner
    return table


def parse_order(text):
    """Read the one-line deployment order: KEEP, GAME, or a tuple of all twelve sinners.

    Sinners are written as their roster number (1 Yi Sang ... 12 Gregor) or their name,
    separated by spaces, commas or arrows. A line may name only the first few; the
    sinners it does not name follow in roster order. A word that is not a sinner, or a
    sinner named twice, is refused by name.
    """
    if not isinstance(text, str):
        raise ValueError('The deployment order must be a line of text')
    plain = text.strip()
    if plain.casefold() in KEEP_WORDS:
        return KEEP
    if plain.casefold() in GAME_WORDS:
        return GAME
    table = _names()
    # Two-word English names are joined before the line is split into words.
    line = plain.casefold()
    for sinner in SINNERS:
        if ' ' in sinner:
            line = line.replace(sinner.casefold(), sinner.replace(' ', '').casefold())
    order = []
    for word in (word for word in re.split(r'[\s,，、;；>→\-]+', line) if word):
        sinner = table.get(word)
        if sinner is None:
            raise ValueError('"%s" is not a sinner: write numbers 1-12 or names' % word)
        if sinner in order:
            raise ValueError('%s is named twice in the deployment order' % sinner)
        order.append(sinner)
    if not order:
        raise ValueError('The deployment order names no sinner')
    return tuple(order) + tuple(sinner for sinner in SINNERS if sinner not in order)


def collect_builds(get_node):
    """Read each team's two nodes; a team with both left at "keep" is not an edit."""
    result = {}
    for slot in range(1, 41):
        prefix = f'Global_global_team_{slot}'
        keywords = get_node(prefix + '_systems')['attach']['global_build']['keywords']
        order = get_node(prefix + '_order')['attach']['global_build']['order']
        if keywords == KEEP and isinstance(order, str) and order.strip().casefold() in KEEP_WORDS:
            continue
        result[str(slot)] = dict(keywords=keywords, order=order)
    return result


def apply_builds(directory, edits):
    if not isinstance(edits, dict):
        raise ValueError('Global build edits must be an object')
    store = ProfileStore(directory / 'user-team-profiles.json')
    teams = list(store.load()) if store.path.exists() else []
    changed = []
    ledger = directory / 'user-run-ledger.json'
    active = read_json(ledger).get('active') if ledger.exists() else None
    for key, edit in edits.items():
        if not isinstance(key, str) or not key.isdecimal() or not 1 <= int(key) <= 40:
            raise ValueError('Unknown global build slot')
        if not isinstance(edit, dict) or set(edit) != {'keywords', 'order'}:
            raise ValueError('A team edit names its systems and its deployment order')
        slot = int(key)
        old = next((t for t in teams if t.slot == slot), None)
        keywords, order = edit['keywords'], parse_order(edit['order'])
        fields = {}
        if keywords != KEEP:
            if (not isinstance(keywords, list) or not keywords or
                    len(set(keywords)) != len(keywords) or not set(keywords) <= set(KEYWORDS)):
                raise ValueError('Choose known, distinct team systems')
            fields['keywords'] = frozenset(keywords)
        elif old is None:
            raise ValueError('Team %d is not saved yet: choose its systems first' % slot)
        if order == GAME:
            fields['deployment'] = ()
        elif order != KEEP:
            fields['deployment'] = order
        new = replace(old or Team(slot, frozenset()), **fields)
        if active and active.get('team') == slot and old != new:
            raise ValueError('Finish the active run before editing its team')
        if old != new:
            if old is None:
                teams.append(new)
            else:
                teams[teams.index(old)] = new
            changed.append(slot)
    if changed:
        store.save(teams)
    return changed
