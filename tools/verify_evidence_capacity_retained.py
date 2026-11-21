"""Offline native-Journal replay of historical captures and capacity refusal.

No ADB, controller construction, game input, ledger change, or model promotion.
Temporary isolated copies exercise the writer; original evidence stays in place.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'agent')]
import recognition
from maalimbus import evidence_capacity, runner, workspace
from maalimbus.vision import Text


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.out.resolve().is_relative_to(ROOT / 'build'):
        raise ValueError('Keep the audit under build')
    original_directory = ROOT / 'evidence/runtime/packaged-mirror-20261117-014047'
    sources = []
    for name, page in [('frame-0004', 'MAP'), ('frame-0005', 'NODE_PANEL')]:
        path = original_directory / (name + '.json')
        document = json.loads(path.read_text(encoding='utf-8'))
        assert document['scene'] == page
        assert digest(path.with_suffix('.png')) == document['image_sha256']
        sources.append((path, document))
    private = {p: digest(p) for p in (ROOT / 'config').rglob('*') if p.is_file()}
    old_root, old_budget = recognition.ROOT, workspace.BUDGET_BYTES
    replay = []
    try:
        with tempfile.TemporaryDirectory(prefix='maalimbus-capacity-replay-') as temporary:
            isolated = Path(temporary)
            recognition.ROOT = isolated
            journal = recognition.Journal(isolated / 'evidence/runtime/replayed')
            journal.capacity_scope = 'isolated-retained-replay'
            for index, (path, record) in enumerate(sources):
                image = cv2.imread(str(path.with_suffix('.png')))
                texts = [Text(item['text'], tuple(item['box']), item['score']) for item in record['ocr']]
                name = journal.frame(image, texts, record['scene'])
                captured = journal.directory / (name + '.json')
                assert np.array_equal(cv2.imread(str(captured.with_suffix('.png'))), image)
                replay.append(dict(source=str(path.relative_to(ROOT)), source_json_sha256=digest(path),
                    source_png_sha256=record['image_sha256'], scene=record['scene'],
                    replayed_json_sha256=digest(captured), replayed_png_sha256=digest(captured.with_suffix('.png')),
                    lossless_pixels=True))
                if index == 0:
                    admission = journal.before_input('plan', ('click', [1201,220,93,76]))
                    full = workspace.size(isolated)
                    workspace.BUDGET_BYTES = full
                else:
                    assert workspace.size(isolated) <= full
            class NoNativeInput:
                def __init__(self): self.requests = 0
                def post_click(self, *point):
                    self.requests += 1
                    raise AssertionError('Capacity refusal must precede this native request')
            native = NoNativeInput()
            device = runner.MaaDevice(native, target_long_side=0, before_input=journal.before_input)
            refused = False
            try:
                device.click(100, 100)
            except evidence_capacity.EvidenceCapacityUnavailable:
                refused = True
            assert refused and native.requests == 0
            pool = evidence_capacity.EvidenceCapacity(isolated)
            remaining = pool.load()['bytes']
            assert remaining >= evidence_capacity.STOP_BYTES
            recognition.write_loop_result(journal.directory,
                dict(passed=False, reason='evidence_capacity_unavailable_before_input', clicks_sent=0))
            assert pool.load()['bytes'] == 0
            assert (journal.directory / 'agent-result.json').is_file()
            assert workspace.size(isolated) <= full
    finally:
        recognition.ROOT, workspace.BUDGET_BYTES = old_root, old_budget
    assert all(digest(p) == expected for p, expected in private.items())
    report = dict(passed=True, replay=replay, admission=admission,
                  full_project_test_budget=full, remaining_credit_after_successor=remaining,
                  insufficient_topup_refused=True, native_input_requests=0,
                  terminal_result_saved=True, private_files_unchanged=len(private),
                  input_sent=False, game_controller=False, production_enabled=False,
                  scope='isolated native Journal replay, not a new live game transition or long-run capacity pass')
    text = json.dumps(report, indent=2) + '\n'
    workspace.require_space(ROOT, len(text.encode('utf-8')), budget=workspace.BUDGET_BYTES)
    args.out.write_text(text, encoding='utf-8')
    print(json.dumps(dict(passed=True, retained_frames=2, private_files_unchanged=len(private), input_sent=False)))


if __name__ == '__main__':
    main()
