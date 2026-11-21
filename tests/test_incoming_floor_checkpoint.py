"""Completion facts do not wait for a later successful click."""
import json,shutil
from pathlib import Path
from types import SimpleNamespace
import pytest
from maalimbus.storage import RunStore,write_json
from maalimbus.run_wiring import observe_map_checkpoint

ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'evidence/runtime/packaged-mirror-20261117-120542/frame-0010.json'


def setup(tmp_path):
    frame=tmp_path/'frame-0001.json'
    for suffix in ('.json','.png'):shutil.copyfile(MAP.with_suffix(suffix),frame.with_suffix(suffix))
    store=RunStore(tmp_path/'ledger.json',[SimpleNamespace(slot=2)]);scope=store.start()
    store.data['active'].update(floors=[1],phase='entered');write_json(store.path,store.data)
    return store,scope,frame


def test_native_floor3_records_floor2_without_any_input_or_later_click(tmp_path):
    store,scope,frame=setup(tmp_path)
    assert [(e.kind,e.floor) for e in observe_map_checkpoint(store,scope,frame)]==[('floor_clear',2)]
    assert store.data['active']['floors']==[1,2]
    assert not store.data['active']['victory'] and not store.data['active']['reward']
    original=store.path.read_bytes()
    assert observe_map_checkpoint(store,scope,frame)==[] and store.path.read_bytes()==original


@pytest.mark.parametrize('fault',['foreign','missing_run','changed_png','missing_pack','not_map','entry_pending'])
def test_unverified_checkpoint_never_creates_a_run_or_writes_a_floor(tmp_path,fault):
    store,scope,frame=setup(tmp_path)
    if fault=='foreign':scope='foreign'
    if fault=='missing_run':store.data['active']=None
    if fault=='entry_pending':store.data['active']['phase']='entry_pending'
    if fault=='changed_png':frame.with_suffix('.png').write_bytes(b'changed')
    if fault in ('missing_pack','not_map'):
        record=json.loads(frame.read_text())
        if fault=='missing_pack':record['ocr']=[r for r in record['ocr'] if 'Gluttony' not in r['text']]
        else:record['scene']='NODE_PANEL'
        write_json(frame,record)
    write_json(store.path,store.data);before=store.path.read_bytes()
    try:events=observe_map_checkpoint(store,scope,frame)
    except (OSError,ValueError):events=[]
    assert events==[] and store.path.read_bytes()==before


@pytest.mark.parametrize('observe_only',[False,True])
def test_actual_incoming_runner_handoff_keeps_completion_separate_from_input(tmp_path,monkeypatch,observe_only):
    from test_incoming_handoff import loop_for
    store,scope,frame=setup(tmp_path)
    loop,record=loop_for(tmp_path,monkeypatch,'MAP',observe_only=observe_only)
    # loop_for intentionally replaces its mock record. Restore the original
    # native pair so the domain reader, not the fake observer, proves the floor.
    for suffix in ('.json','.png'):shutil.copyfile(MAP.with_suffix(suffix),frame.with_suffix(suffix))
    record.clear();record.update(json.loads(frame.read_text()))
    loop.store=store;loop.run_id=scope;before=store.path.read_bytes()
    result=loop.step()
    assert result['done'] and not result['input_sent']
    assert store.data['active']['floors']==([1] if observe_only else [1,2])
    if observe_only:assert store.path.read_bytes()==before
