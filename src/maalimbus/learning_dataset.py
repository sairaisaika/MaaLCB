"""Reviewed evidence only; split by real run, never adjacent screenshot frames."""
import hashlib
import json
from pathlib import Path


LABELS=('STAR_GRACES','THEME_PACKS','MAP','PRE_BATTLE_TEAM','BATTLE_HUD',
        'GIFT_PICK','GIFT_GET','EVENT_CHOICE','SHOP','RUN_COMPLETE','UNKNOWN')


def original_bytes(path):
    """Read exact originals without materializing or re-encoding cold PNGs."""
    path=Path(path)
    if path.suffix.lower()=='.png':
        from .native_image_archive import read_png
        return read_png(path)
    return path.read_bytes()


def digest(path):return hashlib.sha256(original_bytes(path)).hexdigest()


def read_image(path):
    """The same BGR pixels for raw/cold inputs; archive corruption propagates."""
    import cv2
    import numpy as np
    body=original_bytes(path)
    if not body:return None
    return cv2.imdecode(np.frombuffer(body,np.uint8),cv2.IMREAD_COLOR)


def local_file(root,value):
    root=Path(root).resolve()
    path=Path(value)
    if not path.is_absolute():path=root/path
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Evidence outside project')
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Linked evidence')
    if path.exists() and not path.is_file():raise ValueError('Evidence is not a regular file')
    if not path.is_file():
        path=path.resolve()
        # Only this project's canonical PNG index may satisfy a missing file.
        # A foreign ancestor's archive or an arbitrary missing model is not it.
        if path.suffix.lower()!='.png' or not any(path.is_relative_to(base) for base in (
                root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime')):
            raise ValueError('Evidence file missing')
        from .native_image_archive import load_index,archived_bytes
        entry=load_index(root)['members'].get(path.relative_to(root).as_posix())
        if entry is None:raise ValueError('Evidence file missing')
        archived_bytes(root,entry)
    return path


def manifest(root,annotations):
    root=Path(root);rows=[];seen={};episodes={}
    for row in annotations:
        if row.get('reviewed') is not True or row.get('label') not in LABELS:
            raise ValueError('Explicit reviewed page label required; OCR scene is not ground truth')
        episode=row.get('episode')
        if not isinstance(episode,str) or not episode:raise ValueError('Real run scope required')
        frame=local_file(root,row['frame']);proof=local_file(root,row['proof'])
        sha=digest(frame)
        # A verifier must actually bind this exact image; annotation alone cannot
        # promote an unverified capture into a proven receipt or terminal page.
        bound=json.loads(proof.read_text(encoding='utf-8'))
        if sha not in json.dumps(bound):raise ValueError('Proof does not bind the reviewed frame hash')
        if sha in seen:
            if seen[sha]!=(episode,row['label']):raise ValueError('Conflicting duplicate or episode leakage')
            continue
        seen[sha]=(episode,row['label'])
        split='validation' if int(hashlib.sha256(episode.encode()).hexdigest()[:8],16)%5==0 else 'train'
        episodes[episode]=split
        rows.append(dict(frame=str(frame.relative_to(root)),image_sha256=sha,
            label=row['label'],class_id=LABELS.index(row['label']),episode=episode,
            split=split,proof=str(proof.relative_to(root)),proof_sha256=digest(proof)))
    classes={split:{r['label'] for r in rows if r['split']==split} for split in ('train','validation')}
    missing={split:sorted(set(LABELS)-values) for split,values in classes.items()}
    return dict(version=1,labels=list(LABELS),samples=rows,episodes=episodes,
        missing_classes=missing,training_ready=bool(rows) and not any(missing.values()),
        production_enabled=False,model_trained=False,input_authorized=False)
