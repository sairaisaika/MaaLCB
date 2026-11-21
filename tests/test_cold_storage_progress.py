"""Actual completed-work observability cannot invalidate its own byte guard."""
import json,time,sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))

import pytest

from maalimbus import native_image_archive as archive,cold_retention as cold,runner
from maalimbus.evidence_capacity import EvidenceCapacityUnavailable
from test_cold_retention import corpus


def observer(run):
    from recognition import Journal
    return runner.MirrorRunner(runner.FakeDevice(),directory=run,journal=Journal(run),settings={})


def test_real_cold_runner_journal_progress_preserves_snapshot_until_commit(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);loop=observer(run);before=(run/'events.jsonl').read_bytes();pulses=[]
    def activity():
        assert (run/'events.jsonl').read_bytes()==before
        loop._storage_activity();pulses.append(1)
    with archive.verified_reads(on_progress=loop._storage_progress,on_activity=activity):
        result=cold.reclaim(tmp_path)
    assert result['containers']==1 and result['freed_bytes']>0 and pulses
    after=(run/'events.jsonl').read_bytes();assert after.startswith(before)
    events=[json.loads(s) for s in after[len(before):].splitlines()]
    assert [e['stage'] for e in events]==['validated_native_archive','reclaimed_cold_container']
    survivor=run/'frame-0005.png';assert archive.read_png(survivor)==originals[survivor.relative_to(tmp_path).as_posix()]
    assert not cold._states(tmp_path) and not loop.device.clicks


def test_raw_capacity_rechecks_report_activity_without_writing_a_journal_event(tmp_path, monkeypatch):
    from maalimbus import capture_retention as retention, workspace
    from test_capture_retention import run

    directory = run(tmp_path)
    saved_events = (directory / 'events.jsonl').read_bytes()
    activity, progress = [], []
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(tmp_path) + 25_000)

    def checked():
        assert (directory / 'events.jsonl').read_bytes() == saved_events
        activity.append(len(progress))

    with archive.verified_reads(on_progress=progress.append, on_activity=checked):
        result = retention.reserve(directory, 30_000, application_root=tmp_path)

    assert result['sufficient'] and result['files']
    assert activity.count(0) >= 5
    assert [item['stage'] for item in progress] == ['reclaimed_native_capture'] * len(result['files'])
    assert (directory / 'events.jsonl').read_bytes() == saved_events


def test_deferred_progress_is_bounded_nested_and_keeps_callback_owner(tmp_path):
    first=[];second=[];pulses=[]
    with archive.verified_reads(on_progress=first.append,on_activity=lambda:pulses.append(1)) as session:
        with archive.deferred_progress():
            archive.completed_capture_retirement();assert first==[]
            with archive.verified_reads(on_progress=second.append):
                with archive.deferred_progress():
                    for _ in range(30):archive.completed_capture_retirement()
                assert not second
            assert not first and len(session.pending_progress)<=archive.DEFERRED_PROGRESS_STAGES
        assert first==[dict(stage='reclaimed_native_capture',captures=1)]
        assert second==[dict(stage='reclaimed_native_capture',captures=31)] and len(pulses)==31
        assert not session.pending_progress and not session.defer_depth


def test_failed_guard_drops_reports_and_restores_normal_delivery():
    events=[];pulses=[]
    with archive.verified_reads(on_progress=events.append,on_activity=lambda:pulses.append(1)) as session:
        with pytest.raises(ValueError,match='guard failed'):
            with archive.deferred_progress():
                archive.completed_capture_retirement();raise ValueError('guard failed')
        assert not events and not session.pending_progress and not session.defer_depth
        archive.completed_capture_retirement()
    assert events==[dict(stage='reclaimed_native_capture',captures=2)] and len(pulses)==1


