"""Cold storage preserves native originals without deciding what a page means."""
import json
import os

import pytest

from maalimbus import native_image_archive as archive
from maalimbus.native_evidence import frame_reference
from test_observation_frame import capture


def closed_original(root,scene):
    path,raw=capture(root/'evidence/runtime/old',scene=scene)
    pixels=path.with_suffix('.png').read_bytes()+b'original encoded trailing bytes'*3000
    raw['image_sha256']=archive.sha(pixels)
    path.write_text(json.dumps(raw));path.with_suffix('.png').write_bytes(pixels)
    (path.parent/'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped'))+'\n')
    os.utime(path.parent/'events.jsonl',(8000,8000))
    for n in range(5):
        run=root/('evidence/runtime/recent-%d'%n);run.mkdir()
        (run/'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_stopped'))+'\n')
        os.utime(run/'events.jsonl',(9000+n,9000+n))
    return path,pixels,raw


@pytest.mark.parametrize('scene',['PRE_BATTLE_TEAM','SHOP_PURCHASE','EVENT_RESULT','GIFT_GET',
                                'BATTLE_RESULT','HOME','UNRECOGNIZED_NEW_OVERLAY'])
def test_closed_unreferenced_pages_preserve_original_bytes_without_semantic_grant(tmp_path,scene):
    path,pixels,raw=closed_original(tmp_path,scene);expected=frame_reference(path)
    assert len(archive.candidates(tmp_path))==1
    result=archive.compact(tmp_path)
    assert result['files']==1 and result['freed']>0 and result['input_sent'] is False
    assert not path.with_suffix('.png').exists()
    assert archive.read_png(path.with_suffix('.png'))==pixels
    assert frame_reference(path)==expected
    assert json.loads(path.read_bytes())==raw
    assert not (tmp_path/'config').exists()


@pytest.mark.parametrize('owner',['pending','review','model','source'])
def test_independent_raw_pin_still_wins_on_business_page(tmp_path,owner):
    path,pixels,_=closed_original(tmp_path,'SHOP_PURCHASE')
    locations={'pending':'config/pending.json','review':'build/learning-review/review.json',
               'model':'assets/resource/base/model/references.json','source':'docs/proof.md'}
    pin=tmp_path/locations[owner];pin.parent.mkdir(parents=True,exist_ok=True)
    if owner=='source':pin.write_text(path.relative_to(tmp_path).as_posix())
    else:pin.write_text(json.dumps(dict(pending=str(path),approved=False)))
    assert archive.candidates(tmp_path)==[]
    assert archive.compact(tmp_path)['files']==0
    assert path.with_suffix('.png').read_bytes()==pixels


@pytest.mark.parametrize('fault',['unclosed','recent','dimensions','frame_identity','nonobject'])
def test_storage_is_not_permission_to_archive_unbound_or_active_capture(tmp_path,fault):
    path,pixels,raw=closed_original(tmp_path,'PRE_BATTLE_TEAM')
    if fault=='unclosed':
        (path.parent/'events.jsonl').write_text(json.dumps(dict(event='mirror_loop_start'))+'\n')
    elif fault=='recent':os.utime(path.parent/'events.jsonl',(10000,10000))
    else:
        if fault=='dimensions':raw['size']=[16,24]
        elif fault=='frame_identity':raw['frame']='frame-9999'
        else:raw=[]
        path.write_text(json.dumps(raw))
    assert archive.candidates(tmp_path)==[]
    assert path.with_suffix('.png').read_bytes()==pixels
