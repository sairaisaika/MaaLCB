"""A new module gets an owner route in the Wiki; the ones without one are listed, and the list only shrinks.

On 2026-11-23 the routes of ``docs/wiki/routes.json`` named 89 of 157 modules; 68 had
none, and nothing would have said so if the next new module joined them. A route is what
takes a question or an error text to the code that owns it (``python tools/wiki_route.py``).
This is not an approval step. It fails only when a module is added without a route,
naming the module, and when a listed module has since been routed or removed, so the
list stays true.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Modules that had no owner route when this check was added. Do not add to it: give a
#: new module a route in docs/wiki/routes.json instead (an existing route's ``sources``
#: is enough). Remove a name once its module is routed.
UNROUTED = frozenset((
    'adb_input', 'adb_preflight', 'agent_probe', 'anchor', 'auto_formation',
    'battle_counter_native', 'budget', 'build_fingerprint', 'click_space', 'click_trace',
    'crash_codes', 'deployment', 'deployment_availability_native', 'deployment_identity_native',
    'deployment_numbers_native', 'event_log', 'event_vision', 'evidence_audit',
    'floor_trial_vision', 'gift_plan', 'github_cache', 'gui_preferences',
    'identity_catalog', 'initial_transaction', 'input_helpers', 'lix_profiles', 'lux_task',
    'map_progress', 'mirror_assessment', 'mirror_learning_policy', 'mirror_preferences',
    'mxu_distribution', 'overlay_dismissal', 'overlay_vision', 'owned_inventory', 'page_carry',
    'policies', 'reason_kinds', 'reason_provenance', 'releases', 'reward_claim_transaction',
    'reward_vision', 'route_plan', 'run_record',
    'run_summary', 'runtime_paths', 'screen_state', 'shop_learning',
    'shop_native', 'shop_priority', 'shop_revive', 'shop_settings', 'shop_skill_policy',
    'shop_skill_vision', 'sinner_collection', 'sinner_detection', 'startup_update', 'stillness',
    'team_gift_keyword', 'team_navigation', 'update_stage', 'windows_controller',
    'windows_preflight',
))


def routed():
    routes = json.loads((ROOT / 'docs/wiki/routes.json').read_text(encoding='utf-8'))['routes']
    return {item['path'] for row in routes for item in (row.get('sources') or [])
            if isinstance(item, dict) and item.get('path')}


def modules():
    return {path.stem: 'src/maalimbus/' + path.name
            for path in (ROOT / 'src/maalimbus').glob('*.py') if path.name != '__init__.py'}


def test_a_new_module_has_an_owner_route():
    owned = routed()
    missing = sorted(name for name, path in modules().items() if path not in owned and name not in UNROUTED)
    assert not missing, ('no Wiki route names these modules; add each to the sources of the route that '
                         'owns it in docs/wiki/routes.json: %s' % missing)


def test_the_unrouted_list_only_shrinks():
    owned, present = routed(), modules()
    stale = sorted(name for name in UNROUTED if name not in present or present[name] in owned)
    assert not stale, 'routed or removed since, take them off UNROUTED: %s' % stale
    assert len(UNROUTED) <= 68
