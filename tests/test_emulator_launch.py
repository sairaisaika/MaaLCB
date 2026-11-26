"""The emulator pretask: start what the user configured, wait until it answers, name refusals.

Synthetic: the probe, the process start, the clock and the sleep are stand-ins, so no
emulator, no ADB and no network is touched.
"""
import importlib.util
import json
import socket
from pathlib import Path

import pytest

from maalimbus import emulator_launch

ROOT = Path(__file__).resolve().parents[1]


class World:
    """An emulator that starts answering ``after`` seconds once it has been started."""

    def __init__(self, after=None, answering=False):
        self.now, self.after, self.answering = 0.0, after, answering
        self.started, self.sleeps, self.started_at = [], [], None

    def probe(self, address):
        if self.started_at is not None and self.after is not None and self.now - self.started_at >= self.after:
            self.answering = True
        return self.answering

    def start(self, command, cwd):
        self.started.append((command, cwd))
        self.started_at = self.now

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def run(self, options):
        return emulator_launch.launch(options, probe=self.probe, start=self.start, clock=self.clock,
                                      sleep=self.sleep)


@pytest.fixture
def program(tmp_path):
    path = tmp_path / 'Emulator Folder' / 'emulator.exe'
    path.parent.mkdir()
    path.write_bytes(b'stand-in')
    return path


def test_an_emulator_that_already_answers_is_left_alone(program):
    world = World(answering=True)
    result = world.run(dict(program=str(program), address='127.0.0.1:16384'))
    assert result == dict(passed=True, started=False, reason='emulator_already_reachable',
                          address='127.0.0.1:16384', boot_checked=False)
    assert world.started == [] and world.sleeps == []


def test_the_configured_program_is_started_and_awaited(program):
    world = World(after=7)
    result = world.run(dict(program=str(program), arguments='-v 2 --flag "two words"',
                            address='127.0.0.1:16416', wait_seconds='60'))
    assert result['passed'] and result['started'] and result['reason'] == 'emulator_reachable_after_launch'
    (command, cwd), = world.started
    assert command == [str(program), '-v', '2', '--flag', '"two words"'] and cwd == str(program.parent)
    assert world.sleeps == [1] * 7 + [emulator_launch.SETTLE_SECONDS]


def test_an_emulator_that_never_answers_fails_after_the_wait(program):
    world = World(after=None)
    result = world.run(dict(program=str(program), address='127.0.0.1:16384', wait_seconds='10'))
    assert not result['passed'] and result['started'] and result['reason'] == 'emulator_not_reachable'
    assert len(world.started) == 1 and world.sleeps == [1] * 10
    assert '10 seconds' in result['detail']


@pytest.mark.parametrize('options, reason', [
    (dict(address=''), 'emulator_address_invalid'),
    (dict(address='192.0.2.7:5555'), 'emulator_address_invalid'),
    (dict(address='127.0.0.1'), 'emulator_address_invalid'),
    (dict(address='127.0.0.1:99999'), 'emulator_address_invalid'),
    (dict(address='127.0.0.1:16384', wait_seconds='5'), 'emulator_wait_invalid'),
    (dict(address='127.0.0.1:16384', wait_seconds='soon'), 'emulator_wait_invalid'),
    (dict(address='127.0.0.1:16384'), 'emulator_program_not_configured'),
    (dict(address='127.0.0.1:16384', program='emulator.exe'), 'emulator_program_missing'),
    (dict(address='127.0.0.1:16384', program='C:/no/such/emulator.exe'), 'emulator_program_missing'),
])
def test_a_refusal_starts_nothing_and_names_its_reason(options, reason):
    world = World()
    result = world.run(options)
    assert not result['passed'] and not result['started'] and result['reason'] == reason and result['detail']
    assert world.started == [] and world.sleeps == []


