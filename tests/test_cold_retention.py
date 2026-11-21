"""Shared diagnostic authority, exact survivors and interrupted rewrite recovery."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest

from maalimbus import cold_retention as cold,native_image_archive as archive,capture_retention as retention
from maalimbus.native_evidence import frame_reference
from test_map_diagnostic_retention import chain,save


def corpus(tmp_path,monkeypatch):
    run,rows=chain(tmp_path);originals={};entries=[]
    for i,p in enumerate(sorted(run.glob('frame-*.json'))):
        png=p.with_suffix('.png')
        # Exact trailing bytes are part of the original PNG identity. Random
        # payload ensures removing an original has measurable physical gain.
        pixels=png.read_bytes()+np.random.default_rng(i).bytes(100_000)+b'padding'*10_000
        png.write_bytes(pixels);data=json.loads(p.read_bytes());data['image_sha256']=archive.sha(pixels)
        p.write_text(json.dumps(data));originals[png.relative_to(tmp_path).as_posix()]=pixels
        entries.append(dict(path=png.relative_to(tmp_path).as_posix(),bytes=len(pixels),
                            sha256=data['image_sha256'],record_sha256=archive.sha(p.read_bytes())))
    save(run,rows)
    raw={p.relative_to(tmp_path).as_posix() for group in retention.diagnostic_groups(tmp_path)
         for p,_,_ in group}
    monkeypatch.setattr(archive,'candidates',lambda root:entries)
    assert archive.compact(tmp_path)['files']==5
    assert all(not (tmp_path/name).exists() for name in originals)
    return run,originals,raw


def test_cold_consumer_uses_the_same_roles_and_preserves_exact_survivor_identity(tmp_path,monkeypatch):
    run,originals,raw=corpus(tmp_path,monkeypatch)
    logical=set().union(*cold._eligible(tmp_path,None));assert logical==raw
    before={p:p.read_bytes() for p in run.glob('*.json')};journal=(run/'events.jsonl').read_bytes()
    survivor=run/'frame-0005.json';identity=frame_reference(survivor)[0]
    result=cold.reclaim(tmp_path)
    assert result['containers']==1 and result['freed_bytes']>0
    assert set(result['retired'])==logical and len(logical)==4
    assert all(p.read_bytes()==body for p,body in before.items())
    assert (run/'events.jsonl').read_bytes()==journal
    assert frame_reference(survivor)[0]==identity
    assert archive.read_png(survivor.with_suffix('.png'))==originals[survivor.with_suffix('.png').relative_to(tmp_path).as_posix()]
    for name in logical:
        with pytest.raises(FileNotFoundError):archive.read_png(tmp_path/name)
    assert archive.verify_all(tmp_path)['images']==1
    assert not cold._states(tmp_path)


@pytest.mark.parametrize('owner',['pending','review','source','model'])
def test_independent_roots_keep_cold_originals(tmp_path,monkeypatch,owner):
    run,originals,_=corpus(tmp_path,monkeypatch);target=run/'frame-0002.png'
    if owner=='pending':path=tmp_path/'config/pending.json'
    elif owner=='review':path=tmp_path/'build/learning-review/frames/review/proposal.json'
    elif owner=='model':path=tmp_path/'assets/resource/base/model/neural-model.json'
    else:path=tmp_path/'tests/consumer.py'
    path.parent.mkdir(parents=True,exist_ok=True)
    value=target.relative_to(tmp_path).as_posix()
    path.write_text('FRAME='+repr(value) if owner=='source' else json.dumps({'frame':value}))
    result=cold.reclaim(tmp_path)
    assert value not in result['retired']
    assert archive.read_png(target)==originals[value]


def test_new_reference_after_publication_rolls_back_without_changing_pending(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path)
    publish=archive._publish;changed=[];target=run/'frame-0001.png'
    def inject(root,value):
        publish(root,value)
        if not changed:
            changed.append(True);p=tmp_path/'config/pending.json';p.parent.mkdir()
            p.write_text(json.dumps({'frame':target.relative_to(tmp_path).as_posix(),'pending':True}))
    monkeypatch.setattr(archive,'_publish',inject)
    with pytest.raises(ValueError,match='New reference'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before
    assert json.loads((tmp_path/'config/pending.json').read_bytes())['pending'] is True
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())
    assert not cold._states(tmp_path)


def test_publication_failure_keeps_all_originals(tmp_path,monkeypatch):
    _,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path)
    monkeypatch.setattr(archive,'_publish',lambda *a:(_ for _ in ()).throw(OSError('publish failed')))
    with pytest.raises(OSError,match='publish failed'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


class PowerLoss(BaseException):pass


def test_process_interruption_after_publication_restores_original_mapping(tmp_path,monkeypatch):
    _,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path);publish=archive._publish
    def interrupt(root,value):publish(root,value);raise PowerLoss()
    monkeypatch.setattr(archive,'_publish',interrupt)
    with pytest.raises(PowerLoss):cold.reclaim(tmp_path)
    assert cold._states(tmp_path)
    monkeypatch.setattr(archive,'_publish',publish)
    assert cold.recover(tmp_path)==1
    assert archive.load_index(tmp_path)==before
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())
    assert not cold._states(tmp_path)


def test_unlink_failure_restores_original_mapping(tmp_path,monkeypatch):
    _,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path)
    old=tmp_path/next(iter(before['members'].values()))['archive'];unlink=Path.unlink;failed=[]
    def fail(path,*args,**kwargs):
        if path==old and not failed:failed.append(True);raise OSError('unlink failed')
        return unlink(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail)
    with pytest.raises(OSError,match='unlink failed'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


def test_process_interruption_after_unlink_records_existing_completion_only(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);append=cold._append
    def interrupt(root,row):
        if row['stage']=='committed':raise PowerLoss()
        append(root,row)
    monkeypatch.setattr(cold,'_append',interrupt)
    with pytest.raises(PowerLoss):cold.reclaim(tmp_path)
    monkeypatch.setattr(cold,'_append',append)
    assert cold.recover(tmp_path)==1 and not cold._states(tmp_path)
    name=(run/'frame-0005.png').relative_to(tmp_path).as_posix()
    assert archive.read_png(tmp_path/name)==originals[name]
    assert archive.verify_all(tmp_path)['images']==1


def test_budget_refusal_precedes_publication(tmp_path,monkeypatch):
    _,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path)
    def refuse(*a,**kw):raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(cold.workspace,'require_space',refuse)
    assert cold.reclaim(tmp_path)['containers']==0
    assert archive.load_index(tmp_path)==before and not (tmp_path/cold.JOURNAL).exists()
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


def test_changed_original_metadata_cannot_be_retired(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path)
    p=run/'frame-0001.json';value=json.loads(p.read_bytes());value['note']='changed';p.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='metadata changed'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


def test_metadata_change_after_publication_preserves_external_bytes_and_original_pixels(tmp_path,monkeypatch):
    run,originals,_=corpus(tmp_path,monkeypatch);before=archive.load_index(tmp_path);publish=archive._publish;changed=[]
    path=run/'frame-0005.json'
    def alter(root,value):
        publish(root,value)
        if not changed:
            changed.append(True);data=json.loads(path.read_bytes());data['external_note']='keep';path.write_text(json.dumps(data))
    monkeypatch.setattr(archive,'_publish',alter)
    with pytest.raises(ValueError,match='metadata changed'):cold.reclaim(tmp_path)
    assert archive.load_index(tmp_path)==before
    assert json.loads(path.read_bytes())['external_note']=='keep'
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


def test_cross_container_causal_group_is_not_partially_deleted(tmp_path,monkeypatch):
    _,originals,_=corpus(tmp_path,monkeypatch)
    monkeypatch.setattr(cold,'_eligible',lambda *a:[set(originals)|{'evidence/runtime/foreign/frame-0001.png'}])
    assert cold.reclaim(tmp_path)['containers']==0
    assert all(archive.read_png(tmp_path/name)==body for name,body in originals.items())


def test_corrupt_retirement_receipt_cannot_target_other_project_files(tmp_path,monkeypatch):
    _,_,_=corpus(tmp_path,monkeypatch);victim=tmp_path/'config/keep.json';victim.parent.mkdir();victim.write_text('keep')
    row={'operation':'a'*32,'stage':'intent','before':{'x':{}},'after':{},
         'old_archive':'config/keep.json','new_archive':None}
    cold._append(tmp_path,row)
    with pytest.raises(ValueError,match='Invalid cold'):cold.recover(tmp_path)
    assert victim.read_text()=='keep'
