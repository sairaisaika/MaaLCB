"""Real finite reclamation work, not elapsed time, reaches the existing watch."""
import json
from pathlib import Path

import pytest

from maalimbus import capture_retention as retention,native_image_archive as archive,runner
from maalimbus.evidence_capacity import EvidenceCapacityUnavailable
from test_capture_retention import run,make_pressure


def planned(root):
    folder=run(root)
    plan=retention.plan(root,folder,26000,budget=make_pressure(root))
    assert len(plan['files'])==2
    return folder,plan


def test_actual_retirement_receipt_refreshes_runner_only_after_durable_work(tmp_path,monkeypatch):
    import os
    folder,plan=planned(tmp_path);events=[];synced=[]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path/'observer',settings={})
    sync=os.fsync
    def fsync(fd):
        sync(fd);synced.append(fd)
    monkeypatch.setattr(os,'fsync',fsync)
    def progress(event):
        n=event['captures'];row=plan['files'][n-1]
        assert not (tmp_path/row['path']).exists()
        trail=[json.loads(s) for s in (folder/'capture-retention.jsonl').read_text().splitlines()]
        assert sum(x['event']=='capture_reclaimed' for x in trail)==n
        assert len(synced)==n+1  # all intents, then each completed receipt
        # Not ahead of now.  Two readings can be equal: before Python 3.13 time.monotonic()
        # on Windows ticks every 15.6 ms, and a strict '<' failed one full run in four.
        assert 'event_heartbeat' not in loop.artifacts or loop.artifacts['event_heartbeat']<=runner.time.monotonic()
        loop._storage_progress(event);events.append(event)
    with archive.verified_reads(on_progress=progress):retention.apply(tmp_path,folder,plan)
    assert events==[dict(stage='reclaimed_native_capture',captures=1),dict(stage='reclaimed_native_capture',captures=2)]
    assert loop.last_event=='evidence_storage_progress' and loop.device.clicks==[]


def test_planning_and_noop_reservation_do_not_fabricate_retirements(tmp_path):
    folder=run(tmp_path);events=[]
    with archive.verified_reads(on_progress=events.append):
        plan=retention.plan(tmp_path,folder,1)
        assert not plan['files']
        assert retention.reserve(folder,1,application_root=tmp_path)['sufficient']
    assert events==[]


@pytest.mark.parametrize('fault',['image','pending','unlink','receipt'])
def test_failed_work_never_refreshes_watch(tmp_path,monkeypatch,fault):
    import os
    folder,plan=planned(tmp_path);events=[]
    target=tmp_path/plan['files'][0]['path'];other=tmp_path/plan['files'][1]['path']
    if fault=='image':target.write_bytes(b'changed')
    elif fault=='pending':
        p=tmp_path/'config/pending.json';p.parent.mkdir();p.write_text(json.dumps(dict(proof=str(target))))
    elif fault=='unlink':
        unlink=Path.unlink
        def fail(p,*a,**k):
            if p==target:raise PermissionError('Cannot unlink actual capture')
            return unlink(p,*a,**k)
        monkeypatch.setattr(Path,'unlink',fail)
    else:
        sync=os.fsync;calls=[]
        def fail(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError('Receipt sync failed')
            return sync(fd)
        monkeypatch.setattr(os,'fsync',fail)
    with archive.verified_reads(on_progress=events.append):
        with pytest.raises((ValueError,OSError)):retention.apply(tmp_path,folder,plan)
    assert not events and other.is_file()
    assert target.with_suffix('.json').is_file()


def test_new_pin_after_first_completed_unit_preserves_next_original(tmp_path):
    folder,plan=planned(tmp_path);events=[];second=tmp_path/plan['files'][1]['path'];saved=second.read_bytes()
    def progress(event):
        events.append(event)
        p=tmp_path/'config/pending.json';p.parent.mkdir();p.write_text(json.dumps(dict(proof=str(second))))
    with archive.verified_reads(on_progress=progress):
        with pytest.raises(ValueError,match='references changed'):retention.apply(tmp_path,folder,plan)
    assert len(events)==1 and second.read_bytes()==saved


def test_original_deadline_still_ends_completed_batch_before_input(tmp_path):
    import time
    folder,plan=planned(tmp_path)
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=tmp_path/'observer',settings={})
    loop.deadline=time.monotonic()-1
    with archive.verified_reads(on_progress=loop._storage_progress):
        with pytest.raises(EvidenceCapacityUnavailable,match='Original run deadline'):retention.apply(tmp_path,folder,plan)
    first,second=[tmp_path/x['path'] for x in plan['files']]
    assert not first.exists() and second.exists() and not loop.device.clicks
    trail=[json.loads(s) for s in (folder/'capture-retention.jsonl').read_text().splitlines()]
    assert len([x for x in trail if x['event']=='capture_reclaimed'])==1
