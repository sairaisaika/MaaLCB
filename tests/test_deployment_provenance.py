"""New provenance is typed; legacy junk cannot grant availability or erase progress."""
import hashlib,json,sys
from pathlib import Path
import numpy as np,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import recognition
from maalimbus.runner import team_state
from maalimbus.vision import Text
from maalimbus.native_evidence import observation_frame
from maalimbus.deployment_transaction import DeploymentTransaction
from maalimbus.storage import write_json

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'evidence'/'runtime'/'packaged-mirror-20261119-051846'
CONTROLS={'pre_battle.card_%02d'%i:[0,0,1,1] for i in range(1,13)}


def record(local):
    return dict(size=[1920,1080],ocr=[dict(text='8/12',box=[1704,758,118,51],score=.97335)],local_ocr=local)


@pytest.mark.parametrize('local',[None,'bad',{'purpose':'deployment_availability','accepted':True},
    ['<provider object>'],[{},'<provider object>'],[{'purpose':'deployment_availability','accepted':'true','unavailable':[6]}]])
def test_legacy_incompatible_entries_are_not_availability_proof(local):
    seen=team_state(record(local),CONTROLS)
    assert seen['participants']==(8,12) and seen['availability'] is None and seen['unavailable']==[]


def test_typed_availability_proof_is_not_lost_among_legacy_junk():
    proof={'purpose':'deployment_availability','accepted':True,'unavailable':[6]}
    seen=team_state(record(['old',proof]),CONTROLS)
    assert seen['availability'] is proof and seen['unavailable']==[6]


@pytest.mark.parametrize('local',[None,'bad',[object()],['provider'],{},
    [{'results':[object()]}],[{'score':float('nan')}],[{'score':float('inf')}],
    [{'results':{1,2}}]])
def test_new_native_frame_rejects_incompatible_provenance_before_files_or_credit(local,tmp_path,monkeypatch):
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='Native local OCR provenance'):
        journal.frame(np.zeros((1080,1920,3),np.uint8),[],'PRE_BATTLE_TEAM',local_ocr=local)
    assert journal.index==0 and {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


def test_fallback_plain_data_survives_journal_frame_binding_and_consumer(tmp_path,monkeypatch):
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    rows=record([])['ocr'];proof={'purpose':'deployment_participants_fallback',
        'roi':[1593,745,307,97],'scale':4,'source_ocr_threshold':.2,'results':rows}
    name=journal.frame(np.zeros((1080,1920,3),np.uint8),
        [Text(r['text'],tuple(r['box']),r['score']) for r in rows],'PRE_BATTLE_TEAM',local_ocr=[proof])
    observed,_,raw=observation_frame(journal.directory,dict(frame=name,scene='PRE_BATTLE_TEAM'))
    assert observed['local_ocr']==raw['local_ocr']==[proof]
    assert team_state(observed,CONTROLS)['participants']==(8,12)
    assert team_state(observed,CONTROLS)['availability'] is None


def test_actual_crash_frame_remains_immutable_and_committed_eight_resume_without_reset(tmp_path):
    path=RUN/'frame-0026.json'
    if not path.is_file() or not path.with_suffix('.png').is_file():
        pytest.skip('Historical crash frame unavailable; mandatory typed producer/consumer checks still execute')
    before=path.read_bytes();raw=json.loads(before)
    assert hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest()==raw['image_sha256']
    assert any(isinstance(p,str) for p in raw['local_ocr'])
    seen=team_state(raw,CONTROLS);assert seen['participants']==(8,12) and seen['availability'] is None
    order=[3,4,9,1,7,2,12,5,8,10,11,6];tx_path=tmp_path/'deployment.json'
    state=dict(scope='resume-scope',order=order,saved_order=order,unavailable=[],availability_proof=None,
        sequence=order[:8],pending=None,submitted=False,revives=[])
    write_json(tx_path,state);tx=DeploymentTransaction(tx_path);state_bytes=tx_path.read_bytes()
    prepared=tx.prepare('resume-scope',order,seen['participants'],seen['numbers'])
    assert not prepared['reset_required'] and tx_path.read_bytes()==state_bytes
    tx.intent('card',seen['participants'],card=order[len(tx.data['sequence'])])
    assert tx.data['sequence']==order[:8] and tx.data['pending']['card']==8
    assert path.read_bytes()==before and raw['local_ocr']==json.loads(before)['local_ocr']
