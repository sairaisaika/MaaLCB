"""Apply the Mirror team settings of the app's global section without performing device input.

These settings say how a team is used in the Mirror Dungeon; they are not the team itself,
which the game owns. A team has two, and each can be left alone on its own:

- its gift systems: "keep", or a fresh choice of any number of systems by ticking them.
  None ticked is a choice too: the team is tied to no system and the run buys by its
  own scoring. (The first version offered fixed combinations such as "Charge+Tremor";
  the user asked for free ticking on 2026-11-23.)
- its deployment order: "keep"; "game", which forgets the saved order so the run deploys
  whatever order the game itself shows for that team (the run records the order it read,
  with its screenshot: `team_order_record`); or "custom", the whole order written as
  sinner numbers or names. A version that ticked "who deploys first" was dropped the
  day it was made: ticking cannot say an order.

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
    """Read each team's option nodes; a team with both settings left at "keep" is not an edit.

    Ticked systems arrive as one attach key each (`kw_<System>`): the framework merges the
    attach keys of every ticked case onto the node.
    """
    result = {}
    for slot in range(1, 41):
        prefix = f'Global_global_team_{slot}'
        systems = get_node(prefix + '_systems')['attach'].get('mode', KEEP)
        order = get_node(prefix + '_order')['attach'].get('mode', KEEP)
        try:
            stars = get_node(prefix + '_stars')['attach'].get('mode', KEEP)
        except KeyError:
            stars = KEEP    # a pipeline packaged before the team's starlight setting existed
        if systems not in (KEEP, 'choose') or order not in (KEEP, GAME, 'custom') or stars not in (KEEP, 'choose'):
            raise ValueError('Unknown Mirror team setting')
        if systems == KEEP and order == KEEP and stars == KEEP:
            continue
        keywords = KEEP
        if systems == 'choose':
            ticked = get_node(prefix + '_keywords').get('attach') or {}
            keywords = sorted(key[3:] for key, on in ticked.items() if key.startswith('kw_') and on is True)
        if order == 'custom':
            order = get_node(prefix + '_order_text')['attach'].get('order', '')
            if not isinstance(order, str) or not order.strip():
                raise ValueError('Write the deployment order, or choose another way to set it')
        result[str(slot)] = dict(keywords=keywords, order=order)
        if stars == 'choose':
            # The team's own starlight plan: which of the ten cards (Lix zero-based, one
            # attach key per ticked card) and the most starlight it may spend.
            ticked = get_node(prefix + '_star_cards').get('attach') or {}
            budget = get_node(prefix + '_star_budget')['attach'].get('budget', '0')
            if not isinstance(budget, str) or not budget.isdecimal() or len(budget) > 7:
                raise ValueError('Star budget must be decimal digits')
            result[str(slot)]['stars'] = dict(
                choices=sorted(int(key[5:]) for key, on in ticked.items()
                               if key.startswith('star_') and key[5:].isdecimal() and on is True),
                budget=int(budget))
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
        if not isinstance(edit, dict) or set(edit) - {'stars'} != {'keywords', 'order'}:
            raise ValueError('A team edit names its systems and its deployment order')
        slot = int(key)
        old = next((t for t in teams if t.slot == slot), None)
        keywords, order = edit['keywords'], parse_order(edit['order'])
        fields = {}
        if keywords != KEEP:
            # An empty choice is allowed: the team is tied to no system.
            if (not isinstance(keywords, list) or
                    len(set(keywords)) != len(keywords) or not set(keywords) <= set(KEYWORDS)):
                raise ValueError('Choose known, distinct team systems')
            # The run reads `formation_keywords` before `keywords` for the starting gift, so a
            # choice made here sets both: an imported value must not outrank what was ticked.
            fields['keywords'] = fields['formation_keywords'] = frozenset(keywords)
        if order == GAME:
            fields['deployment'] = ()
        elif order != KEEP:
            fields['deployment'] = order
        if 'stars' in edit:
            from .mirror_starlight import plan
            stars = plan(edit['stars'])
            fields['graces'] = tuple(str(card) for card in stars['choices'])
            fields['grace_budget'] = stars['budget']
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
