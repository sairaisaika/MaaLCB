"""Tasks that act on the device rather than on a game page.

``detect_emulator`` remembers the emulator the controller is connected to, so the
emulator pretask can start it without anything typed in and ``close_emulator`` can close
it. ``close_game`` stops the game. They are ordinary entries of the task list: a player
puts "close game" or "close emulator" after the last task of the night.

None of them reads a game page, so none asks for the page identity the other tasks need;
all three need the Android controller, which names the adb and the address they use.
What the player sees is the one-line ``message`` each result carries.
"""
import subprocess
import time

from . import emulator_registry
from .adb_preflight import PACKAGE, foreground_any
from .jobs import dispatch

TASKS = ('detect_emulator', 'close_game', 'close_emulator')


def _android(controller):
    info = controller.info
    if info.get('type') != 'adb' or not info.get('adb_path') or not info.get('adb_serial'):
        raise ValueError('This task needs the Android controller')
    return info


def detect_emulator(controller, directory, journal, *, detect=emulator_registry.detect):
    info = _android(controller)
    record = detect(info['adb_path'], info['adb_serial'])
    emulator_registry.remember(directory, record)
    differences = emulator_registry.display_differences(record)
    journal.record('emulator_remembered', kind=record['kind'], address=record['address'],
                   name=record.get('name'), index=record.get('index'), reason=record.get('reason'),
                   display=record.get('display'), display_differences=differences, input_sent=False)
    if record['kind'] != 'mumu':
        return dict(passed=True, reason='emulator_address_remembered_without_a_way_to_start_it',
                    input_sent=False, emulator=record,
                    message='已记住模拟器地址 %s，但没认出它是哪个模拟器，所以没法替你启动或关闭它；'
                            '「启动模拟器」请继续用手动填写。' % record['address'])
    shown = record.get('display')
    display = ('' if not shown else '；显示 %d×%d、DPI %d、最高 %d 帧' % (
        shown['resolution_width'], shown['resolution_height'], shown['resolution_dpi'], shown['max_frame_rate']))
    warning = ('。注意：程序是在 1280×720、DPI 240、60 帧下验证的，这台的显示设置不同，页面识别可能受影响'
               if differences else '')
    return dict(passed=True, reason='emulator_remembered', input_sent=False, emulator=record,
                display_differences=differences,
                message='已记住模拟器「%s」（MuMu 第 %d 个实例，%s）%s%s。之后「启动模拟器」选「使用已记住的模拟器」即可。'
                        % (record.get('name') or '未命名', record['index'], record['address'], display, warning))


def close_game(controller, journal, *, check_any=foreground_any, rounds=10, interval=.5, pause=None):
    info = _android(controller)
    before = check_any(info['adb_path'], info['adb_serial'])
    journal.record('game_close_intent', package=PACKAGE, before_foreground=before)
    dispatch(controller, controller.post_stop_app(PACKAGE), timeout=30)
    after = before
    for attempt in range(rounds):
        after = check_any(info['adb_path'], info['adb_serial'])
        if not after or PACKAGE + '/' not in after:
            return dict(passed=True, reason='game_closed', input_sent=True, before_foreground=before,
                        foreground=after, message='游戏已关闭。')
        if attempt + 1 < rounds:
            (pause or time.sleep)(interval)
    return dict(passed=False, reason='game_still_in_front_after_stop', input_sent=True,
                before_foreground=before, foreground=after,
                message='已发送关闭游戏，但游戏仍在前台。')


def close_emulator(controller, directory, journal, *, shutdown=emulator_registry.shutdown):
    info = _android(controller)
    record = emulator_registry.remembered(directory, info['adb_serial'])
    if record is None:
        return dict(passed=False, reason='emulator_not_remembered', input_sent=False,
                    message='还没有记住这台模拟器：请先运行一次「检测模拟器并记住」。')
    journal.record('emulator_close_intent', address=record['address'], kind=record.get('kind'),
                   index=record.get('index'))
    result = shutdown(record)
    messages = dict(
        emulator_closed='模拟器「%s」已关闭。' % (record.get('name') or record['address']),
        emulator_already_closed='模拟器已经是关闭的。',
        emulator_has_no_remembered_way_to_close='记住的这台模拟器没有可用的关闭方式（不是 MuMu 实例）。',
        emulator_manager_missing='找不到记住的模拟器管理程序，请重新运行「检测模拟器并记住」。',
        emulator_manager_refused_shutdown='模拟器管理程序没有接受关闭请求。',
        emulator_still_answers_after_shutdown='已请求关闭，但模拟器在等待时间内仍有应答。')
    return dict(result, message=messages.get(result['reason'], result['reason']))


def run(task, controller, directory, journal):
    """Dispatch one device task; a refusal is a result with a reason, never an exception."""
    try:
        if task == 'detect_emulator':
            return detect_emulator(controller, directory, journal)
        if task == 'close_game':
            return close_game(controller, journal)
        if task == 'close_emulator':
            return close_emulator(controller, directory, journal)
        raise ValueError('Unknown device task')
    except (ValueError, OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        return dict(passed=False, reason='device_task_refused', input_sent=False, error=str(error)[:200],
                    message='任务没有执行：%s' % str(error)[:160])
