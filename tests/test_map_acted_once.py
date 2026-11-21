"""被接受过的地图点击，就是这局在地图上的行动权。"""
from __future__ import annotations

import pathlib
import pytest
from maalimbus import runner

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('outcome,acted',[('accepted',True),('unjudged',True),
                                        ('superseded',True),('rejected',False)])
def test_a_sent_map_verdict_records_action_without_inventing_progress(tmp_path,outcome,acted):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    before=dict(loop.result)
    loop._map_verdict(outcome=outcome)
    assert bool(loop.state.get('map_acted_once')) is acted
    assert loop.result==before
    assert loop.device.clicks==[]


def test_the_header_ending_still_reads_the_flag():
    source = (REPO / 'src' / 'maalimbus' / 'runner.py').read_text(encoding='utf-8')
    index = source.index('>= 6 or waited >= 20.0')
    block = source[index:index + 400]
    assert "state.get('map_acted_once')" in block
