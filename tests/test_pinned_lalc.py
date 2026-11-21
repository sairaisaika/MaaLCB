"""Public supplier snapshots retain the pinned Git tree without private evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest


spec=importlib.util.spec_from_file_location('pinned_lalc',Path(__file__).resolve().parents[1]/'tools/pinned_lalc.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)


def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args])


def snapshot(tmp_path):
    checkout=tmp_path/'checkout';checkout.mkdir()
    for name in ['LICENSE','a/tree.c','a/tree/sha1']:
        p=checkout/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(name.encode())
    git(checkout,'init','--quiet');git(checkout,'add','.')
    git(checkout,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','Fixture')
    revision=git(checkout,'rev-parse','HEAD').decode().strip()
    files=[]
    for row in git(checkout,'ls-tree','-rz','HEAD').split(b'\0'):
        if not row:continue
        header,name=row.split(b'\t');mode,kind,sha=header.split();name=name.decode()
        files.append(dict(path=name,mode=mode.decode(),sha1=sha.decode(),bytes=(checkout/name).stat().st_size))
    base=tmp_path/'sources/upstream';base.mkdir(parents=True)
    archive=base/(source.NAME+'.source.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for row in files:z.write(checkout/row['path'],row['path'])
    metadata=dict(revision=revision,commit_object_hex=git(checkout,'cat-file','commit',revision).hex(),
        files=files,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (base/(source.NAME+'.source.json')).write_text(json.dumps(metadata))
    return checkout,archive,metadata,revision


def test_actual_git_tree_and_files_round_trip_and_temporary_source_is_removed(tmp_path):
    original,archive,metadata,revision=snapshot(tmp_path)
    assert source.source_tree(metadata['files'])==git(original,'rev-parse','HEAD^{tree}').decode().strip()
    source.verify_snapshot(archive,metadata,revision)
    with source.checkout(tmp_path,revision) as restored:
        assert all((restored/r['path']).read_bytes()==(original/r['path']).read_bytes() for r in metadata['files'])
    assert not restored.exists()
    with pytest.raises(RuntimeError):
        with source.checkout(tmp_path,revision) as restored:raise RuntimeError('import failed')
    assert not restored.exists()


@pytest.mark.parametrize('fault',['pin','commit','tree','archive','blob','missing','traversal','duplicate'])
def test_changed_or_incomplete_source_cannot_be_used(tmp_path,fault):
    _,archive,metadata,revision=snapshot(tmp_path)
    if fault=='pin':revision='1'*40
    elif fault=='commit':metadata['commit_object_hex']=b'changed'.hex()
    elif fault=='tree':metadata['files'][0]['sha1']='1'*40
    elif fault=='archive':archive.write_bytes(b'changed')
    elif fault=='traversal':metadata['files'][0]['path']='../outside'
    else:
        rows=metadata['files']
        with zipfile.ZipFile(archive,'w') as z:
            for n,row in enumerate(rows):
                if fault=='missing' and n==0:continue
                body=b'changed' if fault=='blob' and n==0 else row['path'].encode()
                z.writestr(row['path'],body)
                if fault=='duplicate' and n==0:z.writestr(row['path'],body)
        metadata['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError):source.verify_snapshot(archive,metadata,revision)


def test_existing_checkout_still_requires_the_exact_pin(tmp_path):
    original,_,_,revision=snapshot(tmp_path)
    target=tmp_path/'sources/upstream'/source.NAME;shutil.move(str(original),target)
    with source.checkout(tmp_path,revision) as result:assert result==target
    with pytest.raises(ValueError):
        with source.checkout(tmp_path,'1'*40):pass


def test_explicit_reference_subset_keeps_full_tree_identity_and_only_extracts_retained_files(tmp_path):
    _,archive,metadata,revision=snapshot(tmp_path)
    wanted=metadata['files'][0]
    with zipfile.ZipFile(archive) as old:body=old.read(wanted['path'])
    with zipfile.ZipFile(archive,'w') as new:new.writestr(wanted['path'],body)
    metadata.update(retained_paths=[wanted['path']],archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    assert source.verify_snapshot(archive,metadata,revision)==[wanted]
    (archive.parent/(source.NAME+'.source.json')).write_text(json.dumps(metadata))
    with source.checkout(tmp_path,revision) as restored:
        assert [p.relative_to(restored).as_posix() for p in restored.rglob('*') if p.is_file()]==[wanted['path']]
    metadata['retained_paths'].append('absent/asset.png')
    with pytest.raises(ValueError):source.verify_snapshot(archive,metadata,revision)
    with pytest.raises(ValueError,match='dependency absent'):
        with source.checkout(tmp_path,revision,required=('a/tree.c',)):pass


def test_windows_newline_normalization_is_explicit_and_does_not_allow_other_edits():
    canonical=b'first\nsecond\n';windows=canonical.replace(b'\n',b'\r\n')
    row=dict(sha1=source.git_hash('blob',canonical),windows_crlf=True,
             checkout_sha256=hashlib.sha256(windows).hexdigest())
    assert source.verified_blob(row,windows)
    assert not source.verified_blob(row,b'first\r\nchanged\r\n')
    row['windows_crlf']=False
    assert not source.verified_blob(row,windows)
