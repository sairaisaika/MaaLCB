"""Read-only MuMu verification of the map page identity and bounded route refusal.

Connects an Android controller with the Null input method, checks that Limbus is
the unique foreground app, captures one frame and runs the real Maa pipeline node
`MapObserve` (limbus_map_observe). No click, swipe or key is ever sent.
"""
import argparse
import hashlib
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'agent'))

import cv2
from maa.controller import AdbController
from maa.define import MaaAdbInputMethodEnum, MaaAdbScreencapMethodEnum
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from maalimbus.adb_preflight import foreground
from maalimbus.controller_lease import ControllerLease
from maalimbus.jobs import wait_job, wait_task
from maalimbus.adb_device import (build, discover, foreground_of, input_policy,
                                   names)
from maalimbus.map_vision import map_header, route_decision
from maalimbus.vision import Text
from recognition import Journal, LimbusRecognition, MapObservation

PIPELINE_DIR = ROOT / 'build/map-live-debug'
PIPELINE = {
    'MapObserve': {
        'recognition': 'Custom', 'custom_recognition': 'limbus_scene',
        'custom_recognition_param': {'scene': 'MAP'},
        'action': 'Custom', 'custom_action': 'limbus_map_observe',
        'max_hit': 1, 'next': [], 'on_error': [],
    },
}


def prepare(current_page=False) -> Path:
    (PIPELINE_DIR / 'pipeline').mkdir(parents=True, exist_ok=True)
    pipeline=PIPELINE
    if current_page:
        node={k:v for k,v in PIPELINE['MapObserve'].items()
              if k not in ('custom_recognition','custom_recognition_param')}
        node['recognition']='DirectHit'
        pipeline={'MapObserve':node}
    (PIPELINE_DIR / 'pipeline/map-live.json').write_text(
        json.dumps(pipeline, indent=2) + '\n', encoding='utf-8')
    return PIPELINE_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--adb', type=Path, default=None,
                        help='optional adb path restricting discovery; omit to let '
                             'MaaToolkit search and supply the emulator config')
    parser.add_argument('--address', required=True)
    parser.add_argument('--current-page',action='store_true',
                        help='capture any current page once; success means a hash-verified '
                             'read, not map identity, progress or permission to input')
    args = parser.parse_args()
    directory = ROOT / ('evidence/runtime/map-live-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    directory.mkdir(parents=True)
    lease = ControllerLease.acquire(ROOT / 'build/controller.lock')
    deadline = time.monotonic() + 120
    result = dict(pid=os.getpid(), address=args.address, controller='Maa AdbController',
                  input_method='Null', input_sent=False, verified_clear=False,
                  foreground_before=None)
    try:
        Library.open(args.binary, agent_server=False)
        device = discover(args.address, args.adb)
        result['foreground_before'] = foreground_of(device)
        from maalimbus.native_evidence import configure_host
        result['native_evidence_policy']=configure_host(prepare(args.current_page))
        controller = build(device, input_enabled=False)
        result['device'] = device
        wait_job(controller.post_connection(), timeout=15, deadline=deadline)
        controller.set_screenshot_target_long_side(1920)
        wait_job(controller.post_screencap(), timeout=15, deadline=deadline)
        frame = controller.cached_image
        if frame is None or not frame.size:
            raise RuntimeError('Maa screenshot unavailable')
        if not args.current_page and not cv2.imwrite(str(directory / 'frame.png'), frame):
            raise RuntimeError('Frame could not be saved')
        journal = Journal(directory)
        recognition = LimbusRecognition('en', journal)
        resource = Resource()
        resource.register_custom_recognition('limbus_scene', recognition)
        resource.register_custom_action('limbus_map_observe', MapObservation(recognition))
        for layer in ('base', 'en'):
            wait_job(resource.post_bundle(ROOT / f'assets/resource/{layer}'), timeout=20, deadline=deadline)
        wait_job(resource.post_bundle(PIPELINE_DIR), timeout=20, deadline=deadline)
        tasker = Tasker()
        assert tasker.bind(resource=resource, controller=controller)
        job = tasker.post_task('MapObserve')
        try:
            task = wait_task(tasker, job, deadline=deadline)
            result.update(task_result=task, stop_confirmed=task['stop_confirmed'])
        except RuntimeError as error:
            # A page that is not an identified map stops the read-only node. The
            # observation event written before that stop is the actual evidence.
            if not job.done:
                wait_job(tasker.post_stop(), timeout=5)
            result.update(task_result={'task_succeeded': False, 'stop_confirmed': job.done,
                                       'error': str(error)}, stop_confirmed=job.done)
        result['input_sent'] = False
        events = [json.loads(line) for line in
                  (directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        observed = next((e for e in events if e['event'] == 'map_observed'), None)
        frames = sorted(directory.glob('frame-*.json'))
        record = json.loads(frames[-1].read_text(encoding='utf-8')) if frames else {}
        result['scene'] = record.get('scene')
        if observed is not None:
            result['map_observed'] = observed
            result['route'] = observed['route']
        records = [Text(t['text'], tuple(t['box']), t['score']) for t in record.get('ocr', [])]
        header = map_header(records, tuple(record['size'])) if record else None
        result['identity'] = None if header is None else {
            'floor': header.floor, 'pack': header.pack,
            'header_box': header.exploring_text.box, 'pack_box': header.pack_text.box}
        result['route_recheck'] = route_decision(header, tuple(record['size'])) if record else None
        result['foreground_after'] = foreground_of(device)
        result['reason'] = ('read_only_map_observed' if result['scene'] == 'MAP'
                            else 'read_only_frame_is_not_an_identified_map')
        result['passed'] = bool(result['scene'] == 'MAP' and result.get('identity')
                                and observed is not None
                                and observed['route']['next_node'] is None
                                and result['route_recheck']['next_node'] is None
                                and not result['input_sent'])
        result['map_identity_verified']=result['passed']
        if args.current_page:
            png=frames[-1].with_suffix('.png') if frames else None
            captured=bool(record and png is not None and png.is_file()
                and hashlib.sha256(png.read_bytes()).hexdigest()==record.get('image_sha256'))
            result.update(passed=captured and result.get('stop_confirmed',False),
                          current_page_captured=captured,
                          frame=None if not frames else str(frames[-1]),
                          reason='readonly_current_page_capture_not_progress_or_input_authorization')
    except Exception as error:
        result.update(reason='map_live_failed', error=str(error), passed=False)
        raise
    finally:
        (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                               encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=1))
        lease.close()
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
