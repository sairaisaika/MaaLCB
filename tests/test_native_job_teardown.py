"""A dead producer cannot leave its host inside an unbounded stop call."""
import threading,time
from types import SimpleNamespace
from maalimbus import jobs


def test_stop_deadline_covers_posting_the_native_request_before_a_job_exists():
    release=threading.Event();entered=threading.Event()
    def post():entered.set();release.wait();return SimpleNamespace(done=True,succeeded=True)
    start=time.monotonic()
    try:
        assert jobs.stop_tasker(SimpleNamespace(post_stop=post),timeout=.03) is False
        assert entered.is_set() and time.monotonic()-start<.5
    finally:release.set()


def test_dead_producer_records_unconfirmed_stop_instead_of_waiting_for_native_ipc(monkeypatch):
    release=threading.Event();native=jobs.call_with_a_deadline
    monkeypatch.setattr(jobs,'call_with_a_deadline',lambda call,**kw:native(call,timeout=.03))
    pending=SimpleNamespace(done=False,succeeded=False)
    def post():release.wait();return SimpleNamespace(done=True,succeeded=True)
    try:
        result=jobs.wait_task(SimpleNamespace(post_stop=post),pending,
            deadline=time.monotonic()+300,producer_alive=lambda:False)
        assert result['producer_exited'] and not result['task_succeeded']
        assert not result['stop_confirmed'] and not result['verified_clear']
        assert result['stop_error']=='the_native_stop_call_did_not_return'
    finally:release.set()
