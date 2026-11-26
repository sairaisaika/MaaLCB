"""The Mirror Dungeons card after the 2026-11-26 client update is read enlarged.

The update redrew the card: its title became a glowing caption over a banner. Live
`pi-20261126-023925` went HOME -> Drive five times and stopped with
`the_same_plan_repeated`, because neither the full-frame read nor the band read named the
card and so nothing named the page. Offline, with the app's own OCR, the band cut into
slices and enlarged four times read 'Dungeons' at .999 in two frames and in both slices
that cover the card; the box it gave, carried back, is [604, 324, 114, 28] on a 1920x1080
frame. The fake reader below returns what that offline read returned.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from maalimbus import drive_menu_native as menu
from maalimbus.vision import Text, classify

ROOT = Path(__file__).resolve().parents[1]
LOCALE = json.loads((ROOT / 'assets/resource/en/locale.json').read_bytes())
SIZE = (1920, 1080)
# What the full-frame read gave on frame-0032: the header reads, the card does not.
PAGE = [Text('Inferno', (1614, 200, 182, 48), 1.0), Text('MISSIONS', (212, 647, 132, 33), 1.0),
        Text('Event Closed', (200, 462, 158, 28), 1.0)]
#: The enlarged read's rows, by the slice's top edge in the frame (y of the band is 270).
ENLARGED = {270: [('Mirror', (708, 126, 340, 119), .897), ('Dungeons', (650, 217, 458, 115), .999)],
            355: [('Schemacraft', (574, 416, 610, 115), 1.0)]}


def reader(enlarged=ENLARGED, native_rows=()):
    calls = []

    def run(kind, param, pixels):
        calls.append((tuple(param.roi), pixels))
        if len(calls) == 1:                      # the band at the frame's own scale
            rows = [SimpleNamespace(text=t, score=s, box=b) for t, b, s in native_rows]
            return SimpleNamespace(hit=bool(rows), filtered_results=rows)
        top = 270 + 85 * (len(calls) - 2)
        rows = [SimpleNamespace(text=t, score=s, box=b) for t, b, s in enlarged.get(top, [])]
        return SimpleNamespace(hit=bool(rows), filtered_results=rows)
    return run, calls


def test_the_card_nobody_read_at_frame_scale_is_read_enlarged_and_names_the_page():
    image = np.zeros((1080, 1920, 3), np.uint8)
    assert classify(PAGE, LOCALE, SIZE) != 'DRIVE'
    run, calls = reader()
    repaired, proof = menu.repair(run, image, PAGE, LOCALE)
    assert classify(repaired, LOCALE, SIZE) == 'DRIVE'
    token = repaired[-1]
    # 650/4, 217/4 in the slice at (442, 270): the caption's own box, back in the frame.
    assert (token.text, token.box) == ('Dungeons', (442 + 162, 270 + 54, 114, 28))
    assert [p['purpose'] for p in proof] == ['drive_mirror_caption', 'drive_mirror_caption_magnified']
    assert proof[-1]['results'] == [dict(text='Dungeons', score=.999, box=[604, 324, 114, 28],
                                         slice=[442, 270, 442, 170], magnify=4)]
    # Every enlarged read is of a frame-sized picture that is not the frame itself.
    assert len(calls) >= 3 and all(pixels is not image and pixels.shape == image.shape for _, pixels in calls[1:])
    assert all(roi == (0, 0, 442 * 4, 170 * 4) for roi, _ in calls[1:])


def test_a_card_read_at_frame_scale_costs_no_enlarged_read():
    image = np.zeros((1080, 1920, 3), np.uint8)
    run, calls = reader(native_rows=[('Dungeons', (649, 317, 109, 20), .999)])
    repaired, proof = menu.repair(run, image, PAGE, LOCALE)
    assert classify(repaired, LOCALE, SIZE) == 'DRIVE' and len(calls) == 1
    assert [p['purpose'] for p in proof] == ['drive_mirror_caption']
    # Nor does a caption the full-frame read already had.
    run, calls = reader()
    had = PAGE + [Text('Dungeons', (649, 317, 109, 20), 1.0)]
    assert len(menu.repair(run, image, had, LOCALE)[1]) == 1 and len(calls) == 1


@pytest.mark.parametrize('rows', [
    {270: [('Dungeons', (650, 217, 458, 115), .89)]},                 # below the threshold
    {270: [('Schemacraft', (650, 217, 458, 115), 1.0)]},              # another card
    {270: [('Dungeons', (650, 217, 458.5, 115), .999)]},              # not a pixel box
    {270: [('Dungeons', (1500, 217, 458, 115), .999)]},               # outside the enlarged slice
    {},
])
def test_an_enlarged_read_that_proves_nothing_names_nothing(rows):
    image = np.zeros((1080, 1920, 3), np.uint8)
    run, _ = reader(rows)
    repaired, proof = menu.repair(run, image, PAGE, LOCALE)
    assert classify(repaired, LOCALE, SIZE) != 'DRIVE'
    assert proof[-1]['purpose'] == 'drive_mirror_caption_magnified' and proof[-1]['results'] == []


def test_the_same_caption_seen_by_two_overlapping_slices_is_one_caption():
    image = np.zeros((1080, 1920, 3), np.uint8)
    twice = {270: [('Dungeons', (650, 217, 458, 115), .999)], 355: [('Dungeons', (650, 217 - 340, 458, 115), .999)]}
    run, _ = reader({270: twice[270], 355: [('Dungeons', (650, 0, 458, 115), .999)]})
    repaired, proof = menu.repair(run, image, PAGE, LOCALE)
    boxes = [row['box'] for row in proof[-1]['results']]
    assert len(boxes) == len({tuple(box) for box in boxes}) >= 1
    assert sum(1 for token in repaired if token.text == 'Dungeons') == len(boxes)


def test_a_frame_too_small_to_hold_an_enlarged_slice_is_left_alone():
    # A band wider than a quarter of the frame cannot be enlarged four times onto it.
    assert menu.magnified(lambda *a: pytest.fail('read'), np.zeros((1080, 1920, 3), np.uint8),
                          (0, 270, 600, 324), LOCALE['mirror_menu'], .9, (.23, .25, .46, .55)) == []
