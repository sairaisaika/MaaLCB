"""Synthetic unit contracts, plus an optional original-capture replay.

Generated PNG/OCR pairs exercise scoring and byte binding only. They are not
Maa recognition accuracy, historical capture evidence or live acceptance.
"""
import hashlib
import shutil
from pathlib import Path
import cv2
import numpy as np
import pytest
from maalimbus.storage import read_json,write_json
from maalimbus.mirror_assessment import assess
ROOT=Path(__file__).resolve().parents[1]


def unit_assessment(tmp_path):
    """Self-contained, explicitly synthetic summary with consistent PNG geometry."""
    tokens=[]
    def caption(text,x,y,w=110,h=24):
        tokens.append(dict(text=text,box=[x,y,w,h],score=.99))
    caption('Exploration',220,125)
    caption('Complete',220,190)
    caption('Dungeon Progress',220,255,170)
    caption('Total Progress',220,700,150)
    caption('100%',260,780,90,35)
    caption('Floor 5 [HARD]',240,610,220,26)
    for floor in range(1,6):
        x=158+(floor-1)*80
        caption(f'Floor{floor}',x,355,56,24)
        caption('[HARD]',x,385,56,20)
    caption('7/7',500,420,40,25)
    image=tmp_path/'synthetic-unit-summary.png'
    assert cv2.imwrite(str(image),np.zeros((1080,1920,3),dtype=np.uint8))
    sha=hashlib.sha256(image.read_bytes()).hexdigest()
    write_json(image.with_suffix('.json'),dict(
        fixture_kind='synthetic_unit_not_native_or_live',size=[1920,1080],
        image_sha256=sha,ocr=tokens))
    proof=dict(scope='synthetic-unit-assessment',team=2,
        fixture_kind='synthetic_unit_not_native_or_live',
        summary=dict(floors=[1,2,3,4,5],difficulty='hard',progress=100,
                     floor_five_encounters='7/7',reward_received=False),
        proofs=[dict(frame=image.with_suffix('.json').name,png_sha256=sha)])
    run=dict(id=proof['scope'],team=proof['team'],floors=[1,2,3,4,5],victory=True,reward=False)
    write_json(tmp_path/'proof.json',proof)
    write_json(tmp_path/'ledger.json',dict(active=run))
    return proof,run


def retained_assessment(tmp_path):
    """Preflight the WHOLE historical bundle before copying or claiming a replay."""
    path=ROOT/'build/team-seven-floor-five-real-verification.json'
    if not path.is_file():
        pytest.skip('Historical capture replay unverified: retained proof manifest absent')
    proof=read_json(path)
    assert proof.get('proofs'), 'Historical proof manifest has no frame bindings'
    sources=[Path(item['frame']) for item in proof['proofs']]
    missing=[str(part) for source in sources for part in (source,source.with_suffix('.png'))
             if not part.is_file()]
    if missing:
        pytest.skip('Historical capture replay unverified: original JSON/PNG bundle incomplete: '
                    +'; '.join(missing))
    # Existing but corrupt originals fail rather than being treated as absent.
    for item,source in zip(proof['proofs'],sources):
        png=source.with_suffix('.png');record=read_json(source)
        sha=hashlib.sha256(png.read_bytes()).hexdigest()
        assert sha==item['png_sha256']==record['image_sha256']
        pixels=cv2.imread(str(png))
        assert pixels is not None
        assert record['size']==[pixels.shape[1],pixels.shape[0]]
    for item,source in zip(proof['proofs'],sources):
        shutil.copy2(source,tmp_path/source.name)
        shutil.copy2(source.with_suffix('.png'),tmp_path/source.with_suffix('.png').name)
        item['frame']=source.name
    run=dict(id=proof['scope'],team=proof['team'],floors=[1,2,3,4,5],victory=True,reward=False)
    write_json(tmp_path/'proof.json',proof);write_json(tmp_path/'ledger.json',dict(active=run))
    return proof,run


def test_unit_unpaid_completion_scores_without_claiming_quality_or_receipt(tmp_path):
    unit_assessment(tmp_path)
    original={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    score=assess(tmp_path,'ledger.json','proof.json')
    assert score['progression_score']==90 and score['censored']
    assert score['efficiency_score'] is None and score['survival_score'] is None
    assert not score['components']['reward_verified'] and not score['strategy_training_eligible']
    assert original=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize('fault',['scope','summary','png','reward_flag'])
def test_unit_scope_image_and_summary_cannot_fake_a_score(tmp_path,fault):
    proof,run=unit_assessment(tmp_path)
    if fault=='scope':proof['scope']='other'
    elif fault=='summary':proof['summary']['progress']=99
    elif fault=='png':next(tmp_path.glob('*.png')).write_bytes(b'altered')
    else:run['reward']=True
    write_json(tmp_path/'proof.json',proof);write_json(tmp_path/'ledger.json',dict(active=run))
    if fault=='reward_flag':
        score=assess(tmp_path,'ledger.json','proof.json')
        assert not score['components']['reward_verified'] and score['progression_score']==90
    else:
        with pytest.raises(ValueError):assess(tmp_path,'ledger.json','proof.json')


def test_historical_original_capture_replay_when_complete_bundle_is_available(tmp_path):
    retained_assessment(tmp_path)
    score=assess(tmp_path,'ledger.json','proof.json')
    assert score['progression_score']==90 and not score['components']['reward_verified']
    assert not score['input_authorized'] and not score['state_modified']
