"""Start the Android emulator before the controller connects, and wait until it answers.

This is the project's ProjectInterface ``pretask``: MXU runs it as an external process
before it looks for the ADB device (the model is MaaEnd's PC launch pretask, which
starts the game host and does its own readiness wait).  MXU does not wait for a device
after a pretask, so the wait is done here.

The program to start and the ADB address are the user's own settings; nothing is
searched for, guessed or downloaded.  An emulator that already answers is left alone.
Readiness is a TCP connection to the ADB address: the emulator's ADB service listening
is what the controller needs next, and it needs no ``adb`` executable to check.

Exit status of ``main``: 0 when the address answers, 1 otherwise, with the reason named.
"""
import json
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path

OPTION = 'launch_emulator'
#: The choice above the four fields: 'manual' uses them, 'remembered' uses what the
#: "detect emulator" task saved. MXU passes a select option as its case name and adds
#: the options nested under that case (read from MXU 2.7.1's own serializer).
SOURCE = 'launch_emulator_source'
REMEMBERED_WAIT = '180'
ADDRESS = re.compile(r'^(127\.0\.0\.1|localhost|\[::1\]):(\d{2,5})$')
SETTLE_SECONDS = 5


def reachable(address, timeout=1.0):
    """Whether something accepts a TCP connection on the emulator's ADB address."""
    host, port = address.rsplit(':', 1)
    try:
        with socket.create_connection((host.strip('[]'), int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def booted(adb, address, run=subprocess.run):
    """Whether Android at `address` says it has finished booting, asked through `adb`.

    The ADB port answers seconds before Android is usable, and MXU connects its
    controller the moment a pretask returns: live 2026-11-26, the user's own Start ran
    this pretask (exit 0 after 8 s), MXU then tried to connect three times within four
    seconds, failed, and the task list never began. The port had answered 4 and 14
    seconds before ``sys.boot_completed`` turned 1 in the two starts measured that day.
    Read-only: ``adb connect`` and one ``getprop``.
    """
    try:
        run([str(adb), 'connect', address], capture_output=True, timeout=8)
        answer = run([str(adb), '-s', address, 'shell', 'getprop', 'sys.boot_completed'],
                     capture_output=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return False
    return answer.returncode == 0 and answer.stdout.decode('utf-8', errors='replace').strip() == '1'


def adb_for(options):
    """The adb to ask about booting: the remembered one, or ``adb.exe`` beside the program.

    Nothing is searched for. MuMu ships its adb beside the manager the player configures;
    another emulator's layout is not guessed, and without an adb the boot is not awaited.
    """
    named = (options.get('adb') or '').strip('"')
    program = (options.get('program') or '').strip('"')
    for candidate in ([Path(named)] if named else []) + ([Path(program).parent / 'adb.exe'] if program else []):
        if candidate.is_absolute() and candidate.is_file():
            return candidate
    return None


def start_detached(command, cwd):
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def settings(argument, remembered=None):
    """The option values MXU passes as its last argument.

    ``{"launch_emulator": {...}}`` is the form before the source choice existed and the
    form of the 'manual' choice. ``{"launch_emulator_source": "remembered"}`` asks for the
    emulator the "detect emulator" task saved; `remembered` is the callable that loads
    it, and a missing record is a refusal with its own reason, not an empty program.
    """
    if not argument:
        return {}
    value = json.loads(argument)
    if not isinstance(value, dict):
        raise ValueError('Pretask options must be a JSON object')
    source = value.get(SOURCE, 'manual')
    if source not in ('manual', 'remembered'):
        raise ValueError('Unknown emulator source')
    if source == 'remembered':
        record = remembered() if remembered is not None else None
        if not isinstance(record, dict) or not record.get('address'):
            raise LookupError('No emulator has been remembered')
        return dict(program=str(record.get('program') or ''), arguments=str(record.get('arguments') or ''),
                    address=str(record['address']), wait_seconds=REMEMBERED_WAIT,
                    adb=str(record.get('adb') or ''))
    chosen = value.get(OPTION, value)
    if SOURCE in chosen:
        chosen = {}
    if not isinstance(chosen, dict):
        raise ValueError('Emulator launch options must be a JSON object')
    return {key: ('' if item is None else str(item)).strip() for key, item in chosen.items()}


def launch(options, *, probe=reachable, start=start_detached, clock=time.monotonic, sleep=time.sleep,
           boot=booted):
    """Start the configured emulator unless it already answers; wait until it does.

    Returns ``{'passed', 'reason', 'started', ...}``.  Refusals happen before anything is
    started: an address that is not a local ``host:port``, a missing program, a wait
    outside 10..600 seconds.
    """
    address = options.get('address', '')
    if not ADDRESS.fullmatch(address) or not 1 <= int(address.rsplit(':', 1)[1]) <= 65535:
        return dict(passed=False, started=False, reason='emulator_address_invalid',
                    detail='Set the emulator ADB address as 127.0.0.1:PORT, the address MXU connects to.')
    try:
        wait = int(options.get('wait_seconds') or 180)
    except ValueError:
        wait = 0
    if not 10 <= wait <= 600:
        return dict(passed=False, started=False, reason='emulator_wait_invalid',
                    detail='The wait must be a whole number of seconds from 10 to 600.')
    adb = adb_for(options)

    def ready(deadline):
        """Wait for Android itself once the port answers; True at once when no adb is known."""
        if adb is None:
            return True
        while True:
            if boot(adb, address):
                return True
            if clock() >= deadline:
                return False
            sleep(1)

    if probe(address):
        # Answering is not booted: an emulator started a moment ago by hand is waited for too.
        if not ready(clock() + wait):
            return dict(passed=False, started=False, reason='emulator_android_not_booted', address=address,
                        detail='The emulator answers at %s but Android did not finish booting within %d '
                               'seconds.' % (address, wait))
        return dict(passed=True, started=False, reason='emulator_already_reachable', address=address,
                    boot_checked=adb is not None)
    program = options.get('program', '').strip('"')
    if not program:
        return dict(passed=False, started=False, reason='emulator_program_not_configured', address=address,
                    detail='Nothing answers at %s and no emulator program is set. Open the emulator '
                           'yourself, or set its program in this task.' % address)
    path = Path(program)
    if not path.is_absolute() or not path.is_file():
        return dict(passed=False, started=False, reason='emulator_program_missing', address=address,
                    detail='The emulator program must be the full path of an existing file.')
    arguments = shlex.split(options.get('arguments', ''), posix=False)
    start([str(path), *arguments], str(path.parent))
    deadline = clock() + wait
    while clock() < deadline:
        if probe(address):
            if not ready(deadline):
                return dict(passed=False, started=True, reason='emulator_android_not_booted', address=address,
                            detail='The emulator was started and answers at %s, but Android did not finish '
                                   'booting within %d seconds.' % (address, wait))
            sleep(SETTLE_SECONDS)
            return dict(passed=True, started=True, reason='emulator_reachable_after_launch',
                        address=address, boot_checked=adb is not None, settled_seconds=SETTLE_SECONDS)
        sleep(1)
    return dict(passed=False, started=True, reason='emulator_not_reachable', address=address,
                detail='The emulator was started but nothing answered at %s within %d seconds. '
                       'Check the address and the instance the arguments select.' % (address, wait))


def main(arguments, *, run=launch, out=print, remembered=None):
    """``arguments`` is what follows ``--pretask launch_emulator``: at most the option JSON."""
    try:
        result = run(settings(arguments[0] if arguments else '', remembered))
    except LookupError:
        result = dict(passed=False, started=False, reason='emulator_not_remembered',
                      detail='No emulator has been remembered yet. Run the task "Detect and remember the '
                             'emulator" once while the emulator is connected, or choose manual entry.')
    except ValueError as error:
        result = dict(passed=False, started=False, reason='emulator_options_invalid', detail=str(error))
    out('MaaLimbus emulator pretask: %s%s' % (result['reason'],
                                               (' -- ' + result['detail']) if result.get('detail') else ''))
    out(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1
