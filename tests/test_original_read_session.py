"""Operation-local reuse never substitutes metadata for original byte proof."""
import json
import os

import pytest

from maalimbus import capture_retention as retention
from maalimbus import native_image_archive as archive
from maalimbus.native_evidence import frame_reference
from test_observation_frame import capture


def two_originals(root,monkeypatch):
    paths=[];entries=[];originals=[]
    for n in range(2):
        path,raw=capture(root/'evidence/runtime/closed','frame-%04d'%(n+1))
        pixels=path.with_suffix('.png').read_bytes()+bytes([n])*10000
        path.with_suffix('.png').write_bytes(pixels)
        raw['image_sha256']=archive.sha(pixels);path.write_text(json.dumps(raw))
        entries.append(dict(path=path.with_suffix('.png').relative_to(root).as_posix(),
                            bytes=len(pixels),sha256=archive.sha(pixels),
                            record_sha256=archive.sha(path.read_bytes())))
        paths.append(path);originals.append(pixels)
    expected=[frame_reference(p)[0] for p in paths]
    monkeypatch.setattr(archive,'candidates',lambda root:entries)
    archive.compact(root)
    assert all(not p.with_suffix('.png').exists() for p in paths)
    return paths,originals,expected


def test_one_session_streams_once_binds_originals_and_expires(tmp_path,monkeypatch):
    paths,originals,expected=two_originals(tmp_path,monkeypatch)
    with archive.verified_reads() as session:
        for n in (0,1,0):
            assert archive.read_png(paths[n].with_suffix('.png'))==originals[n]
            assert frame_reference(paths[n])[0]==expected[n]
        with archive.verified_reads() as nested:assert nested is session
        assert session.streams==1 and session.index_validations==1
        assert session.peak_bytes<=session.max_bytes
    assert session.bytes==0 and not session.members and not session.indexes and not session.shapes
    with archive.verified_reads() as fresh:
        assert frame_reference(paths[0])[0]==expected[0]
        assert fresh is not session and fresh.streams==1


