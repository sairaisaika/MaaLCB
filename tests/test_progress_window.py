"""The progress watch must be able to fire inside the budgets this project uses (D89)."""

from maalimbus import runner


def test_the_progress_window_is_shorter_than_the_budgets_the_harness_uses():
    best = min(runner.MirrorRunner.PROGRESS_SECONDS, 90.0)
    assert runner.MirrorRunner.PROGRESS_SECONDS <= 120.0
    assert runner.MirrorRunner.PROGRESS_SECONDS <= best


def test_the_measured_silences_justify_the_window():
    # D89's measurement: p99 9.27 s over 25 880 inter-row gaps, and every gap over 60 s in
    # the corpus was a wedge.  The window must sit above the p99 with room, and below the
    # shortest gap a wedge ever showed (421 s).
    assert 30.0 <= runner.MirrorRunner.PROGRESS_SECONDS <= 120.0


def test_the_window_is_still_clamped_by_the_run_it_protects():
    import time

    finite = runner.bounded_limit(runner.MirrorRunner.PROGRESS_SECONDS,
                                  time.monotonic() + 5.0)
    assert finite <= 5.0
    assert runner.bounded_limit(runner.MirrorRunner.PROGRESS_SECONDS, None) == \
        runner.MirrorRunner.PROGRESS_SECONDS


def test_a_short_run_still_gets_a_positive_window():
    import time

    assert runner.bounded_limit(runner.MirrorRunner.PROGRESS_SECONDS,
                                time.monotonic() + 0.5) >= 1.0


def test_watchdog_records_the_blocked_execution_location_without_local_values(tmp_path):
    import json,threading
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    release=threading.Event();ready=threading.Event()
    def blocked_capacity_reader():
        private_local='private-value-must-not-be-emitted'
        loop.artifacts['execution_thread_id']=threading.get_ident();ready.set();release.wait()
        return private_local
    worker=threading.Thread(target=blocked_capacity_reader);worker.start();assert ready.wait(1)
    try:
        record=loop._record_no_progress(90)
        assert any(r['function']=='blocked_capacity_reader' for r in record['execution_stack'])
        assert 'private-value-must-not-be-emitted' not in json.dumps(record)
        assert all(set(r)=={'file','line','function'} for r in record['execution_stack'])
    finally:release.set();worker.join(1)


def test_real_storage_work_refreshes_watchdog_but_cannot_extend_original_run_deadline(tmp_path):
    import time,pytest
    from maalimbus.evidence_capacity import EvidenceCapacityUnavailable
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path,settings={})
    before=time.monotonic();loop._storage_progress(dict(stage='validated_native_archive',streams=1))
    assert loop.artifacts['event_heartbeat']>=before and loop.device.clicks==[]
    loop.deadline=time.monotonic()-1
    with pytest.raises(EvidenceCapacityUnavailable,match='Original run deadline'):
        loop._storage_progress(dict(stage='validated_native_archive',streams=2))
    assert loop.device.clicks==[]
