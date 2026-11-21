"""Check frozen Maa Agent registration without creating a device controller."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(transport, source_agent=False, console=False, root_cwd=False, agent_exe=None, variant='',
           *, directory=None, data_directory=None, probe=None, timeout_ms=5000,agent_args=()):
    if tuple(agent_args) not in ((),('--capture-profile-probe',)):
        raise ValueError('Only the read-only capture profile diagnostic flag is supported')
    from maa.agent_client import AgentClient
    from maa.library import Library
    from maa.resource import Resource
    Library.open(ROOT / 'dist/MaaLimbus/maafw')
    # The native API binds an ephemeral loopback port atomically. No fixed port
    # or reserve-and-release race, matching MXU's communication compatibility mode.
    client = AgentClient.create_tcp(0) if transport=='tcp' else AgentClient()
    resource = Resource()
    assert client.bind(resource)
    client.set_timeout(timeout_ms)
    directory = (Path(directory) if directory is not None else ROOT / 'build' /
                 ('agent-ipc-' + transport + ('-source' if source_agent else '')
                  + ('-console' if console else '') + ('-root' if root_cwd else '') + variant))
    directory.mkdir(parents=True, exist_ok=True)
    app = ROOT / 'dist/MaaLimbus'
    environment = {**os.environ, 'MAALIMBUS_EVIDENCE': str(directory),
                   'PI_RESOURCE': json.dumps({'name': 'en'}), 'PI_CONTROLLER': '{}',
                   'MAAFW_BINARY_PATH': str(app / 'maafw')}
    if data_directory is not None:
        Path(data_directory).mkdir(parents=True,exist_ok=True)
        environment['MAALIMBUS_DATA_PATH']=str(Path(data_directory).resolve())
    result = dict(transport=transport, controller_created=False, device_inputs=0,
                  passed=False, source_agent=source_agent, console=console, root_cwd=root_cwd)
    with (directory / 'stdout.log').open('w') as stdout, (directory / 'stderr.log').open('w') as stderr:
        command = ([sys.executable, str(ROOT / 'agent/main.py')] if source_agent else
                   [str(agent_exe or app / 'agent/MaaLimbusAgent.exe')]) + list(agent_args) + [client.identifier]
        result['executable'] = command[0]
        process=None
        try:
            process = subprocess.Popen(command,
                                       cwd=ROOT if root_cwd else app, env=environment, stdout=stdout, stderr=stderr,
                                       creationflags=0 if console else getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result['connected'] = client.connect()
            result['actions'] = sorted(client.custom_action_list) if result['connected'] else []
            result['passed'] = result['connected'] and 'limbus_main_task' in result['actions']
            if result['passed'] and probe is not None:
                result['probe']=probe(client,resource,process)
                result['passed']=isinstance(result['probe'],dict) and result['probe'].get('passed') is True
        except Exception as error:
            result.update(passed=False,error_type=type(error).__name__,error=str(error))
        finally:
            result['exit_before_disconnect'] = process.poll() if process is not None else None
            try:
                client.disconnect()
            except Exception as error:
                result.update(passed=False,disconnect_error=str(error))
            if process is not None:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    # Only this owned, input-free verification child is ended
                    # after explicit disconnect; never a live game controller.
                    result.update(passed=False,terminated_after_disconnect=True)
                    process.terminate()
                    process.wait(timeout=5)
                result['agent_exit_code'] = process.returncode
                result['passed']=bool(result['passed'] and result['exit_before_disconnect'] is None
                                      and process.returncode==0)
    if not result['passed']:
        for name in ('stdout','stderr'):
            result[name+'_tail']=(directory/(name+'.log')).read_text(encoding='utf8',errors='replace')[-6000:]
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('ipc', 'tcp'), default='ipc')
    parser.add_argument('--source-agent', action='store_true', help='Diagnostic comparison only; not a packaged acceptance')
    parser.add_argument('--console', action='store_true', help='Diagnostic: omit CREATE_NO_WINDOW')
    parser.add_argument('--root-cwd', action='store_true', help='Diagnostic: use repository cwd')
    parser.add_argument('--agent-exe', type=Path, help='Diagnostic frozen executable; no device is created')
    args = parser.parse_args()
    result = verify(args.transport, args.source_agent, args.console, args.root_cwd,
                    args.agent_exe, '-alternate' if args.agent_exe else '')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