def test_cache_hit_rehashes_container_despite_unchanged_size_and_mtime(tmp_path,monkeypatch):
    paths,_,_=two_originals(tmp_path,monkeypatch)
    entry=next(iter(archive.load_index(tmp_path)['members'].values()))
    container=tmp_path/entry['archive'];stamp=container.stat()
    with archive.verified_reads():
        frame_reference(paths[0])
        body=bytearray(container.read_bytes());body[-1]^=1;container.write_bytes(body)
        os.utime(container,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(ValueError,match='archive hash changed'):frame_reference(paths[0])


def test_index_copy_cannot_poison_session_and_changed_disk_is_revalidated(tmp_path,monkeypatch):
    paths,_,expected=two_originals(tmp_path,monkeypatch)
    index_path=tmp_path/archive.INDEX;stamp=index_path.stat()
    with archive.verified_reads() as session:
        index=archive.load_index(tmp_path)
        index['members'].clear()
        assert frame_reference(paths[0])[0]==expected[0]
        body=index_path.read_text();member=next(iter(archive.load_index(tmp_path)['members'].values()))
        index_path.write_text(body.replace(member['sha256'],'0'*64))
        os.utime(index_path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(ValueError,match='member hash changed'):frame_reference(paths[0])
        assert session.index_validations==2


def test_corrupt_raw_and_changed_record_win_over_warm_archive(tmp_path,monkeypatch):
    paths,_,_=two_originals(tmp_path,monkeypatch)
    with archive.verified_reads():
        frame_reference(paths[0])
        paths[0].with_suffix('.png').write_bytes(b'not a PNG')
        with pytest.raises(ValueError,match='binding differs'):frame_reference(paths[0])
        frame_reference(paths[1])
        record=json.loads(paths[1].read_bytes());record['size']=[16,24]
        paths[1].write_text(json.dumps(record))
        with pytest.raises(ValueError,match='binding differs'):frame_reference(paths[1])


def test_bounded_payload_eviction_reopens_without_changing_original_bytes(tmp_path,monkeypatch):
    paths,originals,expected=two_originals(tmp_path,monkeypatch)
    with archive.verified_reads(max_bytes=max(map(len,originals))) as session:
        for n in (0,1,0):assert archive.read_png(paths[n].with_suffix('.png'))==originals[n]
        assert session.streams==3
        assert session.peak_bytes<=session.max_bytes
    with pytest.raises(ValueError,match='bound'):
        with archive.verified_reads(max_bytes=archive.READ_CACHE_BYTES+1):pass


def test_provenance_only_consumers_do_not_decompress_after_payload_eviction(tmp_path,monkeypatch):
    paths,_,expected=two_originals(tmp_path,monkeypatch)
    with archive.verified_reads(max_bytes=0) as session:
        for n in (0,1,0,1):assert frame_reference(paths[n])[0]==expected[n]
        assert session.streams==1 and session.bytes==0 and not session.members
        assert len(session.images)==2
    assert not session.images


def test_storage_progress_requires_a_completed_stream_not_an_unchanged_cache_read(tmp_path,monkeypatch):
    paths,_,_=two_originals(tmp_path,monkeypatch);events=[]
    with archive.verified_reads(on_progress=events.append):
        frame_reference(paths[0]);frame_reference(paths[1]);frame_reference(paths[0])
    assert events==[dict(stage='validated_native_archive',streams=1)]


def test_identity_hit_checks_actual_container_even_with_no_payload_cached(tmp_path,monkeypatch):
    paths,_,_=two_originals(tmp_path,monkeypatch)
    entry=next(iter(archive.load_index(tmp_path)['members'].values()))
    container=tmp_path/entry['archive'];stamp=container.stat()
    with archive.verified_reads(max_bytes=0):
        frame_reference(paths[0]);body=bytearray(container.read_bytes());body[-1]^=1
        container.write_bytes(body);os.utime(container,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(ValueError,match='archive hash changed'):frame_reference(paths[0])


def test_retention_shares_reader_without_changing_plan_eligibility(tmp_path,monkeypatch):
    from maalimbus import deployment_evidence,hud_evidence,viewport_evidence
    paths,_,_=two_originals(tmp_path,monkeypatch)
    directory=tmp_path/'evidence/runtime/current';directory.mkdir()
    monkeypatch.setattr(retention,'_reference_keep',lambda root:set())
    monkeypatch.setattr(deployment_evidence,'diagnostic_index',lambda roots:{})
    monkeypatch.setattr(viewport_evidence,'diagnostic_index',lambda roots:{})
    sessions=[]
    def diagnostics(roots):
        sessions.append(archive._reads.get())
        for path in paths:frame_reference(path)
        return {}
    monkeypatch.setattr(hud_evidence,'diagnostic_index',diagnostics)
    expected=retention._plan(tmp_path,directory,archive.workspace.size(tmp_path)+1,budget=1000)
    actual=retention.plan(tmp_path,directory,archive.workspace.size(tmp_path)+1,budget=1000)
    assert actual==expected
    assert sessions[0] is None and sessions[1].streams==1
    assert sessions[1].index_validations==1 and archive._reads.get() is None


def test_bad_later_member_never_publishes_partially_validated_cache(tmp_path):
    import io
    import tarfile
    pixels=b'first';name=archive.sha(pixels)+'.png';blob=io.BytesIO()
    with tarfile.open(fileobj=blob,mode='w:xz') as handle:
        for member_name,body in ((name,pixels),('a'*64+'.png',b'bad digest')):
            member=tarfile.TarInfo(member_name);member.size=len(body)
            handle.addfile(member,io.BytesIO(body))
    container=tmp_path/archive.BLOBS/'invalid.tar.xz';container.parent.mkdir(parents=True)
    container.write_bytes(blob.getvalue())
    entry=dict(archive=container.relative_to(tmp_path).as_posix(),archive_sha256=archive.sha(blob.getvalue()),
               sha256=archive.sha(pixels),bytes=len(pixels))
    with archive.verified_reads() as session:
        for _ in range(2):
            with pytest.raises(ValueError,match='member hash changed'):archive.archived_bytes(tmp_path,entry)
        assert session.members=={} and session.images=={} and session.streams==2
