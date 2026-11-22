"""An event whose outcome is a fight offers "Commence Battle" where Continue usually is.

Live ``pi-20261122-040807`` (2026-11-22), floor 5: the umbrella event resolved to
"Combat Encounter!" and its outcome page carried a bright "Commence Battle" in the
bottom-right slot. The page stayed EVENT_RESULT, the planner tapped the story panel
six times for a Continue that never comes, and the run stopped with
``event_result_semantic_progress_stalled``. The rows are retyped from ``frame-0027``;
the frame itself is local evidence.
"""
import json
from pathlib import Path

from maalimbus.vision import Text, classify
from maalimbus.window import CLICK, plan_step

LOCALES = Path(__file__).resolve().parents[1] / 'assets/resource'
WORDS = json.loads((LOCALES / 'en/locale.json').read_text(encoding='utf-8'))

PAGE = [Text('Result', (1068, 168, 138, 42), 1.0),
        Text('Go under the umbrella and wait until the rain stops.', (1062, 315, 646, 30), .99),
        Text('Combat Encounter!', (1088, 470, 252, 28), .99),
        Text('Win the battle to gain E.G.O Gifts "Four-leaf', (1088, 514, 576, 27), .99),
        Text('No rewards upon Defeat', (1090, 605, 324, 28), .99),
        Text('Commence Battle', (1580, 954, 236, 28), .99)]


def test_the_fight_outcome_is_the_ready_result_page():
    assert classify(PAGE, WORDS, (1920, 1080)) == 'EVENT_RESULT_READY'
    # Without the button the page is still the dim form, as before.
    assert classify(PAGE[:-1], WORDS, (1920, 1080)) == 'EVENT_RESULT'


def test_the_ready_page_presses_its_bottom_right_control():
    box = [1588, 943, 218, 55]                      # the registered continue slot
    plan = plan_step('EVENT_RESULT_READY', controls={'event_result.continue_button': box})
    assert plan['action'] == CLICK and plan['target'] == box
    x, y, w, h = box                                # the live button spans about 1570-1830 x 925-1015
    assert 1570 <= x + w / 2 <= 1830 and 925 <= y + h / 2 <= 1015


def test_a_commence_alone_on_the_skill_check_is_not_a_result():
    # The skill check's own "Commence" (no "Battle") commits a roll on another page.
    check = [Text('What will you do?', (1194, 258, 300, 30), .99), Text('Commence', (1578, 946, 240, 48), .99)]
    assert classify(check, WORDS, (1920, 1080)) != 'EVENT_RESULT_READY'
