"""A map node is its hexagon (state) plus its icon (type); the hexagon decides where to go.

The first group draws synthetic maps in code, so it runs on a public checkout. The
second replays the live floor 1 frames of 2026-11-21, where a pale-cream super shop
was the only next node and the old readers clicked cleared nodes behind the party;
those frames are local evidence and the tests skip, named, where they are absent.
"""
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from maalimbus import map_hexagons as hx

ROOT = Path(__file__).resolve().parents[1]


def bgr(h, s, v):
    return tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0])


CREAM, GOLD, RED = bgr(16, 80, 210), bgr(17, 200, 200), bgr(0, 230, 220)
BOARD = bgr(15, 80, 30)


def hexagon(image, centre, pitch, colour, *, icon=None, thickness=None):
    r = .18 * pitch
    points = np.array([[centre[0] + r * math.cos(math.radians(60 * k + 30)),
                        centre[1] + r * math.sin(math.radians(60 * k + 30))] for k in range(6)], np.int32)
    cv2.polylines(image, [points], True, colour, thickness or max(2, round(.02 * pitch)), cv2.LINE_AA)
    if icon is not None:
        s = round(.06 * pitch)
        cv2.rectangle(image, (centre[0] - s, centre[1] - s), (centre[0] + s, centre[1] + s), icon, -1)


def board(pitch=192, party=(760, 446)):
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[:] = BOARD
    row = hx.ROW_RATIO * pitch
    hexagon(image, party, pitch, CREAM)                                                 # occupied: dark centre
    hexagon(image, (party[0] - pitch, party[1]), pitch, GOLD, icon=GOLD)                 # visited, behind
    hexagon(image, (party[0] - pitch, round(party[1] + row)), pitch, CREAM, icon=CREAM)  # lit but behind
    return image, party, row


def test_states_are_read_from_the_hexagon_and_the_icon_is_cut_out_separately():
    pitch = 192
    image, party, row = board(pitch)
    ahead = (party[0] + pitch, round(party[1] + row))
    hexagon(image, ahead, pitch, CREAM, icon=CREAM)
    hexagon(image, (party[0] + pitch, party[1]), pitch, GOLD, icon=GOLD)
    hexagon(image, (party[0] + 2 * pitch, round(party[1] + row)), pitch, RED, icon=RED)
    cell = hx.read_cell(image, ahead, pitch)
    assert cell['state'] == 'lit' and cell['node_type'] is None
    assert abs(cell['point'][0] - ahead[0]) <= 4 and abs(cell['point'][1] - ahead[1]) <= 4
    x, y, w, h = cell['icon']
    assert w == h == round(2 * hx.ICON * pitch) and x < ahead[0] < x + w and y < ahead[1] < y + h
    hx_, hy, hw, hh = cell['hexagon']
    assert hw > w and hx_ < x and hy < y                                   # the icon lies inside the hexagon
    assert hx.read_cell(image, party, pitch)['state'] == 'occupied'
    assert hx.read_cell(image, (party[0] + pitch, party[1]), pitch)['state'] == 'revealed'
    assert hx.read_cell(image, (party[0] + 2 * pitch, round(party[1] + row)), pitch)['state'] == 'boss'
    assert hx.read_cell(image, (party[0] + pitch, round(party[1] - row)), pitch)['state'] == 'locked'


def test_only_lit_hexagons_one_column_ahead_are_next_nodes():
    pitch = 192
    image, party, row = board(pitch)
    lit = [(party[0] + pitch, round(party[1] - row)), (party[0] + pitch, round(party[1] + row))]
    for centre in lit:
        hexagon(image, centre, pitch, CREAM, icon=CREAM)
    hexagon(image, (party[0] + pitch, party[1]), pitch, GOLD, icon=GOLD)                  # revealed, not lit
    hexagon(image, (party[0] + 2 * pitch, party[1]), pitch, CREAM, icon=CREAM)            # lit but two columns ahead
    nodes = hx.next_nodes(image, party, pitch)
    assert len(nodes) == 2
    for node, centre in zip(sorted(nodes, key=lambda n: n['point'][1]), sorted(lit, key=lambda c: c[1])):
        assert math.hypot(node['point'][0] - centre[0], node['point'][1] - centre[1]) <= 6
        assert node['candidate_kind'] == 'lit_hexagon' and node['party'] == list(party)
        assert node['target'] == node['hexagon'] and node['point'][0] > party[0]


def test_a_lit_node_behind_the_party_is_never_offered():
    pitch = 192
    image, party, row = board(pitch)          # the only lit icon-bearing hexagon is behind the party
    assert hx.next_nodes(image, party, pitch) == []
    assert hx.lit_neighbours(image, party, pitch) == (None, [])


def test_the_spacing_is_confirmed_by_the_party_hexagon_not_taken_from_badges():
    """Badge columns can belong to the other zoom; the party's own hexagon decides."""
    pitch = 384
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[:] = BOARD
    party = (600, 400)
    hexagon(image, party, pitch, CREAM)
    ahead = (party[0] + pitch, round(party[1] + hx.ROW_RATIO * pitch))
    hexagon(image, ahead, pitch, CREAM, icon=CREAM)
    assert hx.next_nodes(image, party, 192) == []                 # the measured spacing alone finds nothing
    chosen, nodes = hx.lit_neighbours(image, party, 192)
    assert chosen == 384 and len(nodes) == 1
    assert math.hypot(nodes[0]['point'][0] - ahead[0], nodes[0]['point'][1] - ahead[1]) <= 10


