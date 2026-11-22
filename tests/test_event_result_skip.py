"""The event Result page's own SKIP is not the Skill Check's forbidden SKIP.

Both pages print SKIP at the same pixels.  The driver hands every registered
control of every page to the planner, so the Skill Check's forbidden SKIP box was
also present on the Result page, and the installed app stopped on floor 2 with
``control_is_forbidden`` on a plain story result (live ``pi-20261121-221745``,
2026-11-21, ``frame-0448``: Result / ``Pressed "No".`` / SKIP [1628,929,138,83]).
"""
from maalimbus.window import CLICK, RECORD, plan_step

SKIP = [1628, 929, 138, 83]             # the Result page's OCR box, and the Skill Check's registered box


def test_the_result_skip_is_taken_with_the_check_skip_registered_at_the_same_box():
    plan = plan_step('EVENT_RESULT', controls={'event_check.skip_button': SKIP,
                                               'event_result.skip_button': SKIP})
    assert plan['action'] == CLICK
    assert plan['target'] == SKIP
    assert plan['reason'] == 'the_result_story_is_skipped_with_its_own_button'


def test_the_skill_check_skip_stays_forbidden_on_its_own_page():
    plan = plan_step('EVENT_CHECK', controls={'event_check.skip_button': SKIP},
                     check={'slot': 1, 'box': SKIP})
    assert plan['action'] == RECORD
    assert plan['reason'] == 'control_is_forbidden'


def test_a_misregistered_control_of_the_same_page_is_still_refused():
    # A forbidden control of the page being acted on keeps its veto, whatever the
    # plan calls its own target.
    plan = plan_step('EVENT_RESULT', controls={'event_result.skip_button': SKIP,
                                               'run_reward.give_up_button': [1, 2, 3, 4]})
    assert plan['action'] == CLICK                      # unrelated forbidden box elsewhere
    stolen = plan_step('REWARD_CARD', controls={'reward_card.card_01': SKIP,
                                                'reward_card.cancel_button': SKIP})
    assert stolen['action'] == RECORD and stolen['reason'] == 'control_is_forbidden'
