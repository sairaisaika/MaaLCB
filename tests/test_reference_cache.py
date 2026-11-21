"""Reference acceleration must still see edits and new pending proof."""
import json
import os

import pytest

from maalimbus import capture_retention, workspace


def test_unchanged_bytes_reuse_immutable_parse_but_missing_file_is_not_cached(tmp_path):
    path=tmp_path/'state.json';path.write_text('{}')
    calls=[]
    def parse(body):
        calls.append(body);return {tmp_path/'proof.png'}
    first=workspace.cached_references(path,tmp_path,'test',parse)
    assert isinstance(first,frozenset)
    assert workspace.cached_references(path,tmp_path,'test',parse)==first
    assert calls==[b'{}']
    path.unlink()
    with pytest.raises(FileNotFoundError):
        workspace.cached_references(path,tmp_path,'test',parse)


@pytest.mark.parametrize('family',['state','report','source'])
def test_same_size_same_timestamp_reference_edit_and_new_file_are_seen(tmp_path,family):
    folder=tmp_path/'evidence/runtime/current';folder.mkdir(parents=True)
    first=folder/'frame-0001.png';second=folder/'frame-0002.png'
    location={'state':'config/pending.json','report':'build/audit.json','source':'docs/case.md'}[family]
    path=tmp_path/location;path.parent.mkdir(parents=True)
    def body(frame):
        relative=frame.relative_to(tmp_path).as_posix()
        return relative if family=='source' else json.dumps({'proof':relative})
    path.write_text(body(first));stamp=path.stat()
    assert first in capture_retention._reference_keep(tmp_path)
    path.write_text(body(second));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert path.stat().st_size==stamp.st_size
    refs=capture_retention._reference_keep(tmp_path)
    assert first not in refs and second in refs
    other=path.with_name('new'+path.suffix);other.write_text(body(first))
    assert first in capture_retention._reference_keep(tmp_path)
    assert second in capture_retention._reference_keep(tmp_path)


def test_reference_families_and_roots_do_not_share_derived_paths(tmp_path):
    path=tmp_path/'proof.json';path.write_text('{}')
    a=workspace.cached_references(path,tmp_path,'a',lambda body:{tmp_path/'a'})
    b=workspace.cached_references(path,tmp_path,'b',lambda body:{tmp_path/'b'})
    c=workspace.cached_references(path,tmp_path/'other','a',lambda body:{tmp_path/'c'})
    assert a=={tmp_path/'a'} and b=={tmp_path/'b'} and c=={tmp_path/'c'}


def test_newly_resolved_reference_paths_are_not_memoized(tmp_path,monkeypatch):
    config=tmp_path/'config';config.mkdir()
    state=config/'pending.json';state.write_text(json.dumps({'proof':'alias/frame-0001.png'}))
    from pathlib import Path
    original=Path.resolve;destination=tmp_path/'outside'
    def resolve(path,*args,**kwargs):
        if path==tmp_path/'alias':return destination
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    assert workspace.protected_evidence(tmp_path)==set()
    destination=tmp_path/'evidence/runtime/new'
    assert destination/'frame-0001.png' in workspace.protected_evidence(tmp_path)


def test_unresolvable_reference_does_not_hide_other_valid_pending_proof(tmp_path,monkeypatch):
    from pathlib import Path
    config=tmp_path/'config';config.mkdir()
    good=tmp_path/'evidence/runtime/current/frame-0001.png'
    (config/'pending.json').write_text(json.dumps({'bad':'invalid/proof.json','good':str(good)}))
    original=Path.resolve
    def resolve(path,*args,**kwargs):
        if path==tmp_path/'invalid':raise OSError('path unavailable')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    assert good in workspace.protected_evidence(tmp_path)


def test_source_reference_window_is_identical_for_lf_and_crlf(tmp_path):
    docs=tmp_path/'docs';docs.mkdir()
    path=docs/'case.md'
    text='evidence/runtime/current\n'+('padding\n'*34)+'frame-1234567890.png'
    path.write_bytes(text.encode())
    expected=capture_retention._reference_keep(tmp_path)
    assert tmp_path/'evidence/runtime/current/frame-1234567890.png' in expected
    path.write_bytes(text.replace('\n','\r\n').encode())
    assert capture_retention._reference_keep(tmp_path)==expected
