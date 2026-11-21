"""Hash-bound roles distinguish a diagnostic census from durable business proof.

The original report bytes remain unchanged. Only a narrowly shaped, completed
battle capture census can declare its exhaustive pair list diagnostic. Explicit
endpoints, all other report fields and independent state/model/review references
remain strong; the capture owner still decides actual reclaimability.
"""
import hashlib,json,re
from pathlib import Path

INDEX='build/evidence-report-roles.json'
KIND='completed_battle_capture_census_v1'
FIELDS=set('stage_verified scope team floors whole_run_victory reward submit_pending submitted '
           'ordinary_inputs touches_bounded pairs verified_clear task_succeeded timed_out '
           'stop_reason normalization limitation victory_anchor victory_proof'.split())


def load(root):
    p=Path(root)/INDEX
    if not p.exists():return {},'absent'
    raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    try:
        if p.is_symlink() or len(raw)>1_000_000:raise ValueError()
        value=json.loads(raw)
        if (set(value)!={'version','kind','roles'} or value['version']!=1
                or value['kind']!='evidence_report_roles' or not isinstance(value['roles'],list)
                or len(value['roles'])>32):raise ValueError()
        roles={}
        for row in value['roles']:
            if (set(row)!={'kind','report','sha256','required_proofs'} or row['kind']!=KIND
                    or not re.fullmatch(r'build/[^/\\]+\.json',row['report'])
                    or not re.fullmatch(r'[0-9a-f]{64}',row['sha256'])
                    or not isinstance(row['required_proofs'],list)
                    or not all(isinstance(p,str) for p in row['required_proofs'])
                    or row['sha256'] in roles):raise ValueError()
            roles[row['sha256']]=row
        return roles,digest
    except (ValueError,TypeError,KeyError):return {},digest


def project(value,raw,roles):
    """Unknown/changed declarations retain ordinary recursive protection."""
    role=roles.get(hashlib.sha256(raw).hexdigest())
    if not role or not isinstance(value,dict) or set(value)!=FIELDS:return value
    if (value['stage_verified'] is not True or value['timed_out'] is not False
            or value['whole_run_victory'] is not False or value['reward'] is not False
            or value['submit_pending'] is not False or value['submitted'] is not True
            or value['touches_bounded'] is not True or value['stop_reason']!='stop_page_reached'):
        return value
    pairs=value['pairs']
    if not isinstance(pairs,list) or len(pairs)<3 or not isinstance(value['victory_proof'],str):return value
    for row in pairs:
        if (not isinstance(row,dict) or set(row)!={'frame','scene','native_hash_match','sha256'}
                or row['native_hash_match'] is not True or not isinstance(row['scene'],str)
                or not isinstance(row['frame'],str)
                or not re.fullmatch(r'evidence/runtime/[\w.-]+/frame-\d+\.json',row['frame'].replace('\\','/'))
                or not isinstance(row['sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',row['sha256'])):
            return value
    required={pairs[0]['frame'],pairs[-1]['frame'],value['victory_proof']}
    if (set(role['required_proofs'])!=required
            or not required<={r['frame'] for r in pairs}):return value
    # The census remains intact on disk. This is only its reference-role view.
    return {**{k:v for k,v in value.items() if k!='pairs'},
            'required_proofs':role['required_proofs']}
