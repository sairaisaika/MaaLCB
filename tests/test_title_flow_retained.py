"""Recover the full title caption without broad fuzzy matching or manual taps."""
import hashlib
import json
from pathlib import Path
import re

import pytest

from maalimbus import session_flow as flows


def test_actual_native_title_caption_matches_both_wait_and_click_with_original_roi():
    root = Path(__file__).resolve().parents[1]
    path = root / 'evidence/runtime/window-20261117-043656/frame-0006.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    assert hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest() == record['image_sha256']
    native = record['ocr']
    for step in flows.flow('finish_launch')[:2]:
        token = flows.token_of(native, record['size'], step)
        assert token is not None and token['text'] == 'TOUCHITOISTART'
        assert token['box'] == [850, 808, 216, 41]
        assert step.threshold == .70 and step.roi == (.36, .72, .62, .84)
    assert all(step.kind != 'start_app' for step in flows.flow('finish_launch'))
    assert tuple(step.id for step in flows.flow('finish_launch')) == ('title_text', 'title_touch', 'home_menu')
    assert flows.validate('finish_launch') == []


@pytest.mark.parametrize('caption', ['TOUICHITOISTART', 'TOUCHITOISTART DOWNLOAD',
                                   'TOUCH TO STAIR', 'TOUCH I I TO START', 'START'])
def test_unrelated_or_partially_read_text_does_not_gain_start_authority(caption):
    assert re.search(flows.TITLE_START_CAPTION, caption) is None


def test_correct_text_outside_the_title_band_is_not_a_title_control():
    step = flows.flow('finish_launch')[1]
    assert flows.token_of([dict(text='TOUCHITOISTART', box=[100,100,216,41], score=.99)], (1920,1080), step) is None
