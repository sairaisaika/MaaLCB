"""The next node is where the game's own ">>" mark points.

On the dungeon map the game draws a double chevron on every path the party may take
next, halfway between the party's node and the node that path leads to. The mark is the
game's answer to "where can I go", it has the same shape on every floor theme, and it
needs no reading of the node itself. So:

    next node = party + 2 x (mark - party)

The older readers classify the node (its outline colour, its hexagon state, its icon),
and every theme that tints nodes differently broke one of them; the user's verdict on
2026-11-23 was that the hexagon reading cannot be relied on, with a screenshot of the
mark as the thing to read instead. On floor 4 of run ea52b509 the hexagon reader offered
the party's own sprite and missed the one node the mark pointed at.

How the mark is found without knowing the theme: it is grey. Every theme tints its
background (red, purple, teal, sepia) and its paths, while the mark is drawn without
colour and brighter than the ground it lies on. The mask is therefore relative to the
ground around the party, not a fixed colour band.

Measured on the installed app's stored runs (2026-11-21..23, four themes, both zoom
levels): for 46 map clicks the game accepted, the position computed from a mark was the
accepted node 44 times (within 90 px).

Nothing here sends input. A mark is evidence of a reachable node, and a click on a
wrong reading is refused by the game without effect.
"""
from __future__ import annotations

import math

#: The mark's centre lies this far from the party, in column pitches (it is drawn at the
#: middle of the path, so about one half).
BAND = (.33, .67)
#: Its bounding box, in column pitches (measured about .26 x .23).
SIDE = (.12, .42)


def marks(image, party, pitch):
    """Centres of the ">>" marks around the party, as ``(x, y)`` floats."""
    import cv2
    import numpy as np
    if image is None or getattr(image, 'ndim', 0) != 3 or party is None or not pitch or pitch <= 0:
        return []
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    height, width = hsv.shape[:2]
    yy, xx = np.ogrid[:height, :width]
    distance = np.hypot(xx - party[0], yy - party[1])
    ground = (distance > .25 * pitch) & (distance < .8 * pitch) & (hsv[:, :, 2] > 12)
    if int(ground.sum()) < 500:
        return []
    saturation = float(np.median(hsv[:, :, 1][ground]))
    value = float(np.median(hsv[:, :, 2][ground]))
    mask = ((hsv[:, :, 1] < .55 * saturation) & (hsv[:, :, 2] > max(25.0, 1.6 * value))
            & (distance < .9 * pitch)).astype(np.uint8) * 255
    # Thin lines (the paths not taken, node wireframes) go; the mark's two halves, which
    # the path line running through it separates, are joined.
    small, large = max(3, int(round(pitch / 75)) | 1), int(round(pitch / 22)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (small, small)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (large, large)))
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    found = []
    for index in range(1, count):
        _x, _y, w, h, area = (int(v) for v in stats[index])
        cx, cy = (float(v) for v in centroids[index])
        away = math.hypot(cx - party[0], cy - party[1])
        if not BAND[0] * pitch <= away <= BAND[1] * pitch:
            continue
        if not (SIDE[0] * pitch <= w <= SIDE[1] * pitch and SIDE[0] * pitch <= h <= SIDE[1] * pitch):
            continue
        if not .2 <= area / float(w * h) <= .85 or area < .004 * pitch * pitch:
            continue
        if cx - party[0] < .1 * pitch:
            continue        # paths lead onward; a grey blob behind or above the party is not a mark
        found.append((cx, cy))
    # The two chevrons of one mark can come apart as two blobs; a pair closer than a fifth
    # of a column is one mark, read at its middle.
    merged = []
    for point in sorted(found):
        near = next((i for i, other in enumerate(merged)
                     if math.hypot(point[0] - other[0], point[1] - other[1]) < .2 * pitch), None)
        if near is None:
            merged.append(point)
        else:
            merged[near] = ((merged[near][0] + point[0]) / 2, (merged[near][1] + point[1]) / 2)
    merged.sort(key=lambda point: abs(point[1] - party[1]))
    return merged


def next_nodes(image, party, pitch):
    """The nodes the marks point at, in the row shape the map planner consumes.

    The straight-ahead node comes first. Each row's ``target`` is a square around the
    computed node centre; ``candidate_kind`` is ``path_node``, the planner's name for a
    step the page itself marks, and ``source`` says it was read from a chevron.
    """
    rows = []
    side = int(round(.5 * pitch))
    for cx, cy in marks(image, party, pitch):
        x, y = party[0] + 2 * (cx - party[0]), party[1] + 2 * (cy - party[1])
        if not (0 <= x < image.shape[1] and 0 <= y < image.shape[0]):
            continue
        rows.append(dict(target=[int(round(x - side / 2)), int(round(y - side / 2)), side, side],
                         point=[int(round(x)), int(round(y))], party=[int(round(party[0])), int(round(party[1]))],
                         step=int(round(math.hypot(x - party[0], y - party[1]))),
                         mark=[int(round(cx)), int(round(cy))], measured_column_pitch=round(float(pitch), 2),
                         candidate_kind='path_node', source='chevron_mark_midway_on_the_path'))
    return rows
