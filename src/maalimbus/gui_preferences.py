"""Read the choices a player made in the GUI, so a driver runs the same task.

The driver used to start `MirrorTask` with its own defaults while the GUI held the
player's real choices (team 2, Charge+Tremor, gift search on).  That produced runs
whose team and build were not the configured ones -- a second source of truth for
"which team and which build", which is exactly the class of defect that makes a
run look like a game problem when it is a configuration problem.

This module only *reads*: it never invents a keyword and never changes a setting.
A missing field stays missing (`None`), so a caller can tell "not configured" from
"configured to the default".
"""
import json
from pathlib import Path

DEFAULT = Path('dist/MaaLimbus/config/mxu-MaaLimbus.json')
FIELDS = ('mirror_team_mode', 'mirror_single_team', 'mirror_initial_keyword',
          'mirror_gift_search', 'mirror_run_count')


def _cases(value):
    return value.get('caseName') if isinstance(value, dict) else None


#: The interface's name for the Mirror task.
MIRROR_TASK = 'mirror_loop'


def _task_values(config, task=MIRROR_TASK):
    """The saved option values of `task` in the first instance, or `{}`.

    The task list is the player's: it starts with whatever they put first. Since the
    emulator pretask and "open game" were added, the Mirror task is the third entry, and
    reading "the first task" returned an empty answer for every field (found
    2026-11-26, when a run without the interface would have kept 500 coins back in
    every shop). The task is found by its name; a list written before tasks carried
    names is still read by its first entry that holds any Mirror field.
    """
    instances = config.get('instances') or []
    tasks = (instances[0].get('tasks') or []) if instances else []
    named = [row for row in tasks if isinstance(row, dict) and row.get('taskName') == task]
    if named:
        return named[0].get('optionValues') or {}
    for row in tasks:
        values = row.get('optionValues') if isinstance(row, dict) else None
        if isinstance(values, dict) and any(field in values for field in FIELDS) and 'taskName' not in row:
            return values
    return {}


def task_override(config_path=DEFAULT, interface_path=None, task=MIRROR_TASK):
    """The pipeline override the interface would send for the task's saved choices.

    Returns ``(override, chosen)``: the merged node patches, and ``(option, case, source)``
    rows saying whether each case was saved by the player or is the interface's default.
    The rule is the interface's own (`interface.json`): every option of the task
    contributes its chosen case's ``pipeline_override``, and so does every option
    nested under a chosen case. What this cannot replay it refuses by name: an option
    that is not a plain choice, a case the interface does not have, or two choices
    patching the same node. A partly replayed configuration would be a run that looks
    configured and is not.
    """
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    interface = json.loads(Path(interface_path).read_text(encoding='utf-8'))
    values = _task_values(config, task)
    entry = next((row for row in interface.get('task') or [] if row.get('name') == task), None)
    if entry is None:
        raise ValueError('The interface has no task named %r' % task)
    override, chosen = {}, []

    def take(name):
        option = (interface.get('option') or {}).get(name)
        if option is None:
            raise ValueError('The interface has no option named %r' % name)
        if option.get('type') != 'select':
            raise ValueError('Option %r is %r, which cannot be replayed' % (name, option.get('type')))
        saved = values.get(name)
        case_name = _cases(saved) if saved is not None else option.get('default_case')
        case = next((row for row in option.get('cases') or [] if row.get('name') == case_name), None)
        if case is None:
            raise ValueError('Option %r has no case %r' % (name, case_name))
        chosen.append((name, case_name, 'saved' if saved is not None else 'default'))
        for node, node_patch in (case.get('pipeline_override') or {}).items():
            if node in override:
                raise ValueError('Two choices patch the node %r' % node)
            override[node] = node_patch
        for nested in case.get('option') or []:
            take(nested)

    for name in entry.get('option') or []:
        take(name)
    return override, chosen


def read(path=DEFAULT):
    """Return the run preferences the GUI persisted, or `{}` when unreadable."""
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    instances = config.get('instances') or []
    if not instances:
        return {}
    options = _task_values(config)
    out = {field: _cases(options.get(field)) for field in FIELDS}
    team = out.get('mirror_single_team')
    if isinstance(team, str) and team.isdigit():
        out['mirror_single_team'] = int(team)
    elif not isinstance(team, int):
        out['mirror_single_team'] = None
    team_number = out.get('mirror_single_team')
    globals_ = config.get('globalOptionValues') or {}
    if team_number:
        systems = globals_.get(f'global_team_{team_number}_systems') or {}
        ticked = globals_.get(f'global_team_{team_number}_keywords') or {}
        chosen = systems.get('caseName') if isinstance(systems, dict) else None
        names = ticked.get('caseNames') if isinstance(ticked, dict) else None
        # "keep" is not a system: the team's saved systems apply, which this file does not hold.
        out['team_systems'] = ('+'.join(sorted(names)) if chosen == 'choose' and isinstance(names, list)
                               and all(isinstance(name, str) for name in names) else None)
    else:
        out['team_systems'] = None
    return out


def describe(prefs):
    """One line for a run's evidence, so a run states what it was told to do."""
    if not prefs:
        return 'no_gui_preferences'
    team = prefs.get('mirror_single_team')
    if team:
        return f'team {team} ({prefs.get("team_systems") or "systems unknown"})'
    return f'team mode {prefs.get("mirror_team_mode") or "unknown"}'
