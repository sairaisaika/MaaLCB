"""Two actual acknowledgements recover the owned replacement out of pick order."""
import copy,json,shutil
from pathlib import Path
import pytest
from maalimbus.floor_gift_transaction import FloorGiftTransaction
from maalimbus.floor_receipt_recovery import recover_closed_receipts
from maalimbus.storage import write_json

ROOT=Path(__file__).resolve().parents[1]
RETAINED=ROOT/'evidence/runtime/packaged-mirror-20261117-120542'
# Every test here starts from fixture(), which copies three frames and the journal of this run.
pytestmark=pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261117-120542')


def fixture(tmp_path,fault=None):
    # Explicit original shape; future live state must not change this test.
    data=dict(schema=2,scope='13e46c794c8445d199a634de6d815c05',commit_sent=True,
        selected=['Skeletal Crumbs','Employee Card'],
        picked_owned={'Skeletal Crumbs':False,'Employee Card':True},
        history=[dict(fixture='preserved prior state')],completed=False,receipts=[],
        pending=dict(kind='receipt',title='Skeletal Crumbs',printed='Faint Vestige',
                     proof=str(RETAINED/'frame-0005.json')))
    base=tmp_path/'evidence/runtime/closed';base.mkdir(parents=True)
    for name in ('frame-0005','frame-0006','frame-0007'):
        for suffix in ('.json','.png'):shutil.copyfile(RETAINED/(name+suffix),base/(name+suffix))
    data['pending']['proof']=str(base/'frame-0005.json')
    rows=[json.loads(s) for s in (RETAINED/'events.jsonl').read_text().splitlines()]
    acknowledgements=[r for r in rows if r.get('event')=='window_intent' and r.get('page')=='GIFT_GET']
    if fault=='short_touch':acknowledgements[0]['delay_ms']=300
    if fault=='outside_control':acknowledgements[0]['point']=[100,100]
    if fault=='foreign_scope':next(r for r in rows if r.get('event')=='mirror_loop_start')['run_scope']='other'
    if fault=='changed_image':(base/'frame-0006.png').write_bytes(b'changed')
    if fault=='stale_successor':
        p=base/'frame-0006.json';r=json.loads(p.read_text());r['utc']='2026-11-17T17:00:00+00:00';p.write_text(json.dumps(r))
    if fault=='missing_final_anchor':
        p=base/'frame-0007.json';r=json.loads(p.read_text());r['ocr']=[];p.write_text(json.dumps(r))
    if fault=='duplicate_ack':rows.insert(rows.index(acknowledgements[0])+1,copy.deepcopy(acknowledgements[0]))
    if fault=='unclosed':rows=[r for r in rows if r.get('event')!='mirror_loop_stopped']
    (base/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    path=tmp_path/'tx.json';write_json(path,data)
    return FloorGiftTransaction(path),base


def test_retained_chain_recovers_both_receipts_without_replaying_a_get(tmp_path):
    tx,base=fixture(tmp_path);history=copy.deepcopy(tx.data.get('history'))
    result=recover_closed_receipts(tx,tx.data['scope'],base.parent)
    assert result['receipts']==2 and result['completed']
    assert tx.data['pending'] is None and tx.data['history']==history
    assert [(r['title'],r.get('printed')) for r in tx.data['receipts']]==[
        ('Employee Card','Faint Vestige'),('Skeletal Crumbs',None)]
    assert tx.data['attribution_revisions'][-1]['previous_title']=='Skeletal Crumbs'
    assert len(tx.data['retained_chain_recoveries'][-1]['proofs'])==2
    original=tx.path.read_bytes()
    assert recover_closed_receipts(tx,tx.data['scope'],base.parent) is None
    assert tx.path.read_bytes()==original


@pytest.mark.parametrize('fault',['short_touch','outside_control','foreign_scope','changed_image','stale_successor','missing_final_anchor','duplicate_ack','unclosed'])
def test_incomplete_or_changed_chain_preserves_the_exact_pending_bytes(tmp_path,fault):
    tx,base=fixture(tmp_path,fault);original=tx.path.read_bytes();state=copy.deepcopy(tx.data)
    try:result=recover_closed_receipts(tx,tx.data['scope'],base.parent)
    except (OSError,ValueError,KeyError,TypeError):result=None
    assert result is None and tx.path.read_bytes()==original and tx.data==state


def test_new_substitution_uses_unique_owned_pick_instead_of_selection_order(tmp_path):
    tx,base=fixture(tmp_path);tx.data['pending']=dict(kind='commit',proof=str(base/'frame-0005.json'))
    write_json(tx.path,tx.data)
    tx.receipt_intent('Faint Vestige',str(base/'frame-0005.json'),on_notice_page=True)
    assert tx.data['pending']['title']=='Employee Card'
    assert tx.data['pending']['printed']=='Faint Vestige'


def test_runner_resume_dispatches_retained_chain_before_any_new_get(tmp_path):
    from types import SimpleNamespace
    from maalimbus.runner import MirrorRunner
    tx,base=fixture(tmp_path);events=[]
    runner=SimpleNamespace(run_id=tx.data['scope'],note=lambda event,**fields:events.append((event,fields)))
    assert MirrorRunner._resolve_floor_receipt(runner,tx,'MAP',None,base.parent/'fresh',{'scene':'MAP'})
    assert tx.data['completed'] and tx.data['pending'] is None
    assert events[0][0]=='floor_gift_retained_chain_recovered' and not events[0][1]['input_sent']
