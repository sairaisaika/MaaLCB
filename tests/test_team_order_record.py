"""When a team follows the game's own order, the run writes down what it read.

The user asked (2026-11-23) for a record of the deployment order with its screenshot,
after two settings for typing or ticking an order proved clumsier than the game's own
team screen. The record is how a player checks which order a run used.
"""
from datetime import datetime, timezone

from maalimbus import team_order_record
from maalimbus.storage import SINNERS, read_json

NOW = datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc)
# The number printed on each of the twelve cards, in roster order: Hong Lu (card 6) is
# first, Ishmael (card 8) second, Heathcliff (card 7) third, then the rest by roster.
BADGES = [4, 5, 6, 7, 8, 1, 3, 2, 9, 10, 11, 12]


def test_the_order_is_read_from_the_card_numbers_and_saved_with_its_frame(tmp_path):
    entry = team_order_record.record(tmp_path, 2, BADGES, tmp_path / 'run/frame-0012.json', now=NOW)
    assert entry['order'][:4] == ['Hong Lu', 'Ishmael', 'Heathcliff', 'Yi Sang'] and entry['changed'] is True
    assert len(entry['order']) == 12 and set(entry['order']) == set(SINNERS)
    saved = read_json(tmp_path / 'user-team-order-records.json')
    assert saved['version'] == 1 and saved['teams']['2']['positions'][:3] == [6, 8, 7]
    assert saved['teams']['2']['frame'].endswith('frame-0012.json') and saved['teams']['2']['at'].startswith('2026-11-24T02:00')
    assert team_order_record.line(2, entry) == (
        '镜牢队伍 2 的出战顺序跟随游戏：鸿璐、以实玛利、希斯克利夫、李箱、浮士德、堂吉诃德、良秀、默尔索、罗佳、辛克莱、奥提斯、格里高尔'
        '（已记录，截图 frame-0012）')


def test_the_same_order_again_keeps_the_first_record_and_a_new_order_replaces_it(tmp_path):
    team_order_record.record(tmp_path, 2, BADGES, 'frame-0012.json', now=NOW)
    again = team_order_record.record(tmp_path, 2, BADGES, 'frame-0300.json', now=NOW)
    assert again['changed'] is False and again['frame'] == 'frame-0012.json'
    changed = team_order_record.record(tmp_path, 2, list(range(1, 13)), 'frame-0400.json', now=NOW)
    assert changed['changed'] is True and changed['order'] == list(SINNERS)
    team_order_record.record(tmp_path, 5, BADGES, 'frame-0001.json', now=NOW)
    assert sorted(read_json(tmp_path / 'user-team-order-records.json')['teams']) == ['2', '5']


def test_numbers_that_are_not_an_order_record_nothing(tmp_path):
    for badges in ([1, 2, 3], BADGES[:11] + [None], BADGES[:11] + [1], [0] + BADGES[1:], None):
        assert team_order_record.record(tmp_path, 2, badges, 'frame-0001.json', now=NOW) is None
    assert team_order_record.record(tmp_path, '2', BADGES, 'frame-0001.json', now=NOW) is None
    assert not (tmp_path / 'user-team-order-records.json').exists()
