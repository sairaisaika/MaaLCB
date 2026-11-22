"""A map node is two things: an outer hexagon and an icon inside it.

The hexagon tells the node's *state*. Measured on the live floor 1 maps of 2026-11-21
(runs ``packaged-mirror-20261121-140432`` and ``-141507``), at both map zooms:

=================  ==========================================================
a node you can     cream ring (hue 8-35, saturation 30-125) in at least 5 of
go to next         the 6 sectors, and a lit icon inside
the current node   the same cream ring, its centre covered by the train
visited / ahead    gold ring, little cream (at most 3 sectors)
locked (``?``)     nothing lit
boss               red ring
=================  ==========================================================

The icon tells the node's *type* (battle, event, shop, super shop, boss...). This
module cuts the icon out as its own region and records it; naming the type needs a
reference image per type, which is game artwork and therefore a local asset, so the
type stays ``None`` until such references exist. Choosing where to go does not need
it: any node the game lit as reachable is a legal step.

Positions come from the lattice: the next column is one pitch to the right of the
party, rows are ``ROW_RATIO`` pitches apart. Floors run left to right, so nothing at or
behind the party's column is ever a next node.
"""
from __future__ import annotations

import math

#: Vertical distance between rows, in column pitches (160 px rows at 192 px columns,
#: 320 at 384, on both measured zooms).
ROW_RATIO = 160 / 192
#: The ring band and the icon disc, in pitches from the node centre.
RING = (.13, .22)
ICON = .10
#: A sector counts as covered when this share of its ring pixels is cream.
SECTOR_SHARE = .02
#: Lit state: cream in this many of the six sectors, and a lit icon inside.
LIT_SECTORS = 5
ICON_LIT = .10
#: How far a cell centre may be nudged to meet the drawn hexagon, in pitches.
NUDGE = .04


def _masks(image):
    import cv2
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, sat, val = (hsv[:, :, i].astype(int) for i in range(3))
    return dict(
        cream=(hue >= 8) & (hue <= 35) & (sat >= 30) & (sat <= 125) & (val >= 100),
        gold=(hue >= 8) & (hue <= 35) & (sat >= 140) & (val >= 110),
        red=((hue <= 6) | (hue >= 170)) & (sat >= 150) & (val >= 120),
    )


def _cell(masks, centre, pitch):
    """Ring and icon measurements of one lattice cell, or None off the picture."""
    import numpy as np
    height, width = next(iter(masks.values())).shape
    cx, cy = centre
    half = .26 * pitch
    x0, x1, y0, y1 = int(cx - half), int(cx + half) + 1, int(cy - half), int(cy + half) + 1
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    radius = np.hypot(xx - cx, yy - cy) / pitch
    ring = (radius >= RING[0]) & (radius <= RING[1])
    icon = radius < ICON
    sector = ((np.arctan2(yy - cy, xx - cx) + np.pi) * 3 / np.pi).astype(int) % 6
    out = {}
    for name, mask in masks.items():
        sub = mask[y0:y1, x0:x1]
        covered = 0
        for index in range(6):
            part = ring & (sector == index)
            if part.any() and float(sub[part].mean()) >= SECTOR_SHARE:
                covered += 1
        out[name] = dict(ring=round(float(sub[ring].mean()), 3), sectors=covered,
                         icon=round(float(sub[icon].mean()), 3))
    return out


def state_of(measure):
    """The hexagon's state from its ring; the icon only says whether it is lit."""
    cream, gold, red = measure['cream'], measure['gold'], measure['red']
    if red['sectors'] >= 5:
        return 'boss'
    if cream['sectors'] >= LIT_SECTORS:
        return 'lit' if cream['icon'] >= ICON_LIT else 'occupied'
    if gold['sectors'] >= 1 or cream['sectors'] >= 1:
        return 'revealed'
    return 'locked'


