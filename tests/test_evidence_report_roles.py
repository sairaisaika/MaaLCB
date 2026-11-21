"""A hash census does not own all diagnostics; actual business roots still win."""
import copy,hashlib,json
from pathlib import Path
import pytest
from maalimbus import capture_retention
from maalimbus.evidence_report_roles import KIND,project,load

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'build/resume-20261117-team2-first-battle-real-verification.json'
# Both tests start from fixture(), which copies this local report.
pytestmark=pytest.mark.needs_local('build/resume-20261117-team2-first-battle-real-verification.json')


def fixture(tmp_path,fault=None):
    value=json.loads(REPORT.read_text());value=copy.deepcopy(value)
    if fault=='business_field':value['pending']=dict(kind='purchase')
    if fault=='reward':value['reward']=True
    if fault=='changed_pair':value['pairs'][2]['native_hash_match']=False
    body=json.dumps(value).encode();p=tmp_path/'build/census.json';p.parent.mkdir();p.write_bytes(body)
    row=dict(kind=KIND,report='build/census.json',sha256=hashlib.sha256(body).hexdigest(),
             required_proofs=[value['pairs'][0]['frame'],value['pairs'][-1]['frame'],value['victory_proof']])
    if fault=='changed_report':p.write_bytes(body+b' ')
    if fault=='unknown_role':row['kind']='ignore_everything'
    if fault=='missing_endpoint':row['required_proofs'].pop()
    return value,row


def declare(root,row):
    (root/'build/evidence-report-roles.json').write_text(json.dumps(dict(version=1,kind='evidence_report_roles',roles=[row])))


def paths(root,value):
    return [root/Path(r['frame'].replace('\\','/')).with_suffix('.png') for r in value['pairs']]


def test_explicit_census_role_invalidates_cached_references_but_keeps_business_endpoints(tmp_path):
    value,row=fixture(tmp_path);frames=paths(tmp_path,value)
    before=capture_retention._reference_keep(tmp_path)
    assert all(p in before for p in frames)
    # A real independent pending transaction pins an intermediate frame too.
    config=tmp_path/'config';config.mkdir()
    (config/'pending.json').write_text(json.dumps(dict(before=str(frames[1]),pending=True)))
    declare(tmp_path,row)
    after=capture_retention._reference_keep(tmp_path)
    assert frames[0] in after and frames[-1] in after and frames[1] in after
    assert tmp_path/Path(value['victory_proof'].replace('\\','/')).with_suffix('.png') in after
    assert frames[2] not in after
    assert (tmp_path/'build/census.json').read_bytes()==json.dumps(value).encode()


@pytest.mark.parametrize('fault',['business_field','reward','changed_pair','changed_report','unknown_role','missing_endpoint'])
def test_unknown_or_changed_report_roles_keep_all_original_frame_protection(tmp_path,fault):
    value,row=fixture(tmp_path,fault);declare(tmp_path,row)
    kept=capture_retention._reference_keep(tmp_path)
    assert all(p in kept for p in paths(tmp_path,value))
