"""Centring runs once per map branch, and never in observe-only mode."""
from types import SimpleNamespace
import pytest

from maalimbus import runner


def _loop(**settings):
    data = {'rounds': 1, 'interval': 0}
    data.update(settings)
    device = SimpleNamespace(controller=object(), swipe=lambda *a, **k: None)
    loop = runner.MirrorRunner(device, settings=data, directory=None)
    loop.journal = SimpleNamespace(record=lambda *a, **k: None)
    return loop


def test_the_first_map_branch_normalises_and_the_second_does_not(monkeypatch):
    """D290: the zoom is a search bounded by the party still being readable, so the
    branch calls `normalise_view` with a measure and a zoom callable; the contract this
    test owns is that it runs once per floor, not which gesture fires inside."""
    import numpy as np
    loop = _loop()
    calls = []
    monkeypatch.setattr(runner, 'latest_frame',
                        lambda directory: (np.zeros((1080, 1920, 3), np.uint8), 'frame-0001'))
    monkeypatch.setattr(runner, 'party_point', lambda image: (800, 500))
    monkeypatch.setattr(runner, 'normalise_view',
                        lambda measure, zoom, drag, **kw: (calls.append('normalise'),
                                                          {'centred': None, 'zoomed': True,
                                                           'scale_lost_party': False})[1])
    monkeypatch.setattr(loop, 'note', lambda name, **fields: None)
    loop._normalise_view_once({'scene':'MAP'})
    assert calls == ['normalise'] and loop.state['view_normalised'] is True
    loop._normalise_view_once({'scene':'MAP'})
    assert calls == ['normalise']


def test_observe_only_never_touches_the_view(monkeypatch):
    loop = _loop(observe_only=True)
    monkeypatch.setattr(runner, 'pinch_out',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('no zoom')))
    loop._normalise_view_once()
    assert 'view_normalised' not in loop.state


def test_small_capture_normalization_uses_scaled_pinch_before_fresh_observation(tmp_path,monkeypatch):
    import numpy as np
    loop=_loop();calls=[]
    image=np.zeros((720,1280,3),np.uint8)
    record=dict(scene='MAP',size=[1280,720],frame='frame-0001',image_sha256='a'*64)
    monkeypatch.setattr(runner,'frame_for',lambda *a:(image,'frame-0001'))
    monkeypatch.setattr(runner,'party_point',lambda *a:(600,320))
    loop.device.pinch=lambda *args:calls.append(args)
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    def normalise(measure,zoom,drag):
        zoom()
        return dict(centred=True,zoomed=True,scale_lost_party=False)
    monkeypatch.setattr(runner,'normalise_view',normalise)
    loop._normalise_view_once(record)
    assert calls==[((640,360),213,.55,.9)]


@pytest.mark.parametrize('scene',[None,'UNKNOWN','INITIAL_GIFTS','STAR_GRACES',
                                  'DUNGEON_TEAM','SHOP','BATTLE_HUD'])
def test_non_map_icon_cannot_authorize_view_gestures_or_consume_normalization(monkeypatch,scene):
    loop=_loop()
    def unexpected(*args,**kwargs):raise AssertionError('non-map image must not be probed or moved')
    monkeypatch.setattr(runner,'party_point',unexpected)
    monkeypatch.setattr(runner,'pinch_out',unexpected)
    monkeypatch.setattr(runner,'frame_for',unexpected)
    loop._normalise_view_once({'scene':scene,'map_party':[321,385]})
    assert 'view_normalised' not in loop.state