def read_cell(image, centre, pitch, *, masks=None):
    """The best-fitting measurement of the hexagon near ``centre``, with its state."""
    masks = _masks(image) if masks is None else masks
    best = None
    step = max(1, round(NUDGE * pitch / 2))
    span = range(-2 * step, 2 * step + 1, step)
    for dx in span:
        for dy in span:
            point = (centre[0] + dx, centre[1] + dy)
            measure = _cell(masks, point, pitch)
            if measure is None:
                continue
            key = (measure['cream']['sectors'], measure['cream']['ring'])
            if best is None or key > best[0]:
                best = (key, point, measure)
    if best is None:
        return None
    _, point, measure = best
    side = round(2 * RING[1] * pitch)
    icon_side = round(2 * ICON * pitch)
    x, y = round(point[0]), round(point[1])
    return dict(point=[x, y], state=state_of(measure), measure=measure,
                hexagon=[x - side // 2, y - side // 2, side, side],
                icon=[x - icon_side // 2, y - icon_side // 2, icon_side, icon_side],
                node_type=None)


def next_nodes(image, party, pitch, *, rows=2):
    """Every lit hexagon one column ahead of the party, nearest row first.

    ``party`` is the occupied node's centre and ``pitch`` the measured column spacing.
    Returns rows in the shape the map planner consumes (``target``, ``party``, ``step``,
    ``candidate_kind``), each carrying its hexagon and icon regions.
    """
    if image is None or party is None or not pitch or pitch <= 0:
        return []
    masks = _masks(image)
    column = party[0] + pitch
    found = []
    for k in range(-rows, rows + 1):
        cell = read_cell(image, (column, party[1] + k * ROW_RATIO * pitch), pitch, masks=masks)
        if cell is None or cell['state'] != 'lit':
            continue
        if cell['point'][0] <= party[0] + .5 * pitch:
            continue  # never at or behind the party's own column
        found.append(dict(cell, party=[round(party[0]), round(party[1])], target=cell['hexagon'],
                          step=round(math.hypot(cell['point'][0] - party[0], cell['point'][1] - party[1])),
                          measured_column_pitch=round(float(pitch), 2), candidate_kind='lit_hexagon',
                          source='hexagon_state_lit_one_column_ahead'))
    found.sort(key=lambda row: row['step'])
    return found


#: Spacings tried around the measured one. Badge columns on screen can belong to
#: either zoom (live frame-0174 of ``-141507`` offered 192 px columns at the 384 px
#: zoom), so the measurement is a starting point, not the answer.
PITCH_FACTORS = (1.0, 2.0, .5, 1.5, 2.5)


def lit_neighbours(image, party, measured_pitch):
    """``(pitch, nodes)`` where the party's hexagon and a lit next node agree, else ``(None, [])``.

    A spacing counts only when the party's own cell reads as an occupied or lit
    hexagon at that spacing *and* at least one lit hexagon stands one column ahead.
    The first factor that satisfies both wins, so the measured spacing is preferred.
    """
    if image is None or party is None or not measured_pitch:
        return None, []
    width = image.shape[1]
    masks = _masks(image)
    tried = set()
    for factor in PITCH_FACTORS:
        pitch = measured_pitch * factor
        if not .05 * width <= pitch <= .30 * width or round(pitch) in tried:
            continue
        tried.add(round(pitch))
        own = read_cell(image, party, pitch, masks=masks)
        if own is None or own['state'] not in ('occupied', 'lit'):
            continue
        nodes = next_nodes(image, party, pitch)
        if nodes:
            return pitch, nodes
    return None, []


def column_pitch(party, boxes, width):
    """Column spacing from node boxes the map reader already offered, or None.

    Node columns sit at whole multiples of the pitch from the party; the smallest
    spacing between distinct columns within a quarter of the screen is that pitch.
    """
    columns = sorted({round(x + w / 2) for x, y, w, h in boxes} | ({round(party[0])} if party else set()))
    gaps = [b - a for i, a in enumerate(columns) for b in columns[i + 1:] if .05 * width <= b - a <= .25 * width]
    return float(min(gaps)) if gaps else None