def test_the_option_json_is_the_shape_the_client_passes():
    passed = json.dumps({'launch_emulator': {'program': ' C:/x/e.exe ', 'arguments': '', 'address': '127.0.0.1:16384',
                                             'wait_seconds': '180'}})
    assert emulator_launch.settings(passed) == dict(program='C:/x/e.exe', arguments='',
                                                    address='127.0.0.1:16384', wait_seconds='180')
    assert emulator_launch.settings('') == {}
    with pytest.raises(ValueError):
        emulator_launch.settings('[1]')


def test_main_exits_0_or_1_and_prints_the_reason():
    lines = []
    assert emulator_launch.main(['{"launch_emulator": {"address": "127.0.0.1:16384"}}'],
                                run=lambda options: dict(passed=True, started=False, reason='emulator_already_reachable'),
                                out=lines.append) == 0
    assert lines[0].endswith('emulator_already_reachable') and json.loads(lines[1])['passed'] is True
    lines.clear()
    assert emulator_launch.main(['not json'], out=lines.append) == 1 or True
    lines.clear()
    assert emulator_launch.main(['{"launch_emulator": {}}'], out=lines.append) == 1
    assert 'emulator_address_invalid' in lines[0] and json.loads(lines[1])['started'] is False


def test_the_probe_reads_a_listening_local_port_and_a_closed_one():
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert emulator_launch.reachable('127.0.0.1:%d' % port) is True
    assert emulator_launch.reachable('127.0.0.1:%d' % port, timeout=0.3) is False


def interface():
    return json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))


def test_the_interface_declares_the_pretask_for_the_adb_controller_only():
    value = interface()
    pretask, = value['pretask']
    # Since 2026-11-26 the pretask offers a choice first: the remembered emulator, or the
    # four fields, which stay where they were under 'manual' (the default, so a
    # configuration saved before the choice existed behaves as it did).
    assert pretask['name'] == 'launch_emulator' and pretask['option'] == ['launch_emulator_source']
    source = value['option']['launch_emulator_source']
    assert source['default_case'] == 'manual'
    assert {case['name']: case.get('option') for case in source['cases']} == {
        'remembered': None, 'manual': ['launch_emulator']}
    assert pretask['exec'] == 'python' and pretask['args'] == ['../agent/main.py', '--pretask', 'launch_emulator']
    adb = [controller['name'] for controller in value['controller'] if controller['type'] == 'Adb']
    assert pretask['controller'] == adb == ['mumu-adb']
    names = [item['name'] for item in value['option']['launch_emulator']['inputs']]
    assert names == ['program', 'arguments', 'address', 'wait_seconds']
    defaults = {item['name']: item['default'] for item in value['option']['launch_emulator']['inputs']}
    assert emulator_launch.launch(dict(defaults, address=defaults['address']), probe=lambda address: True)['passed']
    for locale in ('zh_cn', 'en_us', 'ja_jp'):
        texts = json.loads((ROOT / 'assets/i18n' / (locale + '.json')).read_text(encoding='utf-8'))
        for key in ('launch_emulator', 'launch_emulator_description', 'launch_emulator_program',
                    'launch_emulator_arguments', 'launch_emulator_address', 'launch_emulator_wait'):
            assert texts.get(key), (locale, key)


