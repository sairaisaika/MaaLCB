"""The next node is read from the game's own ">>" mark, on any floor theme.

Run ea52b509 stopped on floor 4 (2026-11-23): the hexagon reader offered the party's own
sprite and missed the one node the mark pointed at. The user had said the hexagon
reading could not be relied on and showed the mark as the thing to read. The mark sits
halfway along each path the party may take, so the node is at twice the mark's offset.

The pictures here are drawn, not captured: a tinted ground, a coloured path and a grey
double chevron. Against the installed app's stored runs the same reader named the
accepted node for 42 of 46 accepted map clicks (four themes, both zoom levels).
"""
import math

import cv2
import numpy as np
import pytest

from maalimbus import map_chevrons

PARTY = (704, 431)
THEMES = {'purple': ((70, 25, 50), (40, 40, 220)), 'red': ((12, 8, 40), (30, 30, 230)),
          'teal': ((60, 55, 12), (220, 200, 40)), 'sepia': ((35, 50, 62), (120, 170, 215))}


def chevron(image, centre, angle, pitch, grey=115):
    """Draw the double chevron: two '>' bands, pointing along `angle`, about .26 x .23 pitch."""
    w, h, band, tip = .26 * pitch, .23 * pitch, .075 * pitch, .11 * pitch
    cos, sin = math.cos(angle), math.sin(angle)
    for shift in (-.05 * pitch, .05 * pitch):
        outline = [(-tip / 2 - band / 2, -h / 2), (-tip / 2 + band / 2, -h / 2), (tip / 2 + band / 2, 0),
                   (-tip / 2 + band / 2, h / 2), (-tip / 2 - band / 2, h / 2), (tip / 2 - band / 2, 0)]
        points = [(centre[0] + (x + shift) * cos - y * sin, centre[1] + (x + shift) * sin + y * cos) for x, y in outline]
        cv2.fillPoly(image, [np.array(points, np.int32)], (grey, grey, grey))


def board(theme, nodes, pitch=384, party=PARTY):
    """A map with a path and a mark from the party to each node in `nodes`."""
    ground, path = THEMES[theme]
    rng = np.random.default_rng(7)
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[:] = ground
    image = np.clip(image.astype(int) + rng.integers(-6, 7, image.shape), 0, 255).astype(np.uint8)
    for node in nodes:
        cv2.line(image, party, node, path, max(3, pitch // 64))
        middle = ((party[0] + node[0]) / 2, (party[1] + node[1]) / 2)
        chevron(image, middle, math.atan2(node[1] - party[1], node[0] - party[0]), pitch)
        # the path line runs through the mark, as it does in the game
        cv2.line(image, party, node, path, max(2, pitch // 96))
    return image


@pytest.mark.parametrize('theme', sorted(THEMES))
def test_the_node_is_at_twice_the_marks_offset_whatever_the_theme(theme):
    node = (PARTY[0] + 384, PARTY[1])
    rows = map_chevrons.next_nodes(board(theme, [node]), PARTY, 384)
    assert len(rows) == 1
    assert math.hypot(rows[0]['point'][0] - node[0], rows[0]['point'][1] - node[1]) <= 25
    x, y, w, h = rows[0]['target']
    assert (w, h) == (192, 192) and x <= node[0] <= x + w and y <= node[1] <= y + h
    assert rows[0]['candidate_kind'] == 'path_node' and rows[0]['party'] == list(PARTY)


def test_every_marked_path_is_offered_and_the_straight_one_comes_first():
    straight, down, up = (PARTY[0] + 384, PARTY[1]), (PARTY[0] + 384, PARTY[1] + 300), (PARTY[0] + 384, PARTY[1] - 290)
    rows = map_chevrons.next_nodes(board('red', [down, straight, up]), PARTY, 384)
    points = [tuple(row['point']) for row in rows]
    assert len(points) == 3 and math.hypot(points[0][0] - straight[0], points[0][1] - straight[1]) <= 25
    for node in (down, up):
        assert min(math.hypot(p[0] - node[0], p[1] - node[1]) for p in points) <= 35


def test_the_zoomed_out_map_is_read_with_its_own_pitch():
    party, node = (864, 485), (864 + 192, 485)
    rows = map_chevrons.next_nodes(board('teal', [node], pitch=192, party=party), party, 192)
    assert len(rows) == 1 and math.hypot(rows[0]['point'][0] - node[0], rows[0]['point'][1] - node[1]) <= 15
    assert rows[0]['target'][2] == 96


def test_a_map_with_no_mark_offers_nothing():
    image = board('purple', [])
    cv2.line(image, PARTY, (PARTY[0] + 384, PARTY[1]), (40, 40, 220), 6)        # a path, no mark
    cv2.line(image, PARTY, (PARTY[0] + 384, PARTY[1] + 300), (128, 128, 128), 5)  # a grey untaken path: thin
    assert map_chevrons.next_nodes(image, PARTY, 384) == []


def test_grey_things_that_are_not_a_mark_are_left_alone():
    image = board('purple', [])
    cv2.circle(image, (PARTY[0] + 384, PARTY[1]), 70, (230, 230, 230), 3)       # a white node outline, one pitch away
    cv2.rectangle(image, (PARTY[0] - 30, PARTY[1] + 50), (PARTY[0] + 30, PARTY[1] + 100), (120, 120, 120), -1)  # a badge under the party
    chevron(image, (PARTY[0] - 192, PARTY[1]), math.pi, 384)                    # a mark behind the party
    assert map_chevrons.next_nodes(image, PARTY, 384) == []


@pytest.mark.parametrize('image, party, pitch', [(None, PARTY, 384), (np.zeros((10, 10), np.uint8), PARTY, 384),
                                                 (np.zeros((1080, 1920, 3), np.uint8), None, 384),
                                                 (np.zeros((1080, 1920, 3), np.uint8), PARTY, 0)])
def test_without_a_picture_a_party_or_a_pitch_there_is_nothing_to_read(image, party, pitch):
    assert map_chevrons.marks(image, party, pitch) == [] and map_chevrons.next_nodes(image, party, pitch) == []
