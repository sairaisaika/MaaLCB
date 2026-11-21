"""Native IPC TEMP must not add unreserved compression files to the project."""
import os,tempfile,io,tarfile
from pathlib import Path

import pytest

from maalimbus import native_image_archive as archive,workspace
from maalimbus.native_agent import native_temp
from test_native_image_archive import batch


@pytest.mark.parametrize('available',['exact','short'])
def test_actual_native_temp_first_default_use_has_one_publication_peak(monkeypatch,available):
    from scratch_roots import short_root
    with short_root('mc-') as root:
        path,entry,pixels=batch(root,monkeypatch)
        reserve=workspace.require_space;calls=[];limit=None
        with native_temp(root) as ipc,monkeypatch.context() as local:
            local.setattr(tempfile,'tempdir',None)
            before=workspace.size(root)
            def bounded(base,additional,**kwargs):
                nonlocal limit
                if not calls:
                    assert workspace.size(root)==before
                    assert not list(ipc.rglob('batch.tar.xz'))
                    assert os.environ['TEMP']==str(ipc)==os.environ['TMP']
                    limit=before+additional-(1 if available=='short' else 0)
                calls.append((workspace.size(root),additional))
                return reserve(base,additional,budget=limit)
            local.setattr(workspace,'require_space',bounded)
            if available=='short':
                with pytest.raises(ValueError,match='Workspace budget exceeded'):archive.compact(root)
                assert path.with_suffix('.png').read_bytes()==pixels
                assert not (root/archive.INDEX).exists() and not (root/archive.BLOBS).exists()
            else:
                result=archive.compact(root)
                assert result['files']==1 and result['retired_bytes']==len(pixels)
                assert archive.read_png(path.with_suffix('.png'))==pixels
                assert archive.verify_all(root)['images']==1 and workspace.size(root)<=limit
            assert calls and os.environ['TEMP']==str(ipc)


def test_memory_staging_retains_raw_when_publication_refuses(monkeypatch,tmp_path):
    path,entry,pixels=batch(tmp_path,monkeypatch)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    def refuse(*args,**kwargs):raise OSError('Publication storage unavailable')
    monkeypatch.setattr(workspace,'require_space',refuse)
    with pytest.raises(OSError,match='Publication storage unavailable'):archive.compact(tmp_path)
    assert {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


def test_memory_staging_keeps_the_previous_file_staging_archive_bytes(monkeypatch,tmp_path):
    path,entry,pixels=batch(tmp_path,monkeypatch)
    with tempfile.TemporaryDirectory(prefix='mc-format-') as temporary:
        previous=Path(temporary)/'batch.tar.xz'
        with tarfile.open(previous,'w:xz',preset=6) as stream:
            item=tarfile.TarInfo(entry['sha256']+'.png');item.size=len(pixels)
            stream.addfile(item,io.BytesIO(pixels))
        expected=previous.read_bytes()
    result=archive.compact(tmp_path)
    assert result['archive_sha256']==archive.sha(expected)
    row=archive.load_index(tmp_path)['members'][entry['path']]
    assert (tmp_path/row['archive']).read_bytes()==expected
