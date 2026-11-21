"""The actual native producer's pixel cache must honor a required new record."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import recognition
from maalimbus import evidence_capacity as capacity,runner
from maalimbus.native_evidence import observation_frame


def prepared(tmp_path,monkeypatch):
    folder=tmp_path/'evidence/runtime/current'
    journal=recognition.Journal(folder,history_maintenance=True)
    reader=recognition.LimbusRecognition('en',journal)
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    monkeypatch.setattr(recognition,'classify',lambda *a:'REWARD_CARD')
    image=np.zeros((480,854,3),np.uint8)
    name=journal.frame(image,[],'REWARD_CARD')
    reader.cache=(hashlib.sha256(image.tobytes()).hexdigest(),[],'REWARD_CARD',name)
    calls=[]
    def read(*args,**kwargs):
        calls.append(1);return SimpleNamespace(all_results=[],filtered_results=[],hit=False)
    context=SimpleNamespace(run_recognition_direct=read)
    return journal,reader,image,name,context,calls


def demand(journal,monkeypatch):
    calls=[]
    def reserve(*args,**kwargs):
        calls.append(1);return dict(storage_maintenance=len(calls)==1)
    monkeypatch.setattr(capacity.capture_retention,'reserve',reserve)
    admission=journal.before_input('plan',('click',10,20))
    assert calls == [1]
    assert admission['reobserve_pairs']==1
    assert admission['successor_pairs']==0 and admission['input_sent'] is False


def test_actual_map_observer_cache_publishes_required_record_then_resumes_reuse(tmp_path,monkeypatch):
    journal,reader,image,old,context,reads=prepared(tmp_path,monkeypatch)
    before={p:p.read_bytes() for p in journal.directory.glob('frame-*')}
    assert reader.observe(context,image)[2]==old and not reads
    demand(journal,monkeypatch)
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='Fresh capture required'):
        journal.before_input('plan',('click',10,20))
    controller=SimpleNamespace(cached_image=image);context.tasker=SimpleNamespace(controller=controller)
    captures=[]
    monkeypatch.setattr(recognition,'screencap',lambda actual,**kw:captures.append(actual))
    action=recognition.MapObservation(reader)
    def run_capture(*_args):
        return dict(task_succeeded=action.run(context,SimpleNamespace(node_name='WindowMapObserve')))
    monkeypatch.setattr(runner,'run_node',run_capture)
    observer=runner.MaaObserver(context,journal.directory,identity_only=True)
    fresh=runner.observe(observer)
    assert len(captures)==1 and reads and fresh['frame']!=old
    assert fresh['scene']=='REWARD_CARD' and fresh['frame_ref']['frame_id']==fresh['frame']
    assert all(p.read_bytes()==body for p,body in before.items())
    assert fresh['image_sha256']==json.loads(before[journal.directory/(old+'.json')])['image_sha256']
    count=len(reads);new=fresh['frame']
    assert reader.observe(context,image)[2]==new and len(reads)==count
    assert len(list(journal.directory.glob('frame-*.json')))==2
    admission=journal.before_input('plan',('click',10,20));assert not admission.get('storage_maintenance')
    assert not capacity.EvidenceCapacity(tmp_path).load()['owner'].get('fresh_capture_required')


def test_normal_cache_reuse_does_not_publish_duplicate_evidence(tmp_path,monkeypatch):
    journal,reader,image,name,context,reads=prepared(tmp_path,monkeypatch)
    for _ in range(3):assert reader.observe(context,image)[2]==name
    assert not reads and len(list(journal.directory.glob('frame-*.json')))==1


def test_foreign_owner_does_not_invalidate_this_journals_cache(tmp_path,monkeypatch):
    journal,reader,image,name,context,reads=prepared(tmp_path,monkeypatch);demand(journal,monkeypatch)
    pool=capacity.EvidenceCapacity(tmp_path);owner=dict(pool.load()['owner'],frame='evidence/runtime/foreign/frame-0001.json')
    pool._resize(pool.load()['bytes'],owner=owner)
    assert not journal.needs_fresh_capture(name)
    assert reader.observe(context,image)[2]==name and not reads


def test_required_read_failure_preserves_original_cache_and_pool(tmp_path,monkeypatch):
    journal,reader,image,name,context,reads=prepared(tmp_path,monkeypatch);demand(journal,monkeypatch)
    before={p:p.read_bytes() for p in journal.directory.glob('frame-*')};pool=capacity.EvidenceCapacity(tmp_path);saved=pool.load()
    context.run_recognition_direct=lambda *a,**k:None
    with pytest.raises(RuntimeError,match='OCR did not return'):reader.observe(context,image)
    assert reader.cache[3]==name and pool.load()==saved
    assert {p:p.read_bytes() for p in journal.directory.glob('frame-*')}==before


def test_required_new_record_keeps_native_binding_and_original_capture_time(tmp_path,monkeypatch):
    journal,reader,image,name,context,reads=prepared(tmp_path,monkeypatch);demand(journal,monkeypatch)
    old=json.loads((journal.directory/(name+'.json')).read_bytes())
    _,_,new=reader.observe(context,image)
    result,ref,_=observation_frame(journal.directory,dict(frame=new,scene='REWARD_CARD'))
    assert ref.frame_id==new and ref.png_sha256==old['image_sha256'] and ref.captured_at!=old['utc']
    assert json.loads((journal.directory/(name+'.json')).read_bytes())==old


def test_changed_pixels_already_follow_normal_publication_path(tmp_path,monkeypatch):
    journal,reader,image,name,context,reads=prepared(tmp_path,monkeypatch);demand(journal,monkeypatch)
    changed=image.copy();changed[0,0,0]=1
    _,_,new=reader.observe(context,changed)
    assert new!=name and reads
    admission=journal.before_input('plan',('click',10,20));assert not admission.get('storage_maintenance')
