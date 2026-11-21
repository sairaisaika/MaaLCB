"""A discarded storage-only START proposal cannot consume the battle turn twice."""
import json
from pathlib import Path
import pytest

from maalimbus import runner as runtime,capture_retention
from test_runner import window

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'evidence/runtime/packaged-mirror-20261119-160101'
ASSIGNED=RUN/'frame-0008.json'
FRESH=RUN/'frame-0009.json'


def instance(tmp_path,monkeypatch,*,always=False):
    loop,device=window(tmp_path,[ASSIGNED]+[FRESH]*8,dict(rounds=1,interval=0,battle_rounds=8))
    # Native battle controls/readouts live in the event envelope, not raw PNG
    # metadata. Replay their actual matching-frame producer, never infer these
    # fields from the page name or invent OCR coordinates in the fixture.
    rows=[json.loads(s) for s in (RUN/'events.jsonl').read_text().splitlines()]
    native={r['frame']:r for r in rows if r['event']=='battle_observed'}
    fields=('wave','turn','start_box','auto_assign_buttons','turn_signature')
    read=loop.observer.observe
    def observe(**kwargs):
        source=Path(loop.observer.frames[loop.observer.index])
        record=read(**kwargs)
        envelope=native[source.stem]
        record.update({key:envelope.get(key) for key in fields})
        return record
    monkeypatch.setattr(loop.observer,'observe',observe)
    record=json.loads(ASSIGNED.read_bytes())
    record.update({key:native[ASSIGNED.stem].get(key) for key in fields})
    loop.state.update(battle_sig=(record.get('wave'),record.get('turn')),battle_rounds=7,
                      battle_speed='on',battle_previous='assign')
    calls=[]
    def admit(kind,payload):
        calls.append(kind)
        if len(calls)==1 or always:
            return dict(storage_maintenance=True,before_frame=str(ASSIGNED),before_json_sha256='bound',
                        before_image_sha256=record['image_sha256'],capacity_sequence=len(calls))
        return dict(successor_pairs=2)
    monkeypatch.setattr(loop,'_admit_capacity',admit)
    monkeypatch.setattr(capture_retention,'prune_discarded_plan',lambda *a:0)
    return loop,device,calls


def test_real_assigned_start_survives_storage_refresh_at_the_last_battle_round(tmp_path,monkeypatch):
    loop,device,calls=instance(tmp_path,monkeypatch)
    first=loop.step()
    assert first['waiting'] and not device.clicks and loop.state['battle_rounds']==8
    second=loop.step()
    assert second['input_sent'] and len(device.clicks)==1 and len(calls)==2
    assert loop.artifacts['steps'][-1]['plan']['reason']=='start_button_submits_the_assigned_turn'
    assert loop.state['capacity_reobservations']==0 and loop.state['battle_rounds']==8


def test_ordinary_hud_has_one_progress_writer_and_still_stalls(tmp_path,monkeypatch):
    loop,device,_=instance(tmp_path,monkeypatch)
    monkeypatch.setattr(loop,'_admit_capacity',lambda *a:{})
    loop.state['battle_rounds']=0
    assert loop.step()['input_sent']
    assert loop.state['battle_rounds']==1
    loop.state['battle_rounds']=8
    result=loop.step()
    assert result['done'] and result['stopped']=='battle_progress_stalled'
    assert len(device.clicks)==1


def test_repeated_storage_reads_keep_their_own_three_attempt_bound(tmp_path,monkeypatch):
    loop,device,calls=instance(tmp_path,monkeypatch,always=True)
    for _ in range(3):assert loop.step()['waiting']
    result=loop.step()
    assert result['done'] and result['stopped']=='evidence_capacity_unavailable_before_input'
    assert loop.state['battle_rounds']==8 and len(calls)==4 and not device.clicks


def test_storage_read_keeps_count_but_a_new_turn_resets_it():
    state=dict(battle_sig=('1/1','1'),battle_rounds=8)
    assert runtime.battle_progress(state,('1/1','1'),rounds=8,read_only_refresh=True)=='progress'
    assert state['battle_rounds']==8
    assert runtime.battle_progress(state,('1/1','2'),rounds=8,read_only_refresh=True)=='progress'
    assert state['battle_rounds']==1 and state['battle_sig']==('1/1','2')
    assert runtime.battle_progress(state,('1/1','2'),rounds=1)=='stalled'


def test_storage_blind_read_does_not_reset_or_spend_the_blind_guard():
    state=dict(battle_sig=(None,None),battle_blind=12,battle_rounds=1)
    assert runtime.battle_progress(state,(None,None),rounds=3,read_only_refresh=True)=='progress'
    assert state['battle_blind']==12
    assert runtime.battle_progress(state,(None,None),rounds=3)=='blind_long'


@pytest.mark.parametrize('page,leaves_battle',[
    ('HOME',True),('MAP',True),('BATTLE_TIP',False),('BATTLE_PLANNING',False),
    ('LOADING',False),('UNKNOWN',False)])
def test_progress_lifetime_ends_only_on_an_independent_named_nonbattle_page(tmp_path,monkeypatch,page,leaves_battle):
    loop=runtime.MirrorRunner(runtime.FakeDevice([]),directory=tmp_path,
        settings=dict(observe_only=True,interval=0))
    loop.state.update(battle_sig=('1/1','1'),battle_rounds=8,battle_blind=12,battle_frame_sig='old')
    record=dict(scene=page,ocr=[],size=[1280,720],image_sha256='next-picture',wave='1/1',turn='1')
    monkeypatch.setattr(loop,'_observe',lambda *a,**k:record)
    loop.step()
    if leaves_battle:
        assert loop.state['battle_sig'] is None and loop.state['battle_rounds']==0
        assert not loop.state.get('battle_blind') and not loop.state.get('battle_frame_sig')
    else:
        assert loop.state['battle_sig']==('1/1','1')
        # Planning is a normal HUD observation: it counts once and may stall.
        assert loop.state['battle_rounds']==(9 if page=='BATTLE_PLANNING' else 8)
