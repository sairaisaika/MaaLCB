"""Storage pressure may reclaim debug output, never unexpired proof by accident."""
import json
from pathlib import Path

import pytest

from maalimbus import workspace


def tree(root):
    run=root/'evidence/runtime/run-a';run.mkdir(parents=True)
    for i in range(6):
        (run/f'frame-{i:04}.png').write_bytes(b'frame'+bytes([i])*100)
        (run/f'frame-{i:04}.json').write_text('{}',encoding='utf8')
    return run


def test_a_successful_run_below_budget_loses_no_frame(tmp_path):
    run=tree(tmp_path)
    before={p:p.read_bytes() for p in run.iterdir()}
    out=workspace.prune(tmp_path,budget=1_000_000)
    assert out['within_budget'] and out['freed']==0 and out['removed']==[]
    assert all(p.read_bytes()==data for p,data in before.items())


def test_default_is_the_users_whole_folder_limit_in_bytes():
    assert workspace.BUDGET_BYTES==3_000_000_000


def test_state_referenced_frames_survive_pressure(tmp_path):
    run=tree(tmp_path);p=tmp_path/'config/user-floor-gift-transaction.json'
    p.parent.mkdir()
    p.write_text(json.dumps(dict(pending=dict(proof=str(run/'frame-0000.json')))))
    protected=workspace.protected_evidence(tmp_path)
    assert run/'frame-0000.png' in protected
    workspace.trim_runs(tmp_path,frames=2)
    assert (run/'frame-0000.png').is_file()
    assert (run/'frame-0004.png').is_file() and (run/'frame-0005.png').is_file()
    assert not (run/'frame-0001.png').exists()


def test_an_old_run_with_a_pending_proof_is_not_a_candidate(tmp_path):
    run=tree(tmp_path)
    for i in range(workspace.KEEP_RUNS+2):
        (run.parent/f'zz-{i}').mkdir()
    config=tmp_path/'config';config.mkdir()
    (config/'pending.json').write_text(json.dumps(dict(proof='evidence/runtime/run-a/frame-0000.json')))
    assert run not in workspace.candidates(tmp_path)


def test_learning_reviews_are_not_rebuildable_cache(tmp_path):
    folder=tmp_path/'build/learning-review';folder.mkdir(parents=True)
    (folder/'review.json').write_text('{}')
    assert folder not in workspace.candidates(tmp_path)


def test_protected_bytes_exceeding_budget_are_reported_honestly(tmp_path):
    assets=tmp_path/'assets';assets.mkdir()
    (assets/'model').write_bytes(b'm'*200)
    result=workspace.prune(tmp_path,budget=100)
    assert result['after']==200 and not result['within_budget']
    assert (assets/'model').read_bytes()==b'm'*200


def test_a_future_build_reserves_peak_space_before_writing(tmp_path):
    (tmp_path/'existing').write_bytes(b'x'*100)
    assert workspace.require_space(tmp_path,50,budget=150)['reserved_bytes']==50
    with pytest.raises(ValueError,match='budget exceeded'):
        workspace.require_space(tmp_path,51,budget=150)
    assert list(tmp_path.iterdir())==[tmp_path/'existing']


def test_cleanup_rejects_an_outside_target_before_deletion(tmp_path):
    root=tmp_path/'workspace';root.mkdir()
    outside=tmp_path/'precious';outside.write_text('keep')
    with pytest.raises(ValueError,match='outside workspace'):
        workspace._remove(outside,root)
    assert outside.read_text()=='keep'


def test_cleanup_never_removes_the_workspace_itself(tmp_path):
    with pytest.raises(ValueError,match='outside workspace'):
        workspace._remove(tmp_path,tmp_path)


@pytest.mark.parametrize('reference', ['absolute', 'workspace_relative', 'application_relative'])
def test_installed_pending_pair_is_protected_before_pressure_cleanup(tmp_path, reference):
    app=tmp_path/'dist/MaaLimbus';run=tree(app)
    frame=run/'frame-0000.json'
    value={'absolute':str(frame),
           'workspace_relative':frame.relative_to(tmp_path).as_posix(),
           'application_relative':frame.relative_to(app).as_posix()}[reference]
    config=tmp_path/'config';config.mkdir()
    state=config/'user-pending.json'
    state.write_text(json.dumps({'pending':{'proof':value}}))
    original={p:p.read_bytes() for p in (state,frame,frame.with_suffix('.png'))}
    protected=workspace.protected_evidence(tmp_path)
    assert frame in protected and frame.with_suffix('.png') in protected
    assert app/'evidence' not in workspace.candidates(tmp_path)
    result=workspace.prune(tmp_path,budget=1)
    assert not result['within_budget']
    assert all(p.read_bytes()==body for p,body in original.items())


def test_ambiguous_application_relative_reference_keeps_both_local_captures(tmp_path):
    canonical=tree(tmp_path);installed=tree(tmp_path/'dist/MaaLimbus')
    review=tmp_path/'build/learning-review';review.mkdir(parents=True)
    (review/'proposal.json').write_text(json.dumps({'native_record':'evidence/runtime/run-a/frame-0000.json'}))
    protected=workspace.protected_evidence(tmp_path)
    assert all(run/'frame-0000.png' in protected for run in (canonical,installed))


def test_external_runtime_reference_does_not_pin_unrelated_cleanup(tmp_path):
    app=tmp_path/'dist/MaaLimbus';run=tree(app)
    config=tmp_path/'config';config.mkdir()
    (config/'pending.json').write_text(json.dumps({'proof':str(tmp_path.parent/'outside/evidence/runtime/frame-0000.json')}))
    assert not workspace.protected_evidence(tmp_path)
    assert app/'evidence' in workspace.candidates(tmp_path)
