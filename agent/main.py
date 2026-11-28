import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'agent')]
from maalimbus.runtime_paths import ROOT
if getattr(sys, 'frozen', False):
    # maa.agent imports and opens its native library immediately.
    os.environ['MAAFW_BINARY_PATH'] = str(ROOT / 'maafw')

from maa.agent.agent_server import AgentServer
from maa.library import Library
from recognition import LimbusRecognition, LimbusTerminal
from recognition import MapObservation, BattleObservation
from recognition import MirrorLoopAction, MainTaskAction


def main():
    import json
    if sys.argv[1:]==['--lease-self-test']:
        from maalimbus.controller_lease import ControllerLease
        lease=ControllerLease(ROOT/'build/controller.lock')
        try:print(json.dumps(dict(passed=True,backend=lease.backend,controller_created=False)))
        finally:lease.close()
        return
    if sys.argv[1:] == ['--evidence-storage-check']:
        from maalimbus.capture_retention import storage_diagnostic
        print(json.dumps(storage_diagnostic(ROOT)))
        return
    if sys.argv[1:2] == ['--pretask']:
        # ProjectInterface pretask: MXU runs this before it connects a controller.
        if sys.argv[2:3] != ['launch_emulator'] or len(sys.argv) > 4:
            raise SystemExit('Expected --pretask launch_emulator [options JSON]')
        from maalimbus import emulator_launch, emulator_registry
        from maalimbus.runtime_paths import data_directory
        raise SystemExit(emulator_launch.main(
            sys.argv[3:], remembered=lambda: emulator_registry.remembered(data_directory(ROOT))))
    if sys.argv[1:] == ['--local-assets-check']:
        # Which game bitmaps this installation has. Reads files; exit status 2 when incomplete.
        from maalimbus import local_assets
        groups=local_assets.inventory(ROOT)
        absent=local_assets.incomplete(groups)
        print(json.dumps(dict(complete=not absent,guide=local_assets.GUIDE,
            groups={name:dict(total=group['total'],missing=len(group['missing']),invalid=len(group['invalid']),
                              feature=group['feature']) for name,group in groups.items()})))
        raise SystemExit(2 if absent else 0)
    if sys.argv[1:] == ['--self-test']:
        # Read actual installed resources and load native libraries; no controller.
        import cv2
        import numpy as np
        probe=np.arange(48,dtype=np.uint8).reshape(4,4,3)
        ok,encoded=cv2.imencode('.png',probe,[cv2.IMWRITE_PNG_COMPRESSION,6])
        if not ok or not np.array_equal(cv2.imdecode(encoded,cv2.IMREAD_COLOR),probe):
            raise RuntimeError('Frozen image PNG roundtrip failed')
        if cv2.resize(probe,(8,8)).shape!=(8,8,3):
            raise RuntimeError('Frozen image resize failed')
        from maalimbus.capture_geometry import analysis_image,frame_coordinates
        if (frame_coordinates((960,540),(1280,720))!=(640,360)
                or analysis_image(np.zeros((720,1280,3),dtype=np.uint8)).shape!=(1080,1920,3)):
            raise RuntimeError('Frozen capture calibration contract failed')
        from maalimbus.capture_profiles import BattleCaptureObserver
        from maalimbus.battle_vision import dial_control
        battle=np.zeros((720,1280,3),dtype=np.uint8)
        cv2.circle(battle,(926,545),40,(40,120,235),-1)
        if BattleCaptureObserver.successor_size!=(1920,1080) or dial_control(battle) is None:
            raise RuntimeError('Frozen battle capture calibration contract failed')
        Library.open(ROOT / 'maafw', agent_server=True)
        for locale in ('en', 'jp'):
            LimbusRecognition(locale)
        # Game bitmaps are supplied locally and never packaged. A catalog is loaded only when
        # its bitmaps are installed; otherwise the result states the absence by group, so a
        # package without game assets can be checked without pretending the assets work.
        from maalimbus import local_assets
        absent=local_assets.incomplete(local_assets.inventory(ROOT))
        if 'gifts' not in absent:
            from maalimbus.gift_vision import GiftCatalog
            GiftCatalog(ROOT / 'assets/resource/base')
        if 'themes' not in absent:
            from maalimbus.theme_vision import ThemeCatalog
            ThemeCatalog(ROOT / 'assets/resource/base')
        from maalimbus import runner
        from maalimbus.shop_value_shadow import diagnostic
        from maalimbus.runtime_paths import data_directory
        if runner.ROOT != ROOT or not runner.REGISTRY.is_file():
            raise RuntimeError('Runner resolved the wrong installed resource directory')
        print(json.dumps({'passed': True, 'application_root': str(ROOT),
                          'runner_root': str(runner.ROOT),
                          'private_state_directory': str(data_directory(ROOT)),
                          'device_controller': False, 'locales': ['en', 'jp'],
                          'local_game_assets': {'complete': not absent, 'missing_groups': sorted(absent),
                                                'catalogs_loaded': sorted({'gifts','themes'}-set(absent)),
                                                'guide': local_assets.GUIDE},
                          'image_runtime': {'png_roundtrip': True, 'resize': True,'capture_calibration':True,
                                            'battle_capture_calibration':True},
                          'shop_value_diagnostic': diagnostic(ROOT/'assets/resource/base/model/shop-value')}))
        return
    if len(sys.argv)==3 and sys.argv[1]=='--native-frame-readback':
        import json
        from maalimbus.capture_retention import roots
        from maalimbus.native_evidence import frame_reference
        project,runtimes=roots(ROOT);path=Path(sys.argv[2]).resolve()
        if not any(path.is_relative_to(base) for base in runtimes):
            raise ValueError('Native frame readback requires a local canonical runtime record')
        reference,_=frame_reference(path)
        print(json.dumps(dict(passed=True,frame_ref=reference.as_dict(),
                              controller_created=False,input_sent=False)))
        return
    capture_probe=len(sys.argv)==3 and sys.argv[1]=='--capture-profile-probe'
    if len(sys.argv) != 2 and not capture_probe:
        raise SystemExit('Expected Maa Agent socket identifier or --self-test')
    from maalimbus.native_agent import native_temp
    with native_temp(ROOT):
        run_agent(capture_probe=capture_probe)


