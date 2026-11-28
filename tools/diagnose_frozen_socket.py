"""Compare minimal frozen/unfrozen Maa server startup, with no controller."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import hashlib
import shutil
import zipfile

from make_local_app import freeze

ROOT = Path(__file__).resolve().parents[1]
ENTRY = '''import os, sys
from pathlib import Path
phase = os.environ.get("MAALIMBUS_DIAGNOSTIC_PHASE", "registered")
from maalimbus import runtime_paths
runtime_paths.ROOT = Path(os.environ["MAAFW_BINARY_PATH"]).parent
from maa.agent.agent_server import AgentServer
if phase != "minimal":
    import main as full_main
    print("full_imported", flush=True)
    if phase == "entry":
        full_main.main()
        raise SystemExit(0)
    if phase in ("recognition", "registered"):
        recognition = full_main.LimbusRecognition("en")
        print("recognition_constructed", flush=True)
    if phase == "registered":
        AgentServer.register_custom_recognition("limbus_scene", recognition)
        for name, factory in (
            ("limbus_terminal", full_main.LimbusTerminal),
            ("limbus_map_observe", full_main.MapObservation),
            ("limbus_battle_observe", full_main.BattleObservation),
            ("limbus_mirror_loop", full_main.MirrorLoopAction),
            ("limbus_main_task", full_main.MainTaskAction)):
            AgentServer.register_custom_action(name, factory(recognition))
        print("registered", flush=True)
print("imported", flush=True)
ok = AgentServer.start_up(sys.argv[1])
print("started="+str(ok), flush=True)
AgentServer.join()
AgentServer.shut_down()
'''


def run(command, environment):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=10, env=environment)
        return dict(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired as error:
        return dict(timed_out=True, stdout=str(error.stdout), stderr=str(error.stderr))


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='maalimbus-minimal-socket-') as work:
        work = Path(work)
        entry = work / 'minimal.py'
        entry.write_text(ENTRY, encoding='utf-8')
        environment = {**os.environ, 'MAAFW_BINARY_PATH': str(ROOT/'dist/MaaLimbus/maafw'),
                       'MAALIMBUS_EVIDENCE':str(work/'evidence')}
        candidate = freeze(entry, 'MinimalMaaServer', work)
        installed = ROOT/'dist/MaaLimbus/agent'
        def hashes(directory):
            return {p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in directory.rglob('*') if p.is_file()}
        a,b=hashes(candidate/'_internal'),hashes(installed/'_internal')
        differences=[name for name in sorted(set(a)|set(b)) if a.get(name)!=b.get(name)]
        with zipfile.ZipFile(candidate/'_internal/base_library.zip') as ca, zipfile.ZipFile(installed/'_internal/base_library.zip') as ia:
            za={n:hashlib.sha256(ca.read(n)).hexdigest() for n in ca.namelist()}
            zb={n:hashlib.sha256(ia.read(n)).hexdigest() for n in ia.namelist()}
            zip_differences=[n for n in sorted(set(za)|set(zb)) if za.get(n)!=zb.get(n)]
        from verify_packaged_agent_ipc import verify
        previous = os.environ.get('MAALIMBUS_DIAGNOSTIC_PHASE')
        frozen = {}
        try:
            for phase in ('entry',):
                os.environ['MAALIMBUS_DIAGNOSTIC_PHASE'] = phase
                frozen[phase] = verify('ipc', agent_exe=candidate/'MinimalMaaServer.exe',variant='-'+phase)
            transplanted=installed/'MaaSocketDiagnostic.exe'
            if transplanted.exists():raise ValueError('Diagnostic executable already exists')
            try:
                shutil.copyfile(candidate/'MinimalMaaServer.exe',transplanted)
                frozen['installed_dependencies']=verify('ipc',agent_exe=transplanted,variant='-transplant')
                base_zip=installed/'_internal/base_library.zip'
                original_zip=base_zip.read_bytes()
                try:
                    shutil.copyfile(candidate/'_internal/base_library.zip',base_zip)
                    frozen['matching_base_zip']=verify('ipc',agent_exe=transplanted,variant='-matching-zip')
                    frozen['actual_executable_matching_zip']=verify('ipc',variant='-actual-matching-zip')
                finally:
                    base_zip.write_bytes(original_zip)
            finally:
                if transplanted.exists():transplanted.unlink()
        finally:
            if previous is None:os.environ.pop('MAALIMBUS_DIAGNOSTIC_PHASE',None)
            else:os.environ['MAALIMBUS_DIAGNOSTIC_PHASE']=previous
        report = dict(controller_created=False, device_inputs=0, frozen=frozen,
                      dependency_file_differences=differences, base_library_member_differences=zip_differences)
        (ROOT/'build/minimal-frozen-socket-diagnostic.json').write_text(
            json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
