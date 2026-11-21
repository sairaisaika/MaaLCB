"""Canonical shop-review references; copied portable datasets remain supported.

The immutable sample still binds original JSON/PNG hashes. An explicit sidecar
selects project-local references; missing copied evidence never silently falls
back to another file. No input, label approval or transaction writes.
"""
from pathlib import Path
from .storage import read_json
from .learning_dataset import local_file

STORAGE='canonical_purchase_evidence_v1'
REFRESH_STORAGE='canonical_refresh_evidence_v1'


def project_root(folder):
    folder=Path(folder).absolute()
    if tuple(folder.parts[-4:-2])!=('build','learning-review') or folder.parts[-2] not in ('shop-purchases','shop'):
        raise ValueError('Canonical purchase evidence needs its project queue')
    root=folder.parents[3]
    for p in (folder,*folder.parents):
        if p.is_symlink() or getattr(p,'is_junction',lambda:False)():
            raise ValueError('Linked canonical purchase review')
        if p==root:break
    return root


def descriptor(folder,sample,key):
    """Choose references only for the named in-project queue; else use copies."""
    parts=Path(folder).parts
    if tuple(parts[-4:-2])!=('build','learning-review') or parts[-2] not in ('shop-purchases','shop'):
        return None
    root=project_root(folder);roles={}
    family=parts[-2];expected='purchase_outcome' if family=='shop-purchases' else 'regular_refresh'
    if sample.get('kind')!=expected:raise ValueError('Canonical shop sample family differs')
    for role in ('before','after','question','notice'):
        proof=sample.get(role)
        if proof is None:continue
        path=local_file(root,proof['path']);local_file(root,path.with_suffix('.png'))
        roles[role]=proof
    return dict(version=1,kind=STORAGE if family=='shop-purchases' else REFRESH_STORAGE,sample=key,roles=roles)


def reference_root(folder,sample=None):
    path=Path(folder)/'evidence-storage.json'
    if not path.exists():return None
    root=project_root(folder);local_file(root,path)
    value=read_json(path)
    sample=sample if sample is not None else read_json(Path(folder)/'sample.json')
    if value!=descriptor(folder,sample,Path(folder).name):
        raise ValueError('Canonical purchase evidence descriptor differs')
    return root


def native_reading(folder,role,proof):
    """Read a complete mirror, or an explicitly declared canonical pair."""
    from .shop_transaction import _frame,_verify
    path=Path(folder)/(role+'.json');png=path.with_suffix('.png')
    for part in (path,png,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise ValueError('Linked purchase evidence')
    if path.exists() or png.exists():return _frame(path)
    root=reference_root(folder)
    if root is None:raise FileNotFoundError(path)
    sample=read_json(Path(folder)/'sample.json')
    if sample.get(role)!=proof:raise ValueError('Canonical purchase role differs')
    local_file(root,proof['path']);local_file(root,Path(proof['path']).with_suffix('.png'))
    record,texts,size=_verify(proof)
    return record,texts,size,proof