def test_deferred_memory_activity_cannot_extend_original_deadline(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);loop=observer(run);before=archive.load_index(tmp_path)
    loop.deadline=time.monotonic()-1
    with archive.verified_reads(on_progress=loop._storage_progress,on_activity=loop._storage_activity):
        with pytest.raises(EvidenceCapacityUnavailable,match='Original run deadline'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before and not loop.device.clicks
    assert all(archive.read_png(tmp_path/n)==b for n,b in originals.items())
    assert not cold._states(tmp_path)


def test_real_role_input_change_is_still_refused_with_all_originals(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);changed=[]
    def activity():
        if not changed:
            changed.append(1)
            with (run/'events.jsonl').open('a') as f:f.write('{"event":"window_intent","point":[10,20]}\n')
    with archive.verified_reads(on_progress=lambda event:None,on_activity=activity):
        with pytest.raises(ValueError,match='role inputs changed'):cold.reclaim(tmp_path)
    assert all(archive.read_png(tmp_path/n)==b for n,b in originals.items())
    assert not cold._states(tmp_path)


def test_memory_activity_override_restores_outer_owner():
    first=[];second=[]
    with archive.verified_reads(on_activity=lambda:first.append(1)):
        with archive.deferred_progress():
            archive.completed_capture_retirement()
            with archive.verified_reads(on_activity=lambda:second.append(1)):archive.completed_capture_retirement()
            archive.completed_capture_retirement()
    assert len(first)==2 and len(second)==1


def test_deferred_progress_requires_existing_operation():
    with pytest.raises(ValueError,match='verified read session'):
        with archive.deferred_progress():pass


def test_many_observer_targets_cannot_grow_deferred_queue_without_bound():
    delivered=[];pulses=[];callbacks=[lambda event,n=n:delivered.append((n,event)) for n in range(20)]
    with archive.verified_reads(on_activity=lambda:pulses.append(1)) as session:
        with archive.deferred_progress():
            for callback in callbacks:
                with archive.verified_reads(on_progress=callback):archive.completed_capture_retirement()
            assert len(session.pending_progress)==archive.DEFERRED_PROGRESS_STAGES
        assert len(delivered)==archive.DEFERRED_PROGRESS_STAGES and len(pulses)==20
        assert [n for n,_ in delivered]==list(range(12,20))


def test_discarded_proposal_witnesses_ignore_no_bytes_and_defer_own_reports(tmp_path,monkeypatch):
    from maalimbus import capture_retention as retention
    from test_capacity_plan_refresh import proposal,save
    archived_run,originals,_=corpus(tmp_path,monkeypatch)
    run,rows,path=proposal(tmp_path);save(run,rows);before=(run/'events.jsonl').read_bytes()
    loop=observer(run);read=retention._reference_keep;injected=[]
    def references(*args,**kwargs):
        if (run/'capture-retention.jsonl').exists() and not injected:
            injected.append(1);target=archived_run/'frame-0005.png'
            assert archive.read_png(target)==originals[target.relative_to(tmp_path).as_posix()]
        return read(*args,**kwargs)
    monkeypatch.setattr(retention,'_reference_keep',references)
    def activity():
        assert (run/'events.jsonl').read_bytes()==before
        loop._storage_activity()
    with archive.verified_reads(max_bytes=0,on_progress=loop._storage_progress,on_activity=activity):
        freed=retention.prune_discarded_plan(run,rows[-1]['before_frame'])
    assert freed>0 and injected and not path.with_suffix('.png').exists()
    assert path.exists() and (run/'frame-0001.png').exists() and not loop.device.clicks
    assert (run/'events.jsonl').read_bytes().startswith(before)


def test_progress_sink_failure_after_cold_commit_does_not_invent_input_or_rollback(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch)
    def failed(event):raise OSError('Progress sink failed after guarded work')
    with archive.verified_reads(on_progress=failed,on_activity=lambda:None):
        with pytest.raises(OSError,match='Progress sink failed'):cold.reclaim(tmp_path)
    assert not cold._states(tmp_path)
    target=run/'frame-0005.png'
    assert archive.read_png(target)==originals[target.relative_to(tmp_path).as_posix()]
