"""Compare node interiors on two retained floors without using hue."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

REFERENCE = 'evidence/runtime/packaged-mirror-20261119-222048/frame-0007.png'
HELD_OUT = 'evidence/runtime/packaged-mirror-20261120-001228/frame-0066.png'
INTERIORS = {
    'shop': (1164, 463, 1206, 499),
    'event': (982, 622, 1009, 661),
    'battle': (595, 468, 628, 498),
}
HELD_OUT_CENTRES = {
    'shop': (835, 404), 'event': (708, 406), 'battle': (580, 510),
    'boss': (963, 404), 'rail': (773, 352),
}
BOARD = (.10, .208, .875, .789)


def raw_frame(root, path):
    image_path = root / path
    record = json.loads(image_path.with_suffix('.json').read_bytes())
    data = image_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if (digest != record['image_sha256'] or record['scene'] != 'MAP' or image is None
            or record['size'] != [image.shape[1], image.shape[0]]):
        raise ValueError(f'Frame identity does not support this audit: {path}')
    return image, {'path': path, 'sha256': digest, 'size': record['size']}


def scaled_interiors(reference, held_out_width):
    expected_scale = held_out_width / reference.shape[1]
    scales = [expected_scale * factor for factor in (.84, .90, .96, 1.0, 1.05, 1.11, 1.17)]
    return {
        label: [cv2.resize(reference[top:bottom, left:right], None, fx=s, fy=s) for s in scales]
        for label, (left, top, right, bottom) in INTERIORS.items()
    }


def board_bounds(plane):
    height, width = plane.shape
    return tuple(round(fraction * length) for fraction, length in zip(BOARD, (width, height) * 2))


def compare(reference, held_out):
    """Compare local scores with the strongest match in the map viewport."""
    reference = reference.max(axis=2)
    held_out = held_out.max(axis=2)
    width = held_out.shape[1]
    board_x, board_y, right, bottom = board_bounds(held_out)
    board = held_out[board_y:bottom, board_x:right]
    scores = {}
    viewport_matches = {}
    for label, templates in scaled_interiors(reference, width).items():
        scores[label] = {}
        for target, (x, y) in HELD_OUT_CENTRES.items():
            patch = held_out[y - 30:y + 30, x - 34:x + 34]
            scores[label][target] = round(max(cv2.minMaxLoc(
                cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED))[1]
                for template in templates), 3)
        peaks = []
        for template in templates:
            _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(board, template, cv2.TM_CCOEFF_NORMED))
            peaks.append((score, board_x + x + template.shape[1] // 2,
                          board_y + y + template.shape[0] // 2))
        score, x, y = max(peaks)
        viewport_matches[label] = {'score': round(score, 3), 'point': [x, y]}
    return scores, viewport_matches


def outline_candidates(plane, *, low, high):
    """Measure possible closed frames without looking at their interiors."""
    left, top, right, bottom = board_bounds(plane)
    viewport = plane[top:bottom, left:right]
    contours, _ = cv2.findContours(cv2.Canny(viewport, low, high),
                                   cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    scale = plane.shape[1] / 1280
    candidates = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if not (33 * scale <= width <= 70 * scale and 24 * scale <= height <= 62 * scale
                and .77 <= width / height <= 1.33):
            continue
        hull = cv2.convexHull(contour)
        fill = cv2.contourArea(hull) / (width * height)
        vertices = len(cv2.approxPolyDP(hull, .04 * cv2.arcLength(hull, True), True))
        if .60 <= fill <= .83 and 5 <= vertices <= 8:
            candidates.append((x + left, y + top, width, height))
    return sorted(set(candidates))


def interior_scores(plane, box, templates_by_type):
    """Score only template placements that fit inside the measured frame."""
    x, y, width, height = box
    inset = round(.08 * min(width, height))
    crop = plane[y + inset:y + height - inset, x + inset:x + width - inset]
    scores = {}
    for label, templates in templates_by_type.items():
        fits = [template for template in templates
                if template.shape[0] <= crop.shape[0] and template.shape[1] <= crop.shape[1]]
        if fits:
            scores[label] = round(max(cv2.minMaxLoc(
                cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED))[1]
                for template in fits), 3)
    return scores


def evaluate_outline_gate(reference, held_out, viewport_matches):
    """Locate geometry first; use manual annotations only to measure coverage."""
    plane = held_out.max(axis=2)
    templates = scaled_interiors(reference.max(axis=2), plane.shape[1])
    result = []
    for low, high in ((8, 24), (16, 48), (32, 96)):
        candidates = outline_candidates(plane, low=low, high=high)
        coverage = {
            label: sum(x <= cx < x + w and y <= cy < y + h for x, y, w, h in candidates)
            for label, (cx, cy) in HELD_OUT_CENTRES.items()
        }
        battle_x, battle_y = viewport_matches['battle']['point']
        result.append({
            'edge_thresholds': [low, high],
            'known_centre_coverage': coverage,
            'battle_background_peak_inside_outline': any(
                x <= battle_x < x + w and y <= battle_y < y + h for x, y, w, h in candidates),
            'candidates': [{'box': box, 'interior_scores': interior_scores(plane, box, templates)}
                           for box in candidates],
        })
    return result


def main():
    from maalimbus.documents import write_document
    from maalimbus.map_node_geometry import connected_nodes
    from maalimbus.runner import node_badge_template

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    a, a_identity = raw_frame(ROOT, REFERENCE)
    b, b_identity = raw_frame(ROOT, HELD_OUT)
    scores, viewport_matches = compare(a, b)
    outline_gate = evaluate_outline_gate(a, b, viewport_matches)
    gray = np.repeat(b.max(axis=2)[..., None], 3, axis=2)
    checked = {'reference': a_identity, 'held_out': b_identity,
               'reference_interiors': INTERIORS, 'held_out_centres': HELD_OUT_CENTRES,
               'scores': scores, 'viewport_matches': viewport_matches,
               'outline_gate': outline_gate,
               'channel_permutation_invariant': (
                   (scores, viewport_matches) == compare(a, b[:, :, ::-1])
                   and outline_gate == evaluate_outline_gate(a[:, :, ::-1], b[:, :, ::-1], viewport_matches)),
               'production_proposals': {'original': len(connected_nodes(b, template=node_badge_template())),
                                        'color_removed': len(connected_nodes(gray, template=node_badge_template()))},
               'scope': 'Local comparisons, unconstrained peaks and gated crops on two retained floors; no input'}
    write_document(args.report, checked, application_root=ROOT)


if __name__ == '__main__':
    main()
