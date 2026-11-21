"""Control geometry stays in capture pixels; analysis is not a new witness."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maalimbus.battle_vision import dial_control, start_button
from maalimbus.capture_geometry import frame_coordinates
from maalimbus.vision import Text


def image_at(side, *, radius=60, centre=(1389, 818)):
    full = np.zeros((1080, 1920, 3), np.uint8)
    cv2.circle(full, centre, radius, (40, 120, 235), -1)
    return cv2.resize(full, (side, side * 9 // 16), interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize('side', [1280, 1920])
def test_same_lit_disc_has_capture_space_geometry(side):
    image = image_at(side)
    expected = frame_coordinates((1329, 758, 121, 121), (side, side * 9 // 16))
    box = dial_control(image)
    assert box is not None and max(abs(a-b) for a, b in zip(box, expected)) <= 2
    assert 0 <= box[0] < side and box[0] + box[2] <= side


@pytest.mark.parametrize('side', [1280, 1920])
@pytest.mark.parametrize('fault', ['undersized', 'oversized', 'off_band', 'erased', 'dark'])
def test_calibration_does_not_promote_small_large_off_band_or_erased_controls(side, fault):
    image = image_at(side, radius=39 if fault == 'undersized' else 95 if fault == 'oversized' else 60,
                     centre=(800, 500) if fault == 'off_band' else (1389, 818))
    if fault == 'erased':
        image[:] = 0
    if fault == 'dark':
        image = (image * .35).astype(np.uint8)
    assert dial_control(image) is None
    assert start_button([], (side, side * 9 // 16), image) is None


@pytest.mark.parametrize('side', [1280, 1920])
def test_native_caption_score_and_geometry_are_preserved(side):
    size = (side, side * 9 // 16)
    box = frame_coordinates((1320, 730, 80, 30), size)
    image = np.zeros((size[1], size[0], 3), np.uint8)
    low = Text('START', box, .84)
    high = Text('START', box, .99)
    assert start_button([low], size, image) is None
    assert start_button([high], size, image) == box
    assert high.box == box and high.score == .99 and high.text == 'START'
    assert start_button([high, Text('START', (box[0]+100, *box[1:]), .99)], size, image) is None


def test_capture_metadata_cannot_borrow_geometry_from_another_size():
    assert start_button([], (1920, 1080), image_at(1280)) is None


@pytest.mark.parametrize('side', [1280, 1920])
def test_retained_control_without_start_word_and_erased_counterexample(side):
    path = Path(__file__).resolve().parents[1] / 'evidence/runtime/packaged-mirror-20261031-205402/frame-0011.json'
    if not path.is_file() or not path.with_suffix('.png').is_file():
        pytest.skip('private retained native control witness absent')
    record = json.loads(path.read_text())
    assert not any(t['text'].strip().upper() == 'START' for t in record['ocr'])
    size = (side, side * 9 // 16)
    texts = [Text(t['text'], frame_coordinates(t['box'], size), t['score']) for t in record['ocr']]
    image = cv2.resize(cv2.imread(str(path.with_suffix('.png'))), size, interpolation=cv2.INTER_AREA)
    expected = frame_coordinates((1325, 746, 123, 151), size)
    found = start_button(texts, size, image)
    assert found is not None and max(abs(a-b) for a, b in zip(found, expected)) <= 2
    x, y, w, h = frame_coordinates((1280, 700, 200, 250), size)
    image[y:y+h, x:x+w] = 0
    assert start_button(texts, size, image) is None
