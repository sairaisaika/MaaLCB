"""Every option the interface defines can be reached, and the tools do not bring removed ones back.

On 2026-11-23 the interface defined 714 options and 22 of them could not be reached
from any task, global option, controller or the pretask: leftovers of four standalone
tasks that were consolidated away, still defined, still translated, still asserted by
tests. They were removed. This keeps the count at zero.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOVED = ([f'deployment_position_{n}' for n in range(1, 13)]
           + ['deployment_preset', 'pack_name', 'pack_weight', 'run_team', 'team_build_name', 'team_build_slot',
              'team_keywords', 'team_keywords_extra', 'team_name', 'team_slot'])


def interface():
    return json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))


def reachable(data):
    stack = [name for task in data.get('task', []) for name in task.get('option') or []]
    stack += list(data.get('global_option') or [])
    for key in ('controller', 'resource', 'pretask'):
        for item in data.get(key, []) or []:
            stack += list(item.get('option') or [])
    seen = set()
    while stack:
        name = stack.pop()
        if name in seen or name not in data['option']:
            continue
        seen.add(name)
        for case in data['option'][name].get('cases', []) or []:
            stack += list(case.get('option') or [])
    return seen


def test_no_option_is_defined_that_nothing_reaches():
    data = interface()
    unreached = sorted(set(data['option']) - reachable(data))
    assert not unreached, 'defined but offered by no task, global option, controller or pretask: %s' % unreached


def test_every_option_a_task_or_case_names_is_defined():
    data = interface()
    named = {name for task in data['task'] for name in task.get('option') or []}
    named |= {name for option in data['option'].values() for case in option.get('cases', []) or []
              for name in case.get('option') or []}
    assert not sorted(named - set(data['option']))


def test_expanding_the_team_slots_does_not_bring_a_removed_option_back():
    spec = importlib.util.spec_from_file_location('expand_team_slots', ROOT / 'tools/expand_team_slots.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = interface()
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    expanded, expanded_nodes = module.expand(json.loads(json.dumps(data)), json.loads(json.dumps(nodes)))
    assert expanded == data and expanded_nodes == nodes
    assert not [name for name in REMOVED if name in expanded['option']]


def test_the_skeleton_script_refuses_to_replace_the_maintained_interface(tmp_path):
    before = (ROOT / 'assets/interface.json').read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / 'tools/prepare_resources.py'), '--ocr', str(tmp_path)],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0 and 'maintained interface' in result.stderr
    assert (ROOT / 'assets/interface.json').read_bytes() == before
