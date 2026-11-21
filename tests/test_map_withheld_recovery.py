"""A withheld click is not an unresolved game input and cannot block recovery."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from maalimbus import runner
from maalimbus.storage import write_json


@pytest.mark.parametrize('pending',[False,True])
def test_full_step_does_not_reserve_or_supersede_an_input_the_guard_withholds(tmp_path,monkeypatch,pending):
    root=Path(__file__).resolve().parents[1]
    source=root/'evidence/runtime/packaged-mirror-20261117-001519/frame-0098.json'
    assert source.exists(), 'actual failed map record must be retained'
    record=json.loads(source.read_text(encoding='utf8'));record['frame']='frame-0001'
    write_json(tmp_path/'frame-0001.json',record)
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,
                             settings=dict(interval=0,map_tries=4))
    monkeypatch.setattr(loop,'_observe',lambda **kw:record)
    monkeypatch.setattr(loop,'_normalise_view_once',lambda r:r)
    target=[793,381,190,190]
    monkeypatch.setattr(runner,'candidates_of',lambda *a,**kw:('frame-0001.png',[target]))
    monkeypatch.setattr(loop,'_map_click_allowed',lambda point:False)
    monkeypatch.setattr(loop,'_resolve_map_click',lambda page,**kwargs:None)
    if pending:
        loop.state.update(map_pending=target,map_committed=target,map_unjudged={'point':[888,476]},
                          map_click_frame='real-sent-before.json')
    keys=['map_pending','map_committed','map_unjudged','map_click_frame']
    before={key:deepcopy(loop.state.get(key)) for key in keys}
    recovered=[]
    def recover(page,state,entry,plan):
        assert entry['reason']=='map_target_outside_current_step'
        assert {key:state.get(key) for key in keys}==before
        recovered.append(page)
        return loop._result(page,None,False,None,waiting=True)
    monkeypatch.setattr(loop,'_recover',recover)
    result=loop.step()
    assert recovered==['MAP'] and result.get('waiting')
    assert loop.device.clicks==[] and loop.artifacts['clicks_sent']==0
    assert not hasattr(loop,'_clicked_at')


def test_battle_return_rearms_same_floor_normalization_without_clearing_any_pending():
    from maalimbus import map_dispatch
    pending=dict(target=[100,200,190,190],frame='actual-input.json')
    state=dict(view_normalised=True,map_pending=pending,map_committed=[100,200,190,190],scope='same')
    assert not map_dispatch.rearm_after_battle(state,'UNKNOWN')
    assert not map_dispatch.rearm_after_battle(state,'GIFT_PICK')
    assert map_dispatch.rearm_after_battle(state,'BATTLE_HUD')
    assert state['map_pending'] is pending and state['scope']=='same'
    before=deepcopy(state)
    assert map_dispatch.prepare_view_change(state) is None and state==before


def test_real_normalization_entry_rearms_before_its_already_normalized_early_return(tmp_path):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    pending=dict(target=[100,200,190,190],frame='actual-input.json')
    loop.state.update(view_normalised=True,map_pending=pending)
    assert loop._normalise_view_once(dict(scene='BATTLE_HUD')) is None
    assert not loop.state.get('view_normalised') and loop.state['map_pending'] is pending
    assert loop.device.clicks==[]
