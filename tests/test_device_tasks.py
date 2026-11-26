"""Remember the connected emulator, start the remembered one, close the game, close the emulator.

Asked for on 2026-11-26: the emulator pretask needed a program path, arguments and an
address typed in; the user wanted a task that detects the emulator and remembers it, so
that starting it later is a choice and not a form, and tasks that close the game and the
emulator at the end of a list. Shutdown, sleep and quitting the program are MXU's own
special tasks and are not rebuilt here.

Synthetic: the manager, the adb, the probe and the controller are stand-ins. The shapes
of the manager's answers are the ones MuMuManager 6.8.17 printed on the development
machine (``info -v all`` and ``setting -v 1 -a``), with made-up names and ports.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus import device_tasks, emulator_launch, emulator_registry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 26, 22, 0, tzinfo=timezone.utc)
LISTING = {
    '0': dict(index='0', name='Another project', is_android_started=False),
    '1': dict(index='1', name='Game device', adb_host_ip='127.0.0.1', adb_port=16416, is_android_started=True),
}
SETTINGS = dict(resolution_width='1280.000000', resolution_height='720.000000', resolution_dpi='240.000000',
                max_frame_rate='60', phone_imei='000000000000000', player_name='Game device')


def install(tmp_path, manager=True):
    folder = tmp_path / 'emulator' / 'nx_main'
    folder.mkdir(parents=True)
    (folder / 'adb.exe').write_bytes(b'')
    if manager:
        (folder / 'MuMuManager.exe').write_bytes(b'')
    return folder / 'adb.exe'


def manager_answers(listing=LISTING, settings=SETTINGS):
    asked = []

    def ask(manager, *arguments):
        asked.append(arguments)
        return listing if arguments[0] == 'info' else settings
    return ask, asked


def test_the_instance_answering_at_the_controllers_address_is_the_one_remembered(tmp_path):
    adb = install(tmp_path)
    ask, asked = manager_answers()
    record = emulator_registry.detect(adb, '127.0.0.1:16416', ask=ask, now=NOW)
    manager = str(adb.parent / 'MuMuManager.exe')
    assert record == dict(address='127.0.0.1:16416', adb=str(adb), detected_utc='2026-11-26T22:00:00+00:00',
                          kind='mumu', name='Game device', index=1, manager=manager, program=manager,
                          arguments='control -v 1 launch', shutdown_arguments='control -v 1 shutdown',
                          display=dict(resolution_width=1280, resolution_height=720, resolution_dpi=240,
                                       max_frame_rate=60))
    # Only read-only commands, and nothing but the four display values is kept.
    assert asked == [('info', '-v', 'all'), ('setting', '-v', '1', '-a')]
    assert 'imei' not in json.dumps(record) and emulator_registry.display_differences(record) == {}
    # `localhost` is the same machine; a lone instance is printed flat and is still found.
    flat = dict(LISTING['1'])
    assert emulator_registry.detect(adb, 'localhost:16416', ask=manager_answers(flat)[0], now=NOW)['index'] == 1


@pytest.mark.parametrize('listing, reason', [
    ({'0': LISTING['0']}, 'no_single_instance_answers_at_this_address'),
    ({'1': LISTING['1'], '2': dict(LISTING['1'], index='2')}, 'no_single_instance_answers_at_this_address'),
    ({'1': dict(LISTING['1'], index='one')}, 'no_single_instance_answers_at_this_address'),
])
def test_an_address_no_single_instance_owns_is_remembered_as_an_address_only(tmp_path, listing, reason):
    record = emulator_registry.detect(install(tmp_path), '127.0.0.1:16416', ask=manager_answers(listing)[0], now=NOW)
    assert record['kind'] == 'unknown' and record['reason'] == reason and 'program' not in record


def test_an_adb_without_the_manager_beside_it_is_another_emulator_and_nothing_is_asked(tmp_path):
    def never(*arguments):
        raise AssertionError('asked')
    record = emulator_registry.detect(install(tmp_path, manager=False), '127.0.0.1:5555', ask=never, now=NOW)
    assert record['kind'] == 'unknown' and record['reason'] == 'no_emulator_manager_beside_the_adb_in_use'
    with pytest.raises(ValueError, match='this machine'):
        emulator_registry.detect(install(tmp_path / 'b'), '192.168.1.20:5555', ask=never)


def test_a_display_that_is_not_the_verified_one_is_reported_and_never_changed(tmp_path):
    ask, asked = manager_answers(settings=dict(SETTINGS, resolution_width='1920', resolution_height='1080',
                                                 max_frame_rate='120'))
    record = emulator_registry.detect(install(tmp_path), '127.0.0.1:16416', ask=ask, now=NOW)
    assert emulator_registry.display_differences(record) == {
        'resolution_width': [1920, 1280], 'resolution_height': [1080, 720], 'max_frame_rate': [120, 60]}
    assert all(arguments[0] in ('info', 'setting') and '-k' not in arguments for arguments in asked)
    # Settings the manager does not print whole leave the display unknown, not guessed.
    partial, _ = manager_answers(settings=dict(resolution_width='1280'))
    assert emulator_registry.detect(install(tmp_path / 'b'), '127.0.0.1:16416', ask=partial, now=NOW)['display'] is None


def test_remembering_keeps_other_emulators_and_selects_the_latest(tmp_path):
    first = dict(address='127.0.0.1:16416', kind='mumu', name='A', index=1)
    second = dict(address='127.0.0.1:16448', kind='mumu', name='B', index=2)
    assert emulator_registry.remembered(tmp_path) is None
    emulator_registry.remember(tmp_path, first)
    emulator_registry.remember(tmp_path, second)
    assert emulator_registry.remembered(tmp_path) == second
    assert emulator_registry.remembered(tmp_path, 'localhost:16416') == first
    assert emulator_registry.remembered(tmp_path, '127.0.0.1:16480') is None
    (tmp_path / emulator_registry.FILE).write_text('{"version": 2}', encoding='utf-8')
    with pytest.raises(ValueError):
        emulator_registry.remembered(tmp_path)


def test_the_pretask_starts_the_remembered_emulator_with_nothing_typed_in():
    record = dict(address='127.0.0.1:16416', program='Z:/someone/emulator/MuMuManager.exe',
                  arguments='control -v 1 launch', kind='mumu')
    options = emulator_launch.settings(json.dumps({'launch_emulator_source': 'remembered'}), lambda: record)
    assert options == dict(program=record['program'], arguments='control -v 1 launch',
                           address='127.0.0.1:16416', wait_seconds='180', adb='')
    # The record's own adb travels with it, so the pretask can ask Android whether it has booted.
    with_adb = dict(record, adb='Z:/someone/emulator/adb.exe')
    assert emulator_launch.settings(json.dumps({'launch_emulator_source': 'remembered'}),
                                    lambda: with_adb)['adb'] == 'Z:/someone/emulator/adb.exe'
    # Manual entry, with and without the new choice in front of it, reads the four fields.
    typed = dict(program='Z:/x.exe', arguments='', address='127.0.0.1:16384', wait_seconds='60')
    for argument in ({'launch_emulator_source': 'manual', 'launch_emulator': typed}, {'launch_emulator': typed}):
        assert emulator_launch.settings(json.dumps(argument), lambda: record) == typed
    with pytest.raises(ValueError):
        emulator_launch.settings(json.dumps({'launch_emulator_source': 'guess'}))


def test_nothing_remembered_is_a_refusal_with_its_own_reason_and_nothing_is_started():
    printed = []

    def run(options):
        raise AssertionError('started')
    for loader in (None, lambda: None, lambda: dict(kind='unknown')):
        code = emulator_launch.main([json.dumps({'launch_emulator_source': 'remembered'})], run=run,
                                    out=printed.append, remembered=loader)
        assert code == 1 and json.loads(printed[-1])['reason'] == 'emulator_not_remembered'


class Controller:
    def __init__(self, serial='127.0.0.1:16416', adb='Z:/someone/emulator/adb.exe', kind='adb'):
        self.info = dict(type=kind, adb_path=adb, adb_serial=serial)
        self.stopped = []

    def post_stop_app(self, package):
        self.stopped.append(package)
        return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True), succeeded=True, done=True)


class Journal:
    def __init__(self):
        self.rows = []

    def record(self, event, **fields):
        self.rows.append((event, fields))


def test_the_detect_task_saves_the_record_and_tells_the_player_what_it_found(tmp_path):
    record = dict(address='127.0.0.1:16416', kind='mumu', name='Game device', index=1,
                  display=dict(resolution_width=1280, resolution_height=720, resolution_dpi=240, max_frame_rate=60))
    journal = Journal()
    result = device_tasks.detect_emulator(Controller(), tmp_path, journal, detect=lambda adb, serial: record)
    assert result['passed'] and result['reason'] == 'emulator_remembered' and not result['input_sent']
    assert 'Game device' in result['message'] and '1280×720' in result['message'] and '注意' not in result['message']
    assert emulator_registry.remembered(tmp_path) == record and journal.rows[0][0] == 'emulator_remembered'
    other = dict(record, display=dict(record['display'], resolution_width=1920, resolution_height=1080))
    warned = device_tasks.detect_emulator(Controller(), tmp_path, Journal(), detect=lambda adb, serial: other)
    assert warned['display_differences'] and '注意' in warned['message']
    unknown = dict(address='127.0.0.1:5555', kind='unknown', reason='no_emulator_manager_beside_the_adb_in_use')
    plain = device_tasks.detect_emulator(Controller('127.0.0.1:5555'), tmp_path, Journal(),
                                         detect=lambda adb, serial: unknown)
    assert plain['passed'] and plain['reason'] == 'emulator_address_remembered_without_a_way_to_start_it'


def test_closing_the_game_is_confirmed_by_what_is_in_front(monkeypatch):
    monkeypatch.setattr(device_tasks, 'dispatch', lambda controller, job, timeout=None: None)
    package = device_tasks.PACKAGE
    seen = iter(['mCurrentFocus=Window{1 u0 %s/Activity}' % package, 'mCurrentFocus=Window{2 u0 launcher/Home}'])
    controller = Controller()
    result = device_tasks.close_game(controller, Journal(), check_any=lambda adb, serial: next(seen), pause=lambda s: None)
    assert result['passed'] and result['reason'] == 'game_closed' and controller.stopped == [package]
    stuck = device_tasks.close_game(Controller(), Journal(), rounds=3, pause=lambda s: None,
                                    check_any=lambda adb, serial: 'mCurrentFocus=Window{1 u0 %s/Activity}' % package)
    assert not stuck['passed'] and stuck['reason'] == 'game_still_in_front_after_stop'


def test_only_the_remembered_instance_at_the_connected_address_is_closed(tmp_path):
    adb = install(tmp_path)
    manager = str(adb.parent / 'MuMuManager.exe')
    record = dict(address='127.0.0.1:16416', kind='mumu', name='Game device', index=1, manager=manager,
                  shutdown_arguments='control -v 1 shutdown')
    emulator_registry.remember(tmp_path, record)
    # Not remembered at this address: refused before anything runs.
    refused = device_tasks.close_emulator(Controller('127.0.0.1:16448'), tmp_path, Journal(),
                                          shutdown=lambda record: pytest.fail('ran'))
    assert not refused['passed'] and refused['reason'] == 'emulator_not_remembered'
    ran, answering = [], [True, True, False]

    def run(command, **kwargs):
        ran.append(command)
        return SimpleNamespace(returncode=0)
    clock = iter(range(100))
    result = emulator_registry.shutdown(record, run=run, probe=lambda address: answering.pop(0),
                                        clock=lambda: next(clock), sleep=lambda seconds: None)
    assert result == dict(passed=True, reason='emulator_closed', input_sent=True, address='127.0.0.1:16416')
    assert ran == [[manager, 'control', '-v', '1', 'shutdown']]
    # Already closed, a record without a way to close, and a manager that refuses.
    assert emulator_registry.shutdown(record, run=run, probe=lambda address: False)['reason'] == 'emulator_already_closed'
    assert emulator_registry.shutdown(dict(address='127.0.0.1:5555', kind='unknown'))['reason'] == \
        'emulator_has_no_remembered_way_to_close'
    refusing = emulator_registry.shutdown(record, run=lambda command, **k: SimpleNamespace(returncode=1),
                                          probe=lambda address: True)
    assert not refusing['passed'] and refusing['reason'] == 'emulator_manager_refused_shutdown'
    still = emulator_registry.shutdown(record, run=run, probe=lambda address: True, clock=iter(range(0, 1000, 30)).__next__,
                                       sleep=lambda seconds: None)
    assert not still['passed'] and still['reason'] == 'emulator_still_answers_after_shutdown'


def test_a_device_task_on_the_wrong_controller_is_a_named_refusal(tmp_path):
    for task in device_tasks.TASKS:
        result = device_tasks.run(task, Controller(kind='win32'), tmp_path, Journal())
        assert not result['passed'] and result['reason'] == 'device_task_refused' and not result['input_sent']


def test_the_interface_pipeline_and_translations_carry_the_three_tasks():
    interface = json.loads((ROOT / 'assets/interface.json').read_text(encoding='utf-8'))
    nodes = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_text(encoding='utf-8'))
    from maalimbus.task_preferences import TASKS
    for task in device_tasks.TASKS:
        entry = next(row for row in interface['task'] if row['name'] == task)
        assert entry['controller'] == ['mumu-adb'] and entry['default_check'] is False
        assert nodes[entry['entry']]['custom_action_param'] == dict(task=task) and task in TASKS
        for locale in ('zh_cn', 'en_us', 'ja_jp'):
            texts = json.loads((ROOT / 'assets/i18n' / (locale + '.json')).read_text(encoding='utf-8'))
            assert texts.get(entry['label'][1:]) and texts.get(entry['description'][1:]), (locale, task)
    for locale in ('zh_cn', 'en_us', 'ja_jp'):
        texts = json.loads((ROOT / 'assets/i18n' / (locale + '.json')).read_text(encoding='utf-8'))
        for key in ('launch_emulator_source', 'launch_emulator_source_description',
                    'launch_emulator_source_remembered', 'launch_emulator_source_manual'):
            assert texts.get(key), (locale, key)
