"""A latched backend error keeps its cause and does not become page-read retries."""
from types import SimpleNamespace

import pytest

from maalimbus import runner


FAILURE=dict(callback='MapObservation',node='WindowMapObserve',error_type='ValueError',
             error='Workspace budget exceeded; protected captures retained',traceback='private stack')


@pytest.mark.parametrize('phase',['before','map','battle_hint','battle_after_map','node_raises'])
def test_native_failure_provider_preempts_empty_record_and_timeout_retries(tmp_path,monkeypatch,phase):
    failure=dict(FAILURE) if phase=='before' else None
    records=[];calls=[]
    def run_node(tasker,name,deadline):
        nonlocal failure
        calls.append(name)
        if phase=='battle_after_map' and name=='WindowMapObserve':
            records.append(dict(scene='BATTLE_HUD'))
            return dict(task_succeeded=True)
        failure=dict(FAILURE)
        if phase=='node_raises':raise runner.ReadNeverReturned('node did not return')
        return dict(task_succeeded=False)
    monkeypatch.setattr(runner,'run_node',run_node)
    monkeypatch.setattr(runner,'events',lambda directory,event:list(records) if event=='map_observed' else [])
    observer=runner.MaaObserver(SimpleNamespace(tasker=object()),tmp_path,
                               failure_provider=lambda:failure)
    with pytest.raises(runner.ObservationCallbackFailed,match='Workspace budget exceeded') as caught:
        observer.observe(battle_hint=phase=='battle_hint')
    assert len(calls)==(0 if phase=='before' else 2 if phase=='battle_after_map' else 1)
    assert caught.value.reason=='native_observation_callback_failed'
    assert 'traceback' not in caught.value.failure


def test_loop_stops_once_with_cause_and_preserves_successful_input_count(tmp_path):
    events=[]
    journal=SimpleNamespace(record=lambda event,**fields:events.append(dict(event=event,**fields)))
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,journal=journal,
                             settings=dict(interval=0,stall_seconds=0,progress_seconds=0))
    calls=[];loop.artifacts['clicks_sent']=15
    def step():
        calls.append(1);raise runner.ObservationCallbackFailed(FAILURE)
    loop.step=step
    result=loop.run(steps=5,interval=0)
    assert len(calls)==1 and not loop.device.clicks
    assert result['reason']=='native_observation_callback_failed' and not result['passed']
    assert result['clicks_sent']==15 and 'Workspace budget exceeded' in result['error']
    assert result['callback_failure']['error_type']=='ValueError'
    assert not any(row['event']=='loop_read_failed' for row in events)