def test_without_a_party_hexagon_there_is_no_spacing_and_no_guess():
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[:] = BOARD
    hexagon(image, (952, 606), 192, CREAM, icon=CREAM)          # a lit node, but nothing where the party is said to be
    assert hx.lit_neighbours(image, (760, 446), 192) == (None, [])
    assert hx.lit_neighbours(image, None, 192) == (None, [])
    assert hx.lit_neighbours(image, (760, 446), None) == (None, [])


def test_the_column_spacing_comes_from_distinct_node_columns():
    boxes = [(665, 361, 190, 190), (665, 521, 190, 190), (473, 361, 190, 190), (1049, 31, 190, 190)]
    assert hx.column_pitch((952, 446), boxes, 1920) == 192.0
    assert hx.column_pitch((952, 446), [], 1920) is None


def red_floor(pitch=384, party=(739, 818)):
    """The approach to a boss: the party's own hexagon glows red too, then `>>`, then the boss."""
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[:] = BOARD
    hexagon(image, party, pitch, RED)
    boss = (party[0] + pitch, party[1])
    hexagon(image, boss, pitch, RED, icon=RED)
    return image, party, boss


def test_the_train_sprite_measures_the_spacing_without_any_node_colour():
    image, party, boss = red_floor()
    assert hx.lit_neighbours(image, party, 384) == (None, [])     # the colour self-check refuses a red party
    pitch, nodes = hx.sprite_neighbours(image, party, 70.09)
    assert round(pitch) == 384 and len(nodes) == 1
    assert nodes[0]['state'] == 'boss' and nodes[0]['candidate_kind'] == 'lit_hexagon'
    assert math.hypot(nodes[0]['point'][0] - boss[0], nodes[0]['point'][1] - boss[1]) <= 10
    assert nodes[0]['lamp_gap'] == 70.09


def test_the_sprite_spacing_never_reaches_two_columns():
    image, party, _ = red_floor()
    # A lamp gap of 35 px is the zoomed-out map: the boss drawn 384 px away is two
    # columns ahead there, and nothing sits one column ahead.
    assert hx.sprite_neighbours(image, party, 35.1) == (None, [])
    assert hx.sprite_neighbours(image, party, None) == (None, [])
    assert hx.sprite_neighbours(image, None, 70.09) == (None, [])


def test_the_two_measured_zooms_give_their_column_pitch():
    assert round(70.09 * hx.PITCH_PER_LAMP_GAP) == 384
    assert round(35.11 * hx.PITCH_PER_LAMP_GAP) == 192


RUN = 'evidence/runtime/packaged-mirror-20261121-141507'
EARLIER = 'evidence/runtime/packaged-mirror-20261121-140432'
BOSS = 'dist/MaaLimbus/evidence/runtime/pi-20261122-003304'


@pytest.mark.needs_local(BOSS + '/frame-0073.png', BOSS + '/frame-0068.png')
@pytest.mark.parametrize('frame, boss', [('frame-0073', (1115, 818)), ('frame-0068', (532, 829))])
def test_the_live_floor_three_boss_is_the_next_node(frame, boss):
    """Floor 3 of pi-20261122-003304 stopped with no candidate one `>>` short of its boss."""
    from maalimbus.map_node_geometry import connected_nodes
    from maalimbus.runner import node_badge_template
    rows = connected_nodes(live(BOSS, frame), template=node_badge_template())
    assert len(rows) == 1 and rows[0]['state'] == 'boss'
    assert math.hypot(rows[0]['point'][0] - boss[0], rows[0]['point'][1] - boss[1]) <= 12
    assert 340 <= rows[0]['step'] <= 420                     # one column at the 384 px zoom


def live(run, frame):
    image = cv2.imread(str(ROOT / run / (frame + '.png')))
    assert image is not None
    return image


@pytest.mark.needs_local(RUN + '/frame-0133.png', RUN + '/frame-0174.png')
@pytest.mark.parametrize('frame, pitch, shop', [('frame-0133', 192, (1140, 610)),
                                                ('frame-0174', 384, (1072, 751))])
def test_the_live_super_shop_is_the_next_node_at_both_zooms(frame, pitch, shop):
    from maalimbus.map_node_geometry import connected_nodes
    from maalimbus.runner import node_badge_template
    rows = connected_nodes(live(RUN, frame), template=node_badge_template())
    assert len(rows) == 1 and rows[0]['candidate_kind'] == 'lit_hexagon'
    assert rows[0]['measured_column_pitch'] == pitch
    assert math.hypot(rows[0]['point'][0] - shop[0], rows[0]['point'][1] - shop[1]) <= 12
    assert rows[0]['point'][0] > rows[0]['party'][0]          # ahead, never the cleared nodes behind


@pytest.mark.needs_local(EARLIER + '/frame-0022.png', EARLIER + '/frame-0116.png')
def test_the_live_battle_choices_are_read_the_same_way():
    from maalimbus.map_node_geometry import connected_nodes
    from maalimbus.runner import node_badge_template
    three = connected_nodes(live(EARLIER, 'frame-0022'), template=node_badge_template())
    assert sorted(round(r['point'][1], -1) for r in three) == [330, 490, 640]
    one = connected_nodes(live(EARLIER, 'frame-0116'), template=node_badge_template())
    assert len(one) == 1 and abs(one[0]['point'][1] - 448) <= 8      # the node whose click the game took
