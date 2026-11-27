"""Which graces a Mirror run buys, at which level, and what it may spend on them.

The Graces page ("Grace of the Sisyphean Star") offers ten cards. Each has three levels:
plain, ``+`` and ``++``, at one, two and three times the card's base cost. A run has an
allowance of starlight for the page; past it the game takes the difference from the
player's stock of owned starlight, and any allowance left over becomes starting Cost.
The game remembers none of this: the page opens empty at every run.

So a plan is three things: which cards, each card's level, and how much may be taken
from the stock (nothing, unless the player says so). A plan belongs either to a saved
team, set with the team in the global settings, or to the Mirror task. The task chooses
which is used: the team's (and the task's own for a team that has none), or the task's.

Until 2026-11-27 a plan was plain cards and a total budget, enhancement was refused
outright, and the task offered two more sources: "saved", which read a file nothing in
the settings wrote, and "auto". The user, looking at the page: the two levels are the
point of the page, the game keeps no selection to "follow", and choosing a plan must not
take more presses here than on the page itself. Hence the presets (everything, at each
level) and one tick per card per level.
"""
from .storage import ProfileStore, read_json, write_json

SOURCES = ('team', 'task')
#: The plan choices a settings dropdown offers besides ticking cards one by one.
PRESETS = {'none': {}, 'all': {card: 0 for card in range(10)}, 'all_plus': {card: 1 for card in range(10)},
           'all_plusplus': {card: 2 for card in range(10)}}
#: "As much of the stock as the plan needs": more than ten cards at ``++`` can ever cost.
STOCK_ALL = 1000000
#: The total a new plan may spend. The allowance and the stock limit are what bound it;
#: the old explicit total stays readable for plans saved before 2026-11-27.
BUDGET = 1000000


def plan(value):
    """Validate a plan: ``dict(levels={card: level}, stock=int)``, cards 0..9, levels 0..2.

    An older plan is ``dict(choices=[cards], budget=int)``; its cards are plain and its
    budget is kept. Returns ``dict(choices, levels, budget, stock)`` with cards in order.
    """
    if not isinstance(value, dict):
        raise ValueError('A star plan is an object')
    levels = value.get('levels')
    if levels is None:
        choices = value.get('choices')
        if (not isinstance(choices, list) or len(choices) > 10 or len(set(choices)) != len(choices)
                or any(type(n) is not int or not 0 <= n <= 9 for n in choices)):
            raise ValueError('Star choices must be distinct Lix zero-based indexes 0..9')
        levels = {card: 0 for card in choices}
    if not isinstance(levels, dict):
        raise ValueError('Star levels map a card to its level')
    clean = {}
    for card, level in levels.items():
        card = int(card) if isinstance(card, str) and card.isdecimal() else card
        if type(card) is not int or not 0 <= card <= 9 or type(level) is not int or not 0 <= level <= 2:
            raise ValueError('Star cards are 0..9 and levels 0 (plain), 1 (+) or 2 (++)')
        clean[card] = level
    budget = value.get('budget', BUDGET)
    stock = value.get('stock', 0)
    if type(budget) is not int or not 0 <= budget <= 1000000:
        raise ValueError('Explicit starlight budget required')
    if type(stock) is not int or not 0 <= stock <= STOCK_ALL:
        raise ValueError('The starlight taken from the stock is 0..1000000')
    ordered = dict(sorted(clean.items()))
    return dict(choices=list(ordered), levels=ordered, budget=budget, stock=stock)


def notation(value):
    """A plan's cards as a team stores them: ``'0'``, ``'4+'``, ``'5++'``."""
    return tuple('%d%s' % (card, '+' * level) for card, level in plan(value)['levels'].items())


def from_team(team):
    """The plan a saved team carries, or None when none was ever set for it."""
    if team is None or team.grace_budget is None:
        return None
    return plan(dict(levels={int(grace[0]): len(grace) - 1 for grace in team.graces},
                     budget=team.grace_budget, stock=team.grace_stock))


