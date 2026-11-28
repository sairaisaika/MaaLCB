"""Every option the interface defines can be reached, and the tools do not bring removed ones back.

On 2026-11-23 the interface defined 714 options and 22 of them could not be reached
from any task, global option, controller or the pretask: leftovers of four standalone
tasks that were consolidated away, still defined, still translated, still asserted by
tests. They were removed. This keeps the count at zero.
"""
import importlib.util
import json
from pathlib import Path

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


def test_the_skeleton_script_that_could_replace_the_interface_is_gone():
    # `tools/prepare_resources.py` wrote the early five-task interface, its pipeline and three
    # short locale files; since 2026-11-23 it refused to run over the maintained interface.
    # Every file it wrote is now maintained by hand, so it was removed on 2026-11-27.
    assert not (ROOT / 'tools/prepare_resources.py').exists()


def test_every_text_key_is_used_and_every_used_key_has_every_language():
    """On 2026-11-23 each language file held 47 keys no label or description referenced."""
    import re
    used = set(re.findall(r'"\$([A-Za-z0-9_]+)"', (ROOT / 'assets/interface.json').read_text(encoding='utf-8')))
    files = sorted((ROOT / 'assets/i18n').glob('*.json'))
    assert len(files) >= 3
    for path in files:
        keys = set(json.loads(path.read_text(encoding='utf-8')))
        assert not sorted(keys - used), '%s has text no label uses: %s' % (path.name, sorted(keys - used))
        assert not sorted(used - keys), '%s lacks text for: %s' % (path.name, sorted(used - keys))


def test_the_interface_does_not_offer_what_the_program_cannot_do():
    """An independent audit on 2026-11-23 compared every entry's promise with its code.

    Five entries did nothing a user would call a function: the update switch (the updater
    runs only from a launcher nobody is told to start, and only for stable releases), the
    skill replacement check (open, select, cancel; never a purchase), the stamina task (one
    screenshot, then "not implemented"), the gift search choice (both cases refuse) and the
    shop's "learned" mode (no model, no samples: the manual rules under another name).
    They left the interface; this keeps them out until there is something behind them.
    The skill replacement came back on 2026-11-27 with its Confirm and receipt
    (shop_transaction.reserve_skill_confirm, reconcile_skill_replacement).
    """
    data = interface()
    for option in ('software_auto_update', 'mirror_gift_search'):
        assert option not in data['option'] and option not in data['global_option']
    assert 'stamina' not in [task['name'] for task in data['task']]
    assert [case['name'] for case in data['option']['mirror_shop_policy']['cases']] == ['saved', 'manual']
    assert not [section for section in data['setting'] if section['name'] == 'software_update']
    # What stays but is not finished says so in its own label.
    labels = json.loads((ROOT / 'assets/i18n/zh_cn.json').read_text(encoding='utf-8'))
    for key in ('main_experience', 'main_thread'):
        assert '开发中' in labels[key]
    for key in ('windows_window', 'windows_background', 'windows_front'):
        assert '未验收' in labels[key] and '推荐' not in labels[key]
    assert next(r for r in data['resource'] if r['name'] == 'jp')['label'].endswith('(experimental)')

