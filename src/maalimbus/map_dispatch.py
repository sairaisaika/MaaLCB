"""What "being on the map" means, and what the MAP branch must record after a click.

The runner grew 22 inline ``page == 'MAP'`` tests.  They are not the same kind of
test: some ask *is this the map* (a naming question), some decide *did the click
land* (a contract question).  Mixing them is how a page ends up with special-case
code in three files.

This module owns the naming question so the branches stop repeating it, and it
owns navigation bookkeeping under that same action contract:

* a named expected panel, preview or room answers the navigation probe, even
  when the party has not moved yet. Allowed unreadable waiting does not.
"""
from __future__ import annotations
from . import pages
from .runtime_contracts import TransitionVerdict

MAP_PAGE = 'MAP'
NODE_PANEL_PAGE = 'NODE_PANEL'


# Compatibility import for existing map callers. The shared record owns the
# vocabulary; this module remains the sole owner of map successor criteria.
MapTransition = TransitionVerdict


def node_transition(page, expected=None):
    """Judge a navigation result, separately from whether the loop may continue.

    UNKNOWN in a plan's allowed wait pages permits observation, not a positive
    learning label. Legacy in-memory intents derive their expectation from the
    same pure planner; there is no second successor table to maintain here.
    """
    if expected is None:
        from .window import plan_step
        expected = plan_step(MAP_PAGE, candidates=[[0, 0, 1, 1]])['expect']
    expected = tuple(expected)
    if not page or pages.is_unreadable(page) or pages.is_loading(page) or page == 'TUTORIAL':
        return MapTransition('unjudged', page, expected, 'successor_not_independently_visible')
    if is_map(page):
        return MapTransition('rejected', page, expected, 'fresh_map_after_prior_settle')
    if page in expected:
        return MapTransition('accepted', page, expected, 'named_expected_successor')
    return MapTransition('unjudged', page, expected, 'successor_not_in_action_contract')


def is_map(page: str | None) -> bool:
    """True when the classifier says the frame is the dungeon map."""
    return page == MAP_PAGE


def is_progress_action(plan):
    """The bound MAP progress control, independent of diagnostic reason prose."""
    return (is_map(plan.get('page')) and plan.get('action') == 'click'
            and plan.get('target_role') == 'page_control'
            and plan.get('control_id') == 'map.progress_button')


def is_node_action(plan):
    """Node reach and navigation bookkeeping apply to destinations, not chrome.

    Legacy MAP click proposals remain node actions. Only the explicitly bound
    progress control currently has a migrated page-control role; an arbitrary
    role string cannot bypass node reach or reinterpret an unresolved target.
    """
    if not is_map(plan.get('page')) or plan.get('action') != 'click':
        return False
    return not is_progress_action(plan)


def resume_return_has_untried_path(state, record, candidates):
    """The first named MAP after a recovery can spend a fresh supported node.

    Keep the already-used recovery ticket. A second three-refusal streak still
    ends the episode, and the remembered destinations stay excluded.
    """
    if not is_map(record.get('scene')) or not state.pop('map_resume_return_pending', False):
        return False
    supported = {tuple(box) for box in record.get('map_gold_path_supported') or ()}
    if not any(tuple(box.get('box') if isinstance(box, dict) else box) in supported
               for box in candidates or ()):
        return False
    state['map_refused_streak'] = 0
    return True


def can_probe_header_only(page):
    """A missing map name may use its header; a named foreground owns its pixels.

    A modal can leave the floor caption readable behind it. That is not evidence
    that map destinations, or arbitrary bright modal controls, are clickable.
    """
    return pages.is_unreadable(page)


def resume_navigation_requested(state, active, run_id):
    """A current unfinished entered run can resume from an already open panel.

    This restores only the navigation goal after a capture-session restart. It
    never enters a new run, spends a reward, settles pending or credits a floor.
    """
    return bool(state.get('resume_requested') or int(state.get('map_refused_streak') or 0)>=1
                or (run_id and active.get('id')==run_id and active.get('phase')=='entered'
                    and active.get('victory') is False and active.get('reward') is False))


