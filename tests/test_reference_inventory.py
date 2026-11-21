"""Pin diagnostics cannot recursively make their own observed pins permanent."""
import json
from pathlib import Path

import pytest

from maalimbus import capture_retention as retention,workspace
from maalimbus.evidence_reports import read_report_bytes
from test_capture_retention import run


def inventory(paths):
    return dict(read_only=True,device_input=False,old_protected=10,new_protected=10+len(paths),
        additional_protected=len(paths),installed_evidence_previously_candidate=True,
        installed_evidence_now_candidate=False,workspace_bytes=10000,additional_paths=paths)


def test_census_does_not_pin_its_own_observed_paths_but_receipt_still_does(tmp_path):
    folder=run(tmp_path,closed=True);build=tmp_path/'build';build.mkdir()
    frames=[str(folder/f'frame-{n:04}.png') for n in (2,5,6)]
    report=build/'pins.json';report.write_text(json.dumps(inventory(frames)))
    original=report.read_bytes()
    assert retention.reference_inventory(json.loads(original))
    assert not (folder/'frame-0005.png') in retention._reference_keep(tmp_path)
    config=tmp_path/'config';config.mkdir()
    (config/'pending.json').write_text(json.dumps(dict(pending=dict(before=frames[1]))))
    assert folder/'frame-0005.png' in retention._reference_keep(tmp_path)
    result=retention.plan(tmp_path,folder,30000,recent=2,budget=workspace.size(tmp_path)+3000)
    removed={Path(x['path']).name for x in result['files']}
    assert 'frame-0005.png' not in removed
    assert 'frame-0006.png' in removed
    assert report.read_bytes()==original


@pytest.mark.parametrize('fault',['extra_proof','count','not_readonly','sent_input','bool_count',
    'duplicate','wrong_kind','untyped_transaction','nonstring'])
def test_incomplete_or_business_records_keep_all_their_normal_references(fault):
    value=inventory(['evidence/runtime/closed/frame-0002.png'])
    if fault=='extra_proof':value['proof']=value['additional_paths'][0]
    elif fault=='count':value['new_protected']+=1
    elif fault=='not_readonly':value['read_only']=False
    elif fault=='sent_input':value['device_input']=True
    elif fault=='bool_count':value['old_protected']=True
    elif fault=='duplicate':value.update(additional_paths=['same','same'],additional_protected=2,new_protected=12)
    elif fault=='wrong_kind':value['kind']='receipt_verification'
    elif fault=='untyped_transaction':value['pending']=None
    else:value['additional_paths']=[{}]
    assert not retention.reference_inventory(value)


def test_actual_legacy_readonly_census_is_recognized_without_rewriting_bytes():
    root=Path(__file__).resolve().parents[1]
    try:body=read_report_bytes(Path('build/resume-20261116-installed-evidence-protection-readonly.json'),root=root)
    except FileNotFoundError:pytest.skip('historical local pin census is not distributed')
    assert retention.reference_inventory(json.loads(body))
    assert body==read_report_bytes(Path('build/resume-20261116-installed-evidence-protection-readonly.json'),root=root)


def test_map_unknown_animation_is_not_fourteen_independent_page_boundaries(tmp_path):
    folder=run(tmp_path,closed=True)
    for n in range(1,15):
        p=folder/f'frame-{n:04}.json';value=json.loads(p.read_text())
        value['scene']='MAP' if n%2 else 'UNKNOWN';p.write_text(json.dumps(value))
    metadata={p:p.read_bytes() for p in folder.glob('*.json')}
    result=retention.plan(tmp_path,folder,26000,recent=2,budget=workspace.size(tmp_path)+1000)
    assert result['sufficient'] and len(result['files'])>=6
    removed={Path(row['path']).name for row in result['files']}
    assert not removed.intersection(f'frame-{n:04}.png' for n in (1,2,3,4,13,14))
    assert all(p.read_bytes()==body for p,body in metadata.items())


def test_actual_named_foreground_change_still_pins_both_sides(tmp_path):
    folder=run(tmp_path,closed=True)
    p=folder/'frame-0007.json';value=json.loads(p.read_text());value['scene']='UNKNOWN_DIALOG';p.write_text(json.dumps(value))
    result=retention.plan(tmp_path,folder,60000,recent=2,budget=workspace.size(tmp_path)+1000)
    removed={Path(row['path']).name for row in result['files']}
    assert not removed.intersection(f'frame-{n:04}.png' for n in (6,7,8))


@pytest.mark.parametrize('fault',[None,'unjudged','foreign_target','changed_successor','no_terminal','active'])
def test_only_pixel_bound_judged_map_diagnostics_may_compact(tmp_path,fault):
    # Same native contract as production: scoped, timestamped input, independent
    # successor and a full floor/pack header. Bare synthetic page names cannot
    # discharge an input's proof obligation.
    from test_map_diagnostic_retention import chain
    folder,rows=chain(tmp_path);events=folder/'events.jsonl'
    verdict=rows[7]  # The input before frame0003 is frame0002.
    if fault=='unjudged':verdict['outcome']='unjudged'
    if fault=='foreign_target':verdict['target']=[50,50,20,20]
    if fault=='changed_successor':(folder/'frame-0003.png').write_bytes(b'changed')
    if fault=='no_terminal':rows.pop()
    events.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
    eligible={p.stem for p,r in retention._run_rows(folder,fault=='active',2)}
    # A judged older input may compact while the controller remains active;
    # its last input pair and every external business/review pin stay retained.
    assert ('frame-0002' in eligible) is (fault in (None,'active'))
