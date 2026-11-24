"""A turn that stood still on the floor-5 boss: the dial box and the assignment switch.

Live `pi-20261124-014821`, WAVE 3/3 TURN 19, a stage drawn in orange. With the skills
assigned the dial glows, the colour reading joined its glow to the highlighted skill
chips and returned a box 254 wide for a dial of about 120, and the press landed on a
chip. The turn came back unchanged, so the loop pressed Win Rate again, which is a
switch: on, off, on, off through four rounds, then `battle_progress_stalled`. One press
of Win Rate by hand assigned the turn at once. The pictures are drawn here.
"""
import numpy as np

from maalimbus import battle_vision as bv
from maalimbus.vision import Text
from maalimbus.window import CLICK, plan_step

SIZE = (1920, 1080)
CAPTIONS = [Text('Win', (1489, 795, 40, 22), 1.0), Text('Rate', (1485, 814, 46, 22), 1.0),
            Text('Damage', (1473, 865, 75, 21), 1.0), Text('WAVE', (18, 39, 51, 30), 1.0),
            Text('TURN', (18, 96, 43, 22), 1.0), Text('3/3', (84, 37, 48, 31), 1.0), Text('19', (94, 90, 40, 42), 1.0)]
WARM = (40, 140, 230)        # BGR: red > 150, green > 90, blue < 110
DIAL = (1317, 770, 120, 133)


def board(*, glow=False):
    image = np.full((1080, 1920, 3), 20, np.uint8)
    x, y, w, h = DIAL
    image[y:y + h, x:x + w] = WARM
    if glow:
        # The lit dial's glow reaching over the skill chips to its left.
        image[724:903, 1056:1330] = WARM
    return image


def test_a_dial_on_its_own_is_read_as_it_is_drawn():
    assert bv.dial_beside_caption(CAPTIONS, SIZE, board()) == DIAL


def test_a_glow_joined_to_the_dial_keeps_only_the_dial_corner():
    x, y, w, h = bv.dial_beside_caption(CAPTIONS, SIZE, board(glow=True))
    assert w <= bv.DIAL_SPAN and h <= bv.DIAL_SPAN
    # The box ends where the dial ends, and its middle is on the dial, not on a chip.
    assert x + w == DIAL[0] + DIAL[2] and y + h == 903
    centre = (x + w / 2, y + h / 2)
    assert DIAL[0] <= centre[0] <= DIAL[0] + DIAL[2] and DIAL[1] <= centre[1] <= DIAL[1] + DIAL[3]


def button(fill):
    """The Win Rate button at its caption, with that share of its face red."""
    image = np.full((1080, 1920, 3), (16, 26, 77), np.uint8)
    x, y, w, h = 1486, 796, 46, 41
    x0, x1, y0, y1 = int(x - .3 * w), int(x + 1.7 * w), int(y - .15 * h), int(y + 1.15 * h)
    cut = x0 + int((x1 - x0) * fill)
    image[y0:y1, x0:cut] = (24, 44, 200)
    return image, (x, y, w, h)


def test_the_switch_is_read_lit_unlit_or_not_at_all():
    assert bv.assignment_lit(*button(0)) is False
    assert bv.assignment_lit(*button(.5)) is True
    assert bv.assignment_lit(*button(.1)) is None           # neither: say so
    assert bv.assignment_lit(None, (1486, 796, 46, 41)) is None
    assert bv.assignment_lit(button(.5)[0], None) is None


def plan(previous, lit, start=(1317, 770, 120, 133)):
    buttons = dict(win_rate=[1486, 796, 46, 41], damage=[1473, 865, 75, 21])
    if lit != 'absent':
        buttons['lit'] = dict(win_rate=lit, damage=False)
    return plan_step('BATTLE_HUD', controls={}, start_box=list(start) if start else None, auto_assign=buttons,
                     battle_assignment='win_rate', battle_previous=previous)


def test_a_lit_switch_is_not_pressed_again_after_a_submit_that_changed_nothing():
    again = plan('submit', True)
    assert again['action'] == CLICK and again['reason'] == 'start_button_submits_the_assigned_turn'
    assert again['target'] == [1317, 770, 120, 133]
    # Unlit, or not read at all: the turn is assigned first, as before.
    for lit in (False, None, 'absent'):
        assign = plan('submit', lit)
        assert assign['reason'] == 'win_rate_is_the_proven_auto_assign_control' and assign['target'] == [1486, 796, 46, 41]
    # A new turn that was just assigned goes to the dial either way.
    assert plan('assign', True)['reason'] == 'start_button_submits_the_assigned_turn'
    assert plan('assign', False)['reason'] == 'start_button_submits_the_assigned_turn'