def run_agent(*,capture_probe=False):
    import json
    resource = json.loads(os.environ.get('PI_RESOURCE', '{}'))
    locale = resource.get('name', 'en')
    Library.open(Path(os.environ.get('MAAFW_BINARY_PATH', ROOT / 'maafw')), agent_server=True)
    recognition = LimbusRecognition(locale)
    from pipeline_trace import PipelineTrace
    recognition.pipeline_trace = PipelineTrace()
    AgentServer.add_context_sink(recognition.pipeline_trace)
    # MXU owns the actual controller; retain its chosen PI profile for diagnosis.
    recognition.journal.record('pi_controller', profile=json.loads(os.environ.get('PI_CONTROLLER', '{}')))
    AgentServer.register_custom_recognition('limbus_scene', recognition)
    AgentServer.register_custom_action('limbus_terminal', LimbusTerminal(recognition))
    # The map and battle observation nodes are read-only recorders that the pipeline
    # names (`MapObserve` / `BattleObserve`) and the toolkit drives directly; a node
    # whose custom_action was never registered cannot run at all, so both names must
    # be here even though no task entry reaches them. `WindowMapObserve` and
    # `WindowBattleObserve`, which the loop posts for every read, use the same two.
    AgentServer.register_custom_action('limbus_map_observe',MapObservation(recognition))
    AgentServer.register_custom_action('limbus_battle_observe',BattleObservation(recognition))
    # `MirrorLoop` is the whole dungeon: it drives `maalimbus.runner` inside this task,
    # so the packaged app runs the same loop the command line runs.
    AgentServer.register_custom_action('limbus_mirror_loop',MirrorLoopAction(recognition))
    AgentServer.register_custom_action('limbus_main_task',MainTaskAction(recognition))
    if capture_probe:
        # Explicit read-only diagnostic mode only; absent from normal registration.
        from recognition import CaptureProfileProbeAction
        AgentServer.register_custom_action('limbus_capture_profile_probe',CaptureProfileProbeAction(recognition))
    # Self-test does not open IPC. Retain the actual loaded native modules when
    # the production startup fails, instead of attributing it to a guessed DLL.
    if os.name == 'nt':
        import ctypes
        import hashlib
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        kernel.GetModuleFileNameW.restype = ctypes.c_uint32
        modules = {}
        for name in ('MaaAgentServer.dll','MaaUtils.dll','opencv_world4_maa.dll','MSVCP140.dll','WS2_32.dll'):
            handle = kernel.GetModuleHandleW(name)
            if handle:
                buffer = ctypes.create_unicode_buffer(32768)
                if kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
                    path = Path(buffer.value)
                    modules[name] = dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        recognition.journal.record('agent_native_bootstrap',modules=modules,
            application_root=str(ROOT),socket_identifier=sys.argv[-1],native_temp=os.environ.get('TEMP'))
    AgentServer.start_up(sys.argv[-1])
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == '__main__':
    main()