def rearm_after_battle(state,page):
    """Battle return can reset camera scale even on the same floor.

    Invalidate normalization bookkeeping only; actual unresolved node outcomes
    still prevent any gesture through prepare_view_change.
    """
    if not str(page or '').startswith('BATTLE') or not state.get('view_normalised'):return False
    state.pop('view_normalised',None)
    return True


def prepare_view_change(state):
    """Retire pixel coordinates only after the preceding node action was judged.

    A pan is not a node-click successor. Pending outcomes survive verbatim and
    defer the gesture, instead of being converted into progress by pixel motion.
    """
    if any(state.get(key) for key in ('map_pending','map_unjudged')):
        return None
    keys=('map_committed','map_pending_kind','map_party_point','map_party_floor',
          'map_party','last_party','map_step_reach','refused_targets','map_candidate_kinds')
    return {key:state.pop(key) for key in keys if key in state}


def relative_destination(record, box):
    """Describe a measured neighbor independently of current camera position."""
    board, party = record.get('map_board'), record.get('map_party')
    pitch = (record.get('map_lattice') or {}).get('pitch')
    if (not board or not party or not pitch or min(pitch)<=0
            or record.get('map_party_from_cache') or not record.get('map_seen_node')
            or record.get('map_party_source') not in ('locomotive', 'read')):
        return None
    x, y, w, h = box.get('box') if isinstance(box, dict) else box
    return (board, *pitch, x+w/2-party[0], y+h/2-party[1])


def same_relative_destination(previous, current):
    """Match across small anchor jitter and translation at comparable scale."""
    if previous is None or current is None or previous[0]!=current[0]:
        return False
    _, px, py, dx, dy = previous
    _, cx, cy, ex, ey = current
    return (abs(px-cx)<=.2*px and abs(py-cy)<=.2*py
            and abs(dx-ex)<=.24*px and abs(dy-ey)<=.24*py)


def retire_judged_target(state, target):
    """A matching accepted/rejected target has no outstanding outcome to protect.

    Only the matching target may be retired. The caller retains its rejection
    event/refused-target memory; a foreign or still-unjudged input is preserved.
    """
    if not target or state.get('map_unjudged'):
        return False
    pending=state.get('map_pending')
    if pending is not None and list(pending)!=list(target):return False
    changed=False
    if pending is not None:
        for key in ('map_pending','map_pending_kind','map_pending_expect','map_click_frame',
                    'map_pending_relative'):
            state.pop(key,None)
        changed=True
    if list(state.get('map_committed') or ()) == list(target):
        state.pop('map_committed', None)
        changed=True
    return changed


def retire_rejected_target(state,target):
    """Compatibility entry for callers already holding a rejected verdict."""
    return retire_judged_target(state,target)


def retire_recovery_after_progress(state):
    """Retire the answered MAP failure episode, not pending or business state.

    Only the node-verdict owner calls this after accepted progress. Merely
    leaving MAP for HOME/resume, waiting or superseding a click cannot renew a
    failed episode's budget. A recovery owned by a different page is untouched.
    """
    if state.get('recovery_for') != MAP_PAGE:
        return None
    keys=('recovery_for','recovery_rung','recovery_episode','recovery_since')
    return {key:state.pop(key) for key in keys if key in state}


def after_settle(state: dict, page: str, settled_page: str, *, expected=None) -> bool:
    """Retire a navigation probe only under its original action's verdict.

    Named preview/panel/room successors share the existing navigation judge.
    Allowed UNKNOWN waiting is unjudged, never an answered probe or receipt.
    """
    if is_map(page) and node_transition(settled_page, expected).outcome == 'accepted':
        if state.get('navigation_probe_pending'):
            state['navigation_probe_pending'] = False
            return True
    return False
