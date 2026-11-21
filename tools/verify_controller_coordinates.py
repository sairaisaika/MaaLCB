"""Exercise the installed Maa DLL with an in-memory controller, never a device.

This checks the native coordinate boundary, not a successful touch in Limbus.
The callback records what the DLL would deliver to a 1280x720 controller after
recognition at 1920x1080. Direct and one-node pipeline routes must agree.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from maalimbus.replay import ReplayController


def verify(runtime: Path) -> dict:
    import numpy as np
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit
    from maalimbus.runner import MaaDevice

    Library.open(runtime)

    with tempfile.TemporaryDirectory(prefix='maalimbus-native-coordinates-') as work:
        work = Path(work)
        # Maa's logger keeps its file open until process exit on Windows.
        # Keep that one small log in build, outside temporary bundle cleanup.
        Toolkit.init_option(ROOT / 'build/native-coordinate-check')
        controller = ReplayController(np.zeros((720,1280,3),dtype=np.uint8),
            uuid='maalimbus-in-memory-coordinate-check',
            expects=lambda kind,position,*args: kind in ('click','swipe'))
        assert controller.post_connection().wait().succeeded
        device = MaaDevice(controller)
        image = device.screencap()
        # A known raw size exposed the old manual conversion. The native DLL
        # owns this conversion whether or not Python has cached that size.
        device._screen = (1280, 720)
        resource = Resource()
        bundle = work / 'bundle' / 'pipeline'
        bundle.mkdir(parents=True)
        (bundle / 'inputs.json').write_text(json.dumps({
            name: {'recognition': 'DirectHit', 'action': 'DoNothing'}
            for name in ('MirrorPointClick', 'MirrorPointSwipe')
        }), encoding='utf-8')
        assert resource.post_bundle(bundle.parent).wait().succeeded
        tasker = Tasker()
        assert tasker.bind(resource, controller)
        device.click(960, 540)
        device.swipe(600, 300, 900, 600, 500)
        device.tasker = tasker
        device.route_suspect = True
        device.click(960, 540)
        device.route_suspect = True
        device.swipe(600, 300, 900, 600, 500)
        actual = [list(row) for row in controller.inputs]
        expected = [['click', 640, 360], ['swipe', 400, 200, 600, 400, 500]] * 2
        # Explicitly tear down while callbacks and temporary resources exist.
        tasker.post_stop().wait()
        del tasker, device, resource, controller
        return {
            'passed': actual == expected,
            'framework_version': importlib.metadata.version('maafw'),
            'framework_sha256': hashlib.sha256((runtime / 'MaaFramework.dll').read_bytes()).hexdigest(),
            'implementation_sha256': {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                for name in ('src/maalimbus/runner.py','tools/verify_controller_coordinates.py')},
            'native_controller': 'in_memory_callbacks', 'device_inputs': 0,
            'raw_size': [1280, 720], 'recognition_size': [image.shape[1], image.shape[0]],
            'routes': ['direct_click', 'direct_swipe', 'pipeline_click', 'pipeline_swipe'],
            'actual': actual, 'expected': expected,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'dist/MaaLimbus/maafw')
    parser.add_argument('--report', type=Path, default=ROOT / 'build/controller-coordinates-native.json')
    args = parser.parse_args()
    result = verify(args.runtime.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
