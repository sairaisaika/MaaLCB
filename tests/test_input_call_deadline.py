"""A request that is never answered must not own the run (D88)."""

import threading
import time

import pytest

from maalimbus import jobs, runner


def test_an_answered_call_returns_its_value():
    box = jobs.call_with_a_deadline(lambda: 7, timeout=1.0)
    assert box == {'answered': True, 'value': 7, 'error': None}


def test_a_call_that_raises_is_reported_not_propagated():
    def boom():
        raise RuntimeError('Maa job failed')

    box = jobs.call_with_a_deadline(boom, timeout=1.0)
    assert box['answered'] is True
    assert isinstance(box['error'], RuntimeError)


def test_a_call_that_never_answers_is_abandoned_at_the_deadline(request):
    started = threading.Event()
    release = threading.Event()
    request.addfinalizer(release.set)

    def hang():
        started.set()
        release.wait()

    began = time.monotonic()
    box = jobs.call_with_a_deadline(hang, timeout=0.2)
    assert box['answered'] is False
    assert box['value'] is None
    assert time.monotonic() - began < 2.0
    assert started.is_set()


def test_an_abandoned_call_cannot_keep_the_process_alive():
    from maalimbus import jobs as module

    worker = None
    box = module.call_with_a_deadline(lambda: time.sleep(0.5), timeout=0.05)
    assert box['answered'] is False
    for candidate in threading.enumerate():
        if candidate.name == 'maalimbus-call':
            worker = candidate
            break
    assert worker is None or worker.daemon


def _device_class():
    class Device(runner.MaaDevice):
        def __init__(self):
            self.controller = self
            self.tasker = None
            self.wait = None
            self.last_input_error = None
            self.route_suspect = False
            self.pipeline_inputs = 0
            self.inputs_abandoned = 0
            self.ended = False

        def _refuse_if_ended(self, what):
            return None

        def _refuse_binding_lost(self, what):
            return None

        def _limit(self, timeout):
            return None

    return Device


def test_an_unanswered_request_is_not_replayed_when_it_can_execute_late(monkeypatch,request):
    """A missing acknowledgement cannot authorize a second physical request."""
    monkeypatch.setattr(runner, 'INPUT_CALL_SECONDS', 0.2)
    Device = _device_class()
    device = Device()
    carried = []
    release=threading.Event()
    completed=threading.Event()
    effects=[]
    request.addfinalizer(release.set)

    def never():
        release.wait()
        effects.append('original')
        completed.set()

    def carrier(what, payload):
        carried.append((what, payload))
        return 'carried'

    device.send_through_a_task = carrier
    began = time.monotonic()
    with pytest.raises(runner.InputDispatchUncertain) as caught:
        device._send('click', never, ('click', 10, 20))
    assert time.monotonic() - began < 3.0
    assert carried == [] and caught.value.input_sent is True
    release.set();assert completed.wait(1)
    assert effects==['original'] and device.input_attempts==1
    with pytest.raises(runner.InputDispatchUncertain):
        device._send('click',lambda:effects.append('duplicate'),('click',10,20))
    assert effects==['original'] and device.input_attempts==1
    assert device.inputs_abandoned == 1
    assert device.route_suspect is True
    assert device.last_input_error == runner.ABANDONED_INPUT


def test_an_abandoned_request_without_a_payload_ends_by_name(monkeypatch,request):
    monkeypatch.setattr(runner, 'INPUT_CALL_SECONDS', 0.2)
    Device = _device_class()
    device = Device()
    release=threading.Event()
    request.addfinalizer(release.set)

    def never():
        release.wait()

    with pytest.raises(runner.RouteLost) as caught:
        device._send('key', never, None)
    assert runner.ABANDONED_INPUT in str(caught.value)
    assert device.inputs_abandoned == 1


def test_a_refused_request_is_still_carried(monkeypatch):
    Device = _device_class()
    device = Device()

    def refuse():
        raise RuntimeError('controller not found [controller_id=]')

    device.send_through_a_task = lambda what, payload: 'carried'
    assert device._send('click', refuse, ('click', 1, 2)) == 'carried'
    assert device.route_suspect is False
    assert 'controller not found' in device.last_input_error


def test_a_non_controller_error_is_not_carried():
    Device = _device_class()
    device = Device()

    def broken():
        raise RuntimeError('something else entirely')

    with pytest.raises(runner.InputDispatchUncertain, match='something else'):
        device._send('click', broken, ('click', 1, 2))


def test_expired_input_budget_posts_nothing():
    device=_device_class()();device.deadline=time.monotonic()-1
    posted=[]
    with pytest.raises(TimeoutError,match='before dispatch'):
        device._send('click',lambda:posted.append('input'),('click',1,2))
    assert posted==[] and getattr(device,'input_attempts',0)==0


def test_uncertain_dispatch_collects_read_only_evidence_and_preserves_pending(tmp_path,monkeypatch):
    pending=tmp_path/'pending.json';pending.write_bytes(b'{"pending":"purchase"}')
    original=pending.read_bytes();events=[];reads=[]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings=dict(interval=0))
    def step():raise runner.InputDispatchUncertain('click; late native acknowledgement')
    def observe(*args,**kwargs):
        reads.append('read')
        return dict(scene='SHOP',frame='frame-0002',image_sha256='a'*64)
    monkeypatch.setattr(loop,'step',step)
    monkeypatch.setattr(loop,'_observe',observe)
    monkeypatch.setattr(loop,'note',lambda event,**fields:events.append(dict(event=event,**fields)))
    result=loop.run(steps=1,interval=0,round_limit=1,deadline=time.monotonic()+60)
    assert result['reason']==runner.INPUT_DISPATCH_UNCERTAIN and result['input_sent'] is True
    assert not result['passed'] and not result['verified_clear'] and loop.device.clicks==[]
    assert reads==['read'] and pending.read_bytes()==original
    assert any(r['event']=='input_dispatch_uncertain' and r['dispatch_status']=='uncertain' for r in events)
    assert any(r['event']=='input_uncertain_observation' and r['transition_verdict']=='unjudged' for r in events)
    assert all(r['event']!='input_withheld' for r in events)


def test_a_caught_input_error_cannot_turn_the_summary_into_success(tmp_path):
    device=runner.FakeDevice();device.dispatch_uncertain=True;device.input_attempts=1
    loop=runner.MirrorRunner(device,directory=tmp_path,settings={})
    loop.artifacts['steps'].append(dict(page_before='MAP',page_after='NODE_PANEL',passed=True))
    result=loop.summary()
    assert not result['passed'] and result['reason']==runner.INPUT_DISPATCH_UNCERTAIN
    assert result['input_sent'] is True and result['native_input_attempts']==1


def test_native_failure_keeps_the_actual_python_call_site(tmp_path,monkeypatch):
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings=dict(interval=0))
    events=[]
    def native_failure():raise OSError('native access violation before any input')
    monkeypatch.setattr(loop,'step',native_failure)
    monkeypatch.setattr(loop,'note',lambda event,**fields:events.append(dict(event=event,**fields)))
    result=loop.run(steps=1,interval=0,round_limit=1)
    assert not result['passed'] and loop.device.clicks==[]
    failure=next(row for row in events if row['event']=='loop_native_or_runtime_error')
    assert failure['error_type']=='OSError' and failure['input_sent'] is False
    assert any('native_failure' in line for line in failure['stack'])
    assert 'native access violation' in failure['stack'][-1]
