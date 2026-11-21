"""A navigation flag never owns an unrelated modal's affirmative button."""
import json
from pathlib import Path

import pytest

from maalimbus.vision import Text, pause_exploration_confirm
from maalimbus.window import plan_step

FRAME = Path(__file__).resolve().parents[1] / 'evidence/runtime/packaged-mirror-20261118-080819/frame-0024.json'


def records():
    raw = json.loads(FRAME.read_text(encoding='utf-8'))
    return raw, [Text(row['text'], tuple(row['box']), row['score']) for row in raw['ocr']]


def test_real_pause_question_owns_confirm_only_with_navigation_intent():
    raw, rows = records()
    box = pause_exploration_confirm(rows, raw['size'])
    assert box == (1104, 714, 118, 36)
    controls = {'pause_exploration.confirm': list(box), 'unknown_dialog.close': [710, 714, 142, 34]}
    assert plan_step('UNKNOWN_DIALOG', controls=controls)['target'] == controls['unknown_dialog.close']
    controls['leave_for_entry_pending'] = True
    plan = plan_step('UNKNOWN_DIALOG', controls=controls)
    assert plan['target'] == list(box)
    assert plan['reason'] == 'the_way_back_to_the_entry_is_confirmed'


@pytest.mark.parametrize('phrase', ['Pause Exploration', 'Save your progress and',
                                  'return to the Main Menu?', 'X Cancel', 'Confirm'])
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'low_score', 'outside'])
def test_every_question_and_button_anchor_is_unique_confident_and_current(phrase, mutation):
    raw, rows = records()
    original = next(row for row in rows if row.text == phrase)
    rows.remove(original)
    if mutation == 'duplicate':
        rows.extend([original, original])
    elif mutation == 'low_score':
        rows.append(Text(original.text, original.box, .89))
    elif mutation == 'outside':
        rows.append(Text(original.text, (0, 0, 100, 20), original.score))
    assert pause_exploration_confirm(rows, raw['size']) is None


@pytest.mark.parametrize('text', ['Use Lunacy', 'Abandon Exploration?', 'Give Up'])
def test_different_dialog_cannot_borrow_pause_intent(text):
    raw, rows = records()
    rows = [Text(text if row.text == 'Save your progress and' else row.text,
                 row.box, row.score) for row in rows]
    assert pause_exploration_confirm(rows, raw['size']) is None
    close = [710, 714, 142, 34]
    plan = plan_step('UNKNOWN_DIALOG', controls={'leave_for_entry_pending': True,
        'unknown_dialog.confirm': [1104, 714, 118, 36], 'unknown_dialog.close': close})
    assert plan['target'] == close
