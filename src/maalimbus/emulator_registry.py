"""Which emulator the controller is connected to, remembered so it can be started and closed.

The emulator pretask needed its program, its arguments and its ADB address typed in by
hand. This module finds them for the emulator a controller is *already connected to*
and keeps them in the user's data folder (``user-emulators.json``), where the pretask's
"remembered" choice and the "close emulator" task read them.

Nothing is searched for on the disk and no registry is read. The one fact used is that
MuMu ships its ``adb.exe`` beside ``MuMuManager.exe``: the controller already names the
adb it uses, the manager beside it lists its instances with their ADB ports, and the
instance whose port is the controller's address is the one. An adb that has no manager
beside it is another emulator; its address is remembered and nothing more is claimed.

Only read-only manager commands are used to detect (``info``, ``setting -a``). From the
settings only the four display values are kept; the rest (device identifiers among
them) is neither stored nor logged.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

from .emulator_launch import ADDRESS, reachable
from .storage import read_json, write_json

FILE = 'user-emulators.json'
MANAGER = 'MuMuManager.exe'
#: The display this project's pages were measured on (docs/wiki, chapter 6). A different
#: one is reported, never changed here.
VERIFIED_DISPLAY = dict(resolution_width=1280, resolution_height=720, resolution_dpi=240, max_frame_rate=60)
DISPLAY_KEYS = tuple(VERIFIED_DISPLAY)


def local_address(serial):
    """``host:port`` of a local ADB serial, with ``localhost`` written as 127.0.0.1."""
    text = str(serial or '').strip()
    if not ADDRESS.fullmatch(text):
        raise ValueError('Only an emulator on this machine can be remembered: %r' % text)
    host, port = text.rsplit(':', 1)
    return '%s:%d' % ('127.0.0.1' if host == 'localhost' else host, int(port))


def query(manager, *arguments, run=subprocess.run, timeout=20):
    """One read-only manager command, as the JSON it prints."""
    completed = run([str(manager), *arguments], capture_output=True, timeout=timeout,
                    cwd=str(Path(manager).parent))
    if completed.returncode != 0:
        raise ValueError('The emulator manager refused %r' % (arguments[0] if arguments else ''))
    value = json.loads(completed.stdout.decode('utf-8', errors='replace'))
    if not isinstance(value, dict):
        raise ValueError('The emulator manager did not answer with an object')
    return value


def _display(settings):
    kept = {}
    for key in DISPLAY_KEYS:
        try:
            kept[key] = int(float(settings[key]))
        except (KeyError, TypeError, ValueError):
            return None
    return kept


def detect(adb_path, serial, *, ask=query, now=None):
    """The record for the emulator answering at `serial`, through the adb at `adb_path`."""
    address = local_address(serial)
    record = dict(address=address, adb=str(adb_path),
                  detected_utc=(now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat())
    manager = Path(adb_path).parent / MANAGER
    if not manager.is_file():
        return dict(record, kind='unknown', reason='no_emulator_manager_beside_the_adb_in_use')
    listing = ask(manager, 'info', '-v', 'all')
    # One instance is printed as a flat object, several as an object of objects.
    rows = [listing] if 'index' in listing else [row for row in listing.values() if isinstance(row, dict)]
    mine = [row for row in rows
            if '%s:%s' % (row.get('adb_host_ip'), row.get('adb_port')) == address]
    if len(mine) != 1 or not re.fullmatch(r'\d{1,3}', str(mine[0].get('index', ''))):
        return dict(record, kind='unknown', reason='no_single_instance_answers_at_this_address',
                    instances=len(rows))
    index = int(mine[0]['index'])
    try:
        display = _display(ask(manager, 'setting', '-v', str(index), '-a'))
    except (ValueError, OSError, subprocess.SubprocessError):
        display = None
    return dict(record, kind='mumu', name=str(mine[0].get('name') or ''), index=index,
                manager=str(manager), program=str(manager),
                arguments='control -v %d launch' % index,
                shutdown_arguments='control -v %d shutdown' % index, display=display)


def display_differences(record):
    """``{key: [found, verified]}`` for every display value that is not the verified one."""
    display = record.get('display') or {}
    return {key: [display.get(key), wanted] for key, wanted in VERIFIED_DISPLAY.items()
            if display.get(key) != wanted} if display else {}


def load(directory):
    path = Path(directory) / FILE
    if not path.exists():
        return dict(version=1, selected=None, emulators={})
    value = read_json(path)
    if (not isinstance(value, dict) or value.get('version') != 1
            or not isinstance(value.get('emulators'), dict)):
        raise ValueError('Unreadable remembered emulators')
    return value


def remember(directory, record):
    """Keep `record` under its address and make it the one "remembered" means."""
    value = load(directory)
    value['emulators'][record['address']] = record
    value['selected'] = record['address']
    write_json(Path(directory) / FILE, value)
    return value


def remembered(directory, address=None):
    """The remembered emulator at `address`, or the selected one; None when there is none."""
    value = load(directory)
    key = local_address(address) if address else value.get('selected')
    record = value['emulators'].get(key) if key else None
    return record if isinstance(record, dict) else None


def shutdown(record, *, run=subprocess.run, probe=reachable, clock=time.monotonic, sleep=time.sleep,
             wait=60):
    """Ask the emulator's own manager to close this one instance and wait until it is gone.

    The instance is the one detected at the record's address, by its index; no other
    instance and no process is touched. Returns ``{'passed', 'reason', ...}``.
    """
    if record.get('kind') != 'mumu' or not record.get('manager') or not record.get('shutdown_arguments'):
        return dict(passed=False, reason='emulator_has_no_remembered_way_to_close', input_sent=False)
    manager = Path(record['manager'])
    if not manager.is_file():
        return dict(passed=False, reason='emulator_manager_missing', input_sent=False)
    if not probe(record['address']):
        return dict(passed=True, reason='emulator_already_closed', input_sent=False, address=record['address'])
    completed = run([str(manager), *record['shutdown_arguments'].split()], capture_output=True,
                    timeout=30, cwd=str(manager.parent))
    if completed.returncode != 0:
        return dict(passed=False, reason='emulator_manager_refused_shutdown', input_sent=True,
                    address=record['address'])
    deadline = clock() + wait
    while clock() < deadline:
        if not probe(record['address']):
            return dict(passed=True, reason='emulator_closed', input_sent=True, address=record['address'])
        sleep(1)
    return dict(passed=False, reason='emulator_still_answers_after_shutdown', input_sent=True,
                address=record['address'])
