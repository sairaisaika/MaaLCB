"""只能走一格：超过一格的候选不进列表。"""
from __future__ import annotations

import numpy as np
from maalimbus import runner


def test_the_measured_pitch_bounds_the_actual_input_guard(tmp_path,monkeypatch):
    image=np.zeros((1080,1920,3),np.uint8)
    monkeypatch.setattr(runner,'latest_frame',lambda directory:(image,'unit-frame'))
    monkeypatch.setattr(runner,'map_clicks',lambda image,**kw:[
        {'box':[525,425,190,190],'kind':'path_node'},
        {'box':[715,425,190,190],'kind':'path_node'},
        {'box':[905,425,190,190],'kind':'path_node'}])
    monkeypatch.setattr(runner.map_vision,'party_tracked',lambda image,previous=None:((620,520),'primary'))
    monkeypatch.setattr(runner,'party_point',lambda image:(620,520))
    monkeypatch.setattr(runner,'header_chrome',lambda record:None)
    record={'scene':'MAP'}
    runner.candidates_of(tmp_path,record)
    assert record['map_step_reach']['step']==190
    assert record['map_step_reach']['reach']==238
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    loop.state.update(map_party=record['map_party'],map_step_reach=record['map_step_reach'])
    assert loop._map_click_allowed((858,520))
    assert not loop._map_click_allowed((859,520))
    assert not loop._map_click_allowed((1000,520))
    assert loop.device.clicks==[]
