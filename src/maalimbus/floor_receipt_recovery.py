"""Replay an already closed recorder's actual GET acknowledgements, without input.

Reuses the transaction owner on an isolated copy, then atomically publishes only
a complete chain. Recorder identity is checked against the logical run scope.
"""
import copy,hashlib,json,tempfile
from pathlib import Path
from datetime import datetime
from .native_evidence import bound_frame
from .floor_gift_transaction import FloorGiftTransaction,retained_notice_name
from .storage import write_json
from .vision import Text,find


def recover_closed_receipts(transaction,scope,evidence_root):
    data=transaction.data or {};pending=data.get('pending') or {}
    if data.get('scope')!=scope or pending.get('kind')!='receipt':return None
    first=Path(pending['proof']);base=first.parent;root=Path(evidence_root).resolve()
    if not base.resolve().is_relative_to(root):return None
    log=base/'events.jsonl'
    if log.is_symlink() or not log.is_file() or log.stat().st_size>8_000_000:return None
    body=log.read_bytes();rows=[json.loads(s) for s in body.splitlines()]
    if any(not isinstance(r,dict) for r in rows):return None
    scopes={r.get('run_scope') for r in rows if r.get('event')=='mirror_loop_start'}
    if scopes!={scope} or not any(r.get('event')=='mirror_loop_stopped' for r in rows):return None
    original=transaction.path.read_bytes();proofs=[]
    if json.loads(original)!=data:return None
    def frame(name):
        if not isinstance(name,str) or not name.startswith('frame-') or not name[6:].isdigit():
            raise ValueError('Invalid receipt capture identity')
        path=base/(name+'.json');identity,record=bound_frame(path)
        return path,identity,record
    with tempfile.TemporaryDirectory(prefix='maalimbus-receipt-replay-') as temporary:
        isolated=Path(temporary)/'transaction.json';isolated.write_bytes(original)
        replay=FloorGiftTransaction(isolated)
        for _ in range(len(data.get('selected',[]))+1):
            p=replay.data.get('pending') or {}
            if p.get('kind')!='receipt':return None
            before=Path(p['proof']);_,identity,record=frame(before.stem)
            printed=retained_notice_name(before,root)
            if not printed:return None
            last=None;ack=None
            for index,row in enumerate(rows):
                if row.get('event') in ('map_observed','battle_observed'):last=row.get('frame')
                if row.get('event')=='window_intent' and last==before.stem:
                    if ack is not None:return None
                    if (row.get('page')!='GIFT_GET' or row.get('reason')!=
                            'the_gift_get_notice_is_cleared_with_its_own_confirm'):return None
                    ack=(index,row)
            if ack is None:return None
            index,intent=ack;point=intent.get('point');delay=intent.get('delay_ms')
            texts=[Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']]
            controls=find(texts,r'^Confirm$',(.35,.65,.65,.85),record['size'],.9)
            if len(controls)!=1:return None
            box=list(controls[0].box);target=intent.get('target')
            # The native button target includes padding around its OCR caption.
            # Prove the actual touch lies inside both; equal rectangle geometry
            # would reject the genuine padded control used by the runtime.
            if (not isinstance(target,list) or len(target)!=4 or any(type(n) is not int for n in target)
                    or min(target[2:])<=0 or type(delay) is not int or not 350<=delay<=750
                    or not isinstance(point,list) or len(point)!=2
                    or any(type(n) is not int for n in point)
                    or not (box[0]<=point[0]<=box[0]+box[2] and box[1]<=point[1]<=box[1]+box[3])
                    or not (target[0]<=point[0]<=target[0]+target[2] and target[1]<=point[1]<=target[1]+target[3])):return None
            successor=None
            for row in rows[index+1:]:
                if row.get('event')=='window_intent':return None
                if row.get('event') in ('map_observed','battle_observed') and row.get('frame')!=before.stem:
                    if row.get('scene') in ('UNKNOWN','LOADING'):continue
                    successor=row;break
            if successor is None:return None
            path,next_identity,next_record=frame(successor['frame'])
            if next_record['scene']!=successor.get('scene'):return None
            if successor.get('image_sha256',next_identity['png_sha256'])!=next_identity['png_sha256']:return None
            start=datetime.fromisoformat(intent['utc']);end=datetime.fromisoformat(successor['utc'])
            captured=datetime.fromisoformat(record['utc']);fresh=datetime.fromisoformat(next_record['utc'])
            if (not all(t.tzinfo for t in (start,end,captured,fresh))
                    or end<=start or captured>start or not start<fresh<=end):return None
            if next_record['scene']=='GIFT_GET':name=retained_notice_name(path,root)
            elif next_record['scene']=='THEME_PACKS':
                ts=[Text(t['text'],tuple(t['box']),t['score']) for t in next_record['ocr']]
                if len(find(ts,r'^SELECT FLOOR [2-5] THEME PACK$',(.35,.10,.65,.20),next_record['size'],.9))!=1:return None
                name=None
            else:return None
            proofs.append(dict(before=str(before),before_hashes=identity,
                successor=str(path),successor_hashes=next_identity,acknowledgement=copy.deepcopy(intent)))
            replay.observe_receipt(next_record['scene'],name,str(path))
            if replay.data.get('completed'):break
            replay.receipt_intent(name,str(path),on_notice_page=True)
        if not replay.data.get('completed') or replay.data.get('pending') is not None:return None
        if transaction.path.read_bytes()!=original or log.read_bytes()!=body:
            raise ValueError('Receipt recovery source changed')
        replay.data.setdefault('retained_chain_recoveries',[]).append(dict(
            original_transaction_sha256=hashlib.sha256(original).hexdigest(),
            event_log_sha256=hashlib.sha256(body).hexdigest(),proofs=proofs,input_sent=False))
        write_json(transaction.path,replay.data);transaction.data=replay.data
    return dict(scope=scope,receipts=len(transaction.data['receipts']),
                completed=True,recorder=base.name)
