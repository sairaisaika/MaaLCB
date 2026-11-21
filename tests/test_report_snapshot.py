"""A deduplicated backup must be reconstructible as the original ZIP bytes."""
import base64,hashlib,importlib.util,io,zipfile
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('restore_snapshot',Path(__file__).resolve().parents[1]/'tools/restore_report_snapshot.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


def snapshot():
    data={'build/a.json':b'{"receipt":true}', 'build/b.json':b'{"floor":3}'}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        archive.comment=b'original snapshot'
        for name,body in data.items():archive.writestr(name,body)
    original=buffer.getvalue();rows=[]
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        for info in archive.infolist():
            row={k:getattr(info,k) for k in ('filename','date_time','compress_type','create_system',
                'create_version','extract_version','reserved','flag_bits','volume','internal_attr','external_attr')}
            row.update(extra=base64.b64encode(info.extra).decode(),comment=base64.b64encode(info.comment).decode(),
                sha256=hashlib.sha256(data[info.filename]).hexdigest())
            rows.append(row)
    recipe=dict(version=1,kind='report_snapshot_recipe',comment=base64.b64encode(b'original snapshot').decode(),
        members=rows,bytes=len(original),sha256=hashlib.sha256(original).hexdigest())
    return original,recipe,data


def test_original_container_round_trips_from_current_members():
    original,recipe,data=snapshot()
    assert tool.reconstruct(recipe,data)==original


@pytest.mark.parametrize('fault',['member','metadata','container','missing'])
def test_incomplete_or_changed_reconstruction_is_refused(fault):
    original,recipe,data=snapshot()
    if fault=='member':data['build/a.json']=b'changed'
    elif fault=='metadata':recipe['members'][0]['date_time']=[2020,1,1,0,0,0]
    elif fault=='container':recipe['sha256']='0'*64
    else:del data['build/a.json']
    with pytest.raises((ValueError,KeyError)):tool.reconstruct(recipe,data)