def from_nodes(get_node, names):
    """Read a plan from its option nodes; `names` gives the node of each part.

    ``plan``: the dropdown (a preset, or ``custom``); ``base``, ``plus``, ``plusplus``:
    one row of ticks per level, each tick an attach key ``star_<card>``; ``spend`` and
    ``cap``: what may be taken from the stock. A card ticked in two rows takes the higher
    level: ticking ``++`` is what the player did last in their head.
    """
    mode = get_node(names['plan'])['attach'].get('mode')
    if mode in PRESETS:
        levels = dict(PRESETS[mode])
    elif mode == 'custom':
        levels = {}
        for level, part in enumerate(('base', 'plus', 'plusplus')):
            ticked = get_node(names[part]).get('attach') or {}
            for key, on in ticked.items():
                if key.startswith('star_') and key[5:].isdecimal() and on is True and 0 <= int(key[5:]) <= 9:
                    levels[int(key[5:])] = max(level, levels.get(int(key[5:]), 0))
    else:
        raise ValueError('Unknown star plan choice')
    spend = get_node(names['spend'])['attach'].get('mode', 'allowance')
    if spend == 'allowance':
        stock = 0
    elif spend == 'stock_all':
        stock = STOCK_ALL
    elif spend == 'stock_cap':
        cap = get_node(names['cap'])['attach'].get('cap', '0')
        if not isinstance(cap, str) or not cap.isdecimal() or len(cap) > 7:
            raise ValueError('The starlight taken from the stock must be decimal digits')
        stock = min(int(cap), STOCK_ALL)
    else:
        raise ValueError('Unknown star spending choice')
    return plan(dict(levels=levels, stock=stock))


TASK_NODES = dict(plan='MirrorTaskStarPlan', base='MirrorTaskStarBase', plus='MirrorTaskStarPlus',
                  plusplus='MirrorTaskStarPlusPlus', spend='MirrorTaskStarSpend', cap='MirrorTaskStarCap')


def team_nodes(slot):
    prefix = 'Global_global_team_%d_star' % slot
    return dict(plan=prefix + 's', base=prefix + '_base', plus=prefix + '_plus', plusplus=prefix + '_plusplus',
                spend=prefix + '_spend', cap=prefix + '_cap')


def collect(get_node):
    """``(source, task plan)`` from the Mirror task's options.

    A pipeline or a saved choice from before 2026-11-27 may still say ``saved`` or
    ``auto``; both mean what the default means now, the team's plan.
    """
    source = get_node('MirrorStarSource')['attach'].get('source')
    if source in ('saved', 'auto'):
        source = 'team'
    if source not in SOURCES:
        raise ValueError('Unknown star rule source')
    try:
        task = from_nodes(get_node, TASK_NODES)
    except KeyError:
        task = plan(dict(levels={}))     # a pipeline packaged before the task plan had these nodes
    return source, task


def apply(directory, source, task_plan):
    """Save the task's choice of source and its own plan; no controller input here."""
    if source not in SOURCES:
        raise ValueError('Unknown star rule source')
    setting = dict(version=2, source=source, task=plan(task_plan))
    write_json(directory / 'user-mirror-starlight.json', setting)
    return setting


def resolve(directory, slot):
    """What the run that uses team `slot` buys, as the loop's settings; None without a rule file."""
    path = directory / 'user-mirror-starlight.json'
    if not path.exists():
        return None
    settings = read_json(path)
    if settings.get('version') not in (1, 2):
        raise ValueError('Unknown star rule version')
    source = settings['source']
    if source == 'auto':
        source = 'team'
    if source not in SOURCES:
        raise ValueError('Unknown star rule source')
    selected = plan(settings['task'])
    used = 'task'
    if source == 'team':
        profiles = ProfileStore(directory / 'user-team-profiles.json')
        team = next((t for t in profiles.load() if t.slot == slot), None) if profiles.path.exists() else None
        own = from_team(team)
        if own is not None:
            selected, used = own, 'team'
    return dict(graces=','.join(str(card + 1) for card in selected['choices']),
                grace_levels=','.join('%d:%d' % (card + 1, level) for card, level in selected['levels'].items()),
                grace_budget=selected['budget'], grace_stock=selected['stock'], grace_auto=False,
                star_source=source, plan_of=used, team=slot)


def affordable(priorities, budget, available, costs):
    if len(priorities) > 10 or len(set(priorities)) != len(priorities):
        raise ValueError('Distinct auto priorities required')
    if type(available) is not int or available < 0:
        raise ValueError('Current available starlight required')
    if type(budget) is not int or budget < 0:
        raise ValueError('Current budget required')
    limit = min(budget, available)
    result = []
    spent = 0
    for n in priorities:
        if type(n) is not int or not 1 <= n <= 10 or n in result:
            raise ValueError('Invalid auto priority')
        cost = costs[n - 1]
        if type(cost) is not int or cost <= 0:
            raise ValueError('Every candidate needs a current visible cost')
        if spent + cost <= limit:
            result.append(n)
            spent += cost
    return result