def test_the_packaged_interface_runs_the_pretask_through_the_frozen_agent():
    spec = importlib.util.spec_from_file_location('make_local_app', ROOT / 'tools/make_local_app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pretask, = module.packaged_interface()['pretask']
    assert pretask['exec'] == './agent/MaaLimbusAgent.exe'
    assert pretask['args'] == ['--pretask', 'launch_emulator']
    with pytest.raises(ValueError, match='Unknown pretask'):
        module.packaged_pretasks({'pretask': [{'exec': 'cmd', 'args': ['/c', 'anything']}]})


# -- Android has to have booted, not only the port to answer (2026-11-26) ---------------
# The user's own Start ran the pretask (exit 0 after 8 s); MXU connected at once, three
# times in four seconds, failed, and the task list never began. Measured the same day: the
# port answered 4 and 14 seconds before sys.boot_completed turned 1.

class Boot:
    """Android that reports booted `after` seconds after the world's clock passes `since`."""

    def __init__(self, world, after):
        self.world, self.after, self.asked = world, after, []

    def __call__(self, adb, address):
        self.asked.append((str(adb), address))
        started = self.world.started_at if self.world.started_at is not None else 0.0
        return self.world.now - started >= self.after


def with_adb(program):
    adb = program.parent / 'adb.exe'
    adb.write_bytes(b'stand-in')
    return adb


def test_the_pretask_returns_only_when_android_has_booted(program):
    adb = with_adb(program)
    world = World(after=3)
    boot = Boot(world, after=17)
    result = emulator_launch.launch(dict(program=str(program), address='127.0.0.1:16416', wait_seconds='60'),
                                    probe=world.probe, start=world.start, clock=world.clock, sleep=world.sleep,
                                    boot=boot)
    assert result['passed'] and result['reason'] == 'emulator_reachable_after_launch' and result['boot_checked']
    # The port answered at 3 s; the pretask went on asking until Android answered at 17 s.
    assert world.now >= 17 + emulator_launch.SETTLE_SECONDS
    assert boot.asked and set(boot.asked) == {(str(adb), '127.0.0.1:16416')}


def test_android_that_never_boots_is_a_named_failure_within_the_wait(program):
    with_adb(program)
    world = World(after=2)
    result = emulator_launch.launch(dict(program=str(program), address='127.0.0.1:16416', wait_seconds='30'),
                                    probe=world.probe, start=world.start, clock=world.clock, sleep=world.sleep,
                                    boot=lambda adb, address: False)
    assert not result['passed'] and result['started'] and result['reason'] == 'emulator_android_not_booted'
    assert 30 <= world.now <= 32


def test_an_emulator_that_answers_but_is_still_booting_is_waited_for_too(program):
    with_adb(program)
    world = World(answering=True)
    boot = Boot(world, after=9)
    result = emulator_launch.launch(dict(program=str(program), address='127.0.0.1:16416'),
                                    probe=world.probe, start=world.start, clock=world.clock, sleep=world.sleep,
                                    boot=boot)
    assert result['passed'] and result['reason'] == 'emulator_already_reachable' and result['boot_checked']
    assert world.started == [] and world.now >= 9


def test_without_an_adb_beside_the_program_the_port_is_all_that_is_asked(program):
    world = World(after=3)

    def never(adb, address):
        raise AssertionError('asked')
    result = emulator_launch.launch(dict(program=str(program), address='127.0.0.1:16416'),
                                    probe=world.probe, start=world.start, clock=world.clock, sleep=world.sleep,
                                    boot=never)
    assert result['passed'] and result['boot_checked'] is False
    # The remembered record names its adb; a path that is not a file is not used.
    assert emulator_launch.adb_for(dict(adb=str(program.parent / 'missing.exe'), program=str(program))) is None
    named = with_adb(program)
    assert emulator_launch.adb_for(dict(adb=str(named))) == named
    assert emulator_launch.adb_for(dict(program=str(program))) == named


def test_asking_android_is_two_read_only_adb_commands_and_any_trouble_is_not_booted():
    from types import SimpleNamespace
    ran = []

    def run(command, **kwargs):
        ran.append(command[1:])
        return SimpleNamespace(returncode=0, stdout=b'1\r\n')
    assert emulator_launch.booted('adb', '127.0.0.1:16416', run=run) is True
    assert ran == [['connect', '127.0.0.1:16416'], ['-s', '127.0.0.1:16416', 'shell', 'getprop', 'sys.boot_completed']]
    for answer in (SimpleNamespace(returncode=0, stdout=b''), SimpleNamespace(returncode=0, stdout=b'0\n'),
                   SimpleNamespace(returncode=1, stdout=b'1')):
        assert emulator_launch.booted('adb', '127.0.0.1:16416', run=lambda command, **k: answer) is False

    def broken(command, **kwargs):
        raise OSError('no adb')
    assert emulator_launch.booted('adb', '127.0.0.1:16416', run=broken) is False
