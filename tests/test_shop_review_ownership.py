"""Automatic delayed labels must not overwrite human feedback (isolated fixtures)."""
import json
import hashlib
from types import SimpleNamespace

import pytest

from maalimbus.shop_value_training import review_sample
from maalimbus import shop_value_training as training
from maalimbus.shop_review_state import automatic_owned,merge_outcome
from maalimbus.shop_outcomes import sync


def fixture(tmp_path,review):
    (tmp_path/'sample.json').write_text(json.dumps(dict(version=1,kind='purchase_outcome',scope='fixture')))
    (tmp_path/'outcome.json').write_text(json.dumps(dict(version=1,outcomes=[dict(kind='floor_clear',floor=3,
        evidence=dict(sha256='a'*64))],human_approved=False,training_eligible=False)))
    (tmp_path/'review.json').write_text(json.dumps(review))
    return {p.name:p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize('review',[
    dict(status='rejected',benefit=.1,notes='human rejected this sample',corrected_category=None),
    dict(status='approved',benefit=.2,notes='human correction',corrected_category='other'),
])
def test_human_review_is_preserved_byte_for_byte(tmp_path,review):
    before=fixture(tmp_path,review)
    value,reason=review_sample(tmp_path)
    assert value is None and reason in ('human_review_preserved','human_review_rejected')
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def valid_sample(tmp_path):
    from test_shop_value_training import sample_folder,ledger_for
    samples=tmp_path/'samples'
    folder=sample_folder(samples,'ownership-fixture',scope='scope',status='pending',
        benefit=None,eligible=False,approved_outcome=False)
    return folder,ledger_for(samples)


def pair(folder):
    return {n:((folder/n).read_bytes(),(folder/n).stat().st_mtime_ns)
            for n in ('review.json','outcome.json')}


def transaction_for(folder):
    sample=json.loads((folder/'sample.json').read_text())
    return SimpleNamespace(data=dict(scope=sample['scope'],bought=[dict(
        name=sample['name'],price=sample['price'],visit=sample['visit'],before=sample['before'],
        successor=sample['after'],question=sample['question'],decision_context=sample['context'])],
        visits={sample['visit']:dict(learning_context=sample['context'])}))


def append_victory(folder,ledger):
    from test_shop_value_training import _write_frame
    record=folder.parent.parent/'later-victory.json'
    _write_frame(record,coins=880,offers=[],utc='2026-10-12T14:00:00+00:00',scene='RUN_CLAIM')
    state=json.loads(ledger.read_text())
    state['receipts'][0]['events']['victory']=dict(kind='final_victory',evidence=str(record.resolve()),
        sha256=hashlib.sha256(record.read_bytes()).hexdigest())
    ledger.write_text(json.dumps(state))


@pytest.mark.parametrize('review',[
    dict(status='pending',notes='needs my review',corrected_category=None),
    dict(status='pending',notes='',corrected_category='human-corrected'),
    dict(status='pending',notes='',benefit=.2),
    dict(status='unknown-new-version',notes=''),
])
def test_edited_or_unknown_pending_review_is_not_auto_approved(tmp_path,review):
    before=fixture(tmp_path,review)
    assert review_sample(tmp_path)[0] is None
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_hash_strings_without_native_purchase_evidence_cannot_auto_approve(tmp_path):
    before=fixture(tmp_path,dict(status='pending',notes='',corrected_category=None))
    value,reason=review_sample(tmp_path,ledger={'version':1})
    assert value is None and reason.startswith('automatic_evidence_unverified:')
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_human_takeover_from_automatic_label_survives_retraining_loader(tmp_path):
    from test_shop_review_tool import review_tool
    folder,ledger=valid_sample(tmp_path)
    assert review_sample(folder,ledger=ledger)[0]['benefit']==.8
    review_tool.decide(folder,approve=True,benefit=.2,eligible=True,note='human correction',ledger=ledger)
    before=pair(folder)
    tx=transaction_for(folder)
    assert sync(tx,folder.parent,ledger)[0]['training_eligible']
    assert pair(folder)==before
    assert review_sample(folder,ledger=ledger)==(None,'human_review_preserved')
    assert pair(folder)==before
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    result=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert result['row_count']==1,result['excluded']
    row=result['episodes'][0]['rows'][0]
    assert row['target']==.2 and row['label_source']==training.LABEL_SOURCE
    review_tool.decide(folder,reject=True,note='human rejects')
    before=pair(folder)
    assert sync(tx,folder.parent,ledger)==[]
    assert review_sample(folder,ledger=ledger)==(None,'human_review_rejected')
    assert pair(folder)==before
    assert training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)['row_count']==0


def test_collector_teacher_loader_chain_refreshes_only_unmodified_auto_review(tmp_path):
    folder,ledger=valid_sample(tmp_path);tx=transaction_for(folder)
    assert review_sample(folder,ledger=ledger)[0]['benefit']==.8
    before=pair(folder)
    assert sync(tx,folder.parent,ledger)[0]['training_eligible']
    assert pair(folder)==before
    append_victory(folder,ledger)
    result=sync(tx,folder.parent,ledger)
    assert result[0]['training_eligible'] and result[0]['automatic_label']['benefit']==1.0
    assert json.loads((folder/'review.json').read_text())['benefit']==1.0
    assert review_sample(folder,ledger=ledger)[0]['benefit']==1.0
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    ready=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert ready['row_count']==1,ready['excluded']
    row=ready['episodes'][0]['rows'][0]
    assert row['target']==1.0 and row['label_source']==training.OBJECTIVE_LABEL_SOURCE


def test_collector_refresh_after_human_correction_keeps_human_target(tmp_path):
    from test_shop_review_tool import review_tool
    folder,ledger=valid_sample(tmp_path);tx=transaction_for(folder)
    assert review_sample(folder,ledger=ledger)[1] is None
    review_tool.decide(folder,approve=True,benefit=.2,eligible=True,note='manual override',ledger=ledger)
    review=(folder/'review.json').read_bytes()
    append_victory(folder,ledger)
    assert sync(tx,folder.parent,ledger)[0]['training_eligible']
    assert (folder/'review.json').read_bytes()==review
    assert review_sample(folder,ledger=ledger)==(None,'human_review_preserved')
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    ready=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert ready['row_count']==1,ready['excluded']
    assert ready['episodes'][0]['rows'][0]['target']==.2


def test_missing_ledger_does_not_erase_retained_outcome_or_review(tmp_path):
    folder,ledger=valid_sample(tmp_path);tx=transaction_for(folder)
    assert sync(tx,folder.parent,ledger)[0]['automatic_label']['status']=='ready'
    before=pair(folder)
    result=sync(tx,folder.parent)
    assert result[0]['outcomes'] and pair(folder)==before
    assert result[0]['automatic_label']['status']=='pending'


def test_optional_teacher_failure_cannot_turn_a_verified_purchase_into_a_game_failure(tmp_path,monkeypatch):
    folder,ledger=valid_sample(tmp_path);tx=transaction_for(folder)
    def fail(*a,**kw):raise RuntimeError('unexpected optional teacher failure')
    monkeypatch.setattr(training,'review_sample',fail)
    result=sync(tx,folder.parent,ledger)
    assert result[0]['automatic_label']==dict(status='pending',reason='automatic_review_unavailable',error_type='RuntimeError')
    assert not result[0]['training_eligible']


def test_collector_capacity_failure_precedes_sample_and_image_writes(tmp_path,monkeypatch):
    import maalimbus.shop_outcomes as collector
    folder,ledger=valid_sample(tmp_path);tx=transaction_for(folder)
    fresh=tmp_path/'fresh-review'
    def full(*a,**kw):raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(collector,'reserve_output',full)
    with pytest.raises(ValueError,match='budget'):sync(tx,fresh,ledger)
    assert not list(fresh.rglob('*'))


def test_evidence_created_during_copy_is_not_replaced(tmp_path,monkeypatch):
    import maalimbus.shop_outcomes as collector
    origin=tmp_path/'source';target=tmp_path/'target'
    origin.write_bytes(b'original');expected=hashlib.sha256(origin.read_bytes()).hexdigest()
    copy=collector.shutil.copyfile
    def race(source,destination):
        copy(source,destination);target.write_bytes(b'human changed proof')
    monkeypatch.setattr(collector.shutil,'copyfile',race)
    with pytest.raises(ValueError,match='preserved'):collector._copy_evidence(origin,target,expected)
    assert target.read_bytes()==b'human changed proof'
    assert not list(tmp_path.glob('*.tmp'))


def test_editing_a_sealed_auto_review_is_preserved_but_does_not_forge_eligibility(tmp_path):
    folder,ledger=valid_sample(tmp_path)
    assert review_sample(folder,ledger=ledger)[1] is None
    review=json.loads((folder/'review.json').read_text());review['benefit']=.1
    (folder/'review.json').write_text(json.dumps(review))
    before=pair(folder)
    assert review_sample(folder,ledger=ledger)==(None,'human_review_preserved')
    assert pair(folder)==before
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    result=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert result['row_count']==0
    assert result['excluded'][0]['reason']=='objective_label_differs_from_its_evidence'


def test_interrupted_auto_pair_is_completed_without_a_lock_or_human_overwrite(tmp_path,monkeypatch):
    folder,ledger=valid_sample(tmp_path)
    original=training._write_json
    def fail_outcome(path,data):
        if path.name=='outcome.json':raise OSError('injected interruption')
        original(path,data)
    with monkeypatch.context() as m:
        m.setattr(training,'_write_json',fail_outcome)
        assert review_sample(folder,ledger=ledger)==(None,'automatic_review_write_pending')
    review=json.loads((folder/'review.json').read_text())
    assert automatic_owned(review,json.loads((folder/'outcome.json').read_text()))
    assert json.loads((folder/'outcome.json').read_text())['training_eligible'] is False
    assert review_sample(folder,ledger=ledger)[1] is None
    assert json.loads((folder/'outcome.json').read_text())['training_eligible'] is True


def test_a_human_edit_during_verification_preserves_the_new_decision(tmp_path,monkeypatch):
    folder,ledger=valid_sample(tmp_path)
    original=training.verify_episode_evidence
    outcome=(folder/'outcome.json').read_bytes()
    def edit(*a,**kw):
        result=original(*a,**kw)
        (folder/'review.json').write_text(json.dumps(dict(status='rejected',notes='arrived during audit')))
        return result
    monkeypatch.setattr(training,'verify_episode_evidence',edit)
    assert review_sample(folder,ledger=ledger)==(None,'review_changed_during_verification')
    assert json.loads((folder/'review.json').read_text())['status']=='rejected'
    assert (folder/'outcome.json').read_bytes()==outcome


def test_human_edit_between_automatic_file_writes_is_not_lost(tmp_path,monkeypatch):
    folder,ledger=valid_sample(tmp_path)
    original=training._write_json;outcome=(folder/'outcome.json').read_bytes()
    def edit(path,data):
        original(path,data)
        if path.name=='review.json':
            path.write_text(json.dumps(dict(status='rejected',notes='human arrived during commit')))
    monkeypatch.setattr(training,'_write_json',edit)
    assert review_sample(folder,ledger=ledger)==(None,'review_changed_during_commit')
    assert json.loads((folder/'review.json').read_text())['status']=='rejected'
    assert (folder/'outcome.json').read_bytes()==outcome


def test_explicit_outcome_approval_is_preserved_even_with_pending_label(tmp_path):
    folder,ledger=valid_sample(tmp_path)
    outcome=json.loads((folder/'outcome.json').read_text());outcome['human_approved']=True
    (folder/'outcome.json').write_text(json.dumps(outcome));before=pair(folder)
    assert review_sample(folder,ledger=ledger)==(None,'human_outcome_preserved')
    assert pair(folder)==before


def test_cli_distinguishes_preserved_decisions_from_automatic_updates(tmp_path):
    import subprocess,sys
    from pathlib import Path
    from test_shop_value_training import sample_folder,ledger_for
    samples=tmp_path/'samples'
    first=sample_folder(samples,'manual-approved',scope='approved',status='approved',benefit=.2)
    second=sample_folder(samples,'manual-rejected',scope='rejected',status='rejected',benefit=None)
    before={str(p):p.read_bytes() for f in (first,second) for p in f.iterdir()}
    tool=Path(__file__).resolve().parents[1]/'tools/shop_value_review.py'
    run=subprocess.run([sys.executable,str(tool),'--samples',str(samples),'--ledger',str(ledger_for(samples)),
                        '--review-only','--json'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    report=json.loads(run.stdout)
    assert report['reviewed']==0 and report['human_preserved']==1 and report['human_rejected']==1
    assert before=={str(p):p.read_bytes() for f in (first,second) for p in f.iterdir()}


def test_capacity_failure_preserves_both_label_files(tmp_path,monkeypatch):
    from maalimbus import workspace
    folder,ledger=valid_sample(tmp_path);before=pair(folder)
    def full(*a,**kw):raise ValueError('Workspace budget exceeded')
    monkeypatch.setattr(workspace,'reserve_output',full)
    assert review_sample(folder,ledger=ledger)==(None,'automatic_review_capacity_unavailable')
    assert pair(folder)==before


def test_native_observation_refresh_preserves_human_flags_and_auto_ownership():
    current=dict(version=1,category='delayed',outcomes=[dict(floor=2)],objective='run return',
                 human_approved=False,training_eligible=False,reason='new observations')
    human=dict(current,human_approved=True,training_eligible=True,reason='human approved')
    assert merge_outcome(human,current)==human
    later=dict(current,outcomes=[dict(floor=3)])
    kept=merge_outcome(human,later)
    assert kept['human_approved'] and kept['training_eligible'] and kept['outcomes']==later['outcomes']
    auto=dict(current,approved_by=training.OBJECTIVE_APPROVAL,training_eligible=True,label={'old':'label'})
    updated=merge_outcome(auto,later)
    assert not updated['training_eligible'] and updated['label']==auto['label']


def test_unknown_outcome_schema_is_retained():
    with pytest.raises(ValueError,match='preserved'):
        merge_outcome(dict(version=99),dict(version=1))


def test_unknown_outcome_kind_is_not_guessed_as_a_low_value_label():
    assert training.label_from_outcomes([dict(kind='unknown_future_observation',
        evidence=dict(sha256='a'*64))]) is None


def test_runner_reports_label_state_without_claiming_training_or_purchase_control(capsys):
    from maalimbus.runner import MirrorRunner
    runner=object.__new__(MirrorRunner);runner.artifacts={}
    runner.note('shop_purchase_learning_samples',samples=3,automatic_labels_ready=2,manual_labels_preserved=1)
    text=capsys.readouterr().out
    assert '自动事实标签就绪=2' in text and '人工标签保留=1' in text
    assert '模型尚未应用' not in text and '是否参与排序见商店评分记录' in text


def test_malformed_review_status_excludes_only_that_sample(tmp_path):
    folder,ledger=valid_sample(tmp_path)
    review=json.loads((folder/'review.json').read_text());review['status']={'new':'schema'}
    (folder/'review.json').write_text(json.dumps(review));before=pair(folder)
    assert review_sample(folder,ledger=ledger)==(None,'review_status_unknown')
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    result=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert result['row_count']==0 and result['excluded'][0]['reason']=='review_status_unknown'
    assert pair(folder)==before


def test_legacy_generated_review_can_refresh_but_its_human_annotations_are_kept(tmp_path):
    folder,ledger=valid_sample(tmp_path)
    assert review_sample(folder,ledger=ledger)[1] is None
    review=json.loads((folder/'review.json').read_text());review.pop('auto_payload_sha256')
    (folder/'review.json').write_text(json.dumps(review))
    assert review_sample(folder,ledger=ledger)[1] is None
    assert 'auto_payload_sha256' in json.loads((folder/'review.json').read_text())
    review=json.loads((folder/'review.json').read_text());review['notes']='human annotation'
    (folder/'review.json').write_text(json.dumps(review));before=pair(folder)
    assert review_sample(folder,ledger=ledger)==(None,'human_review_preserved')
    assert pair(folder)==before


def test_legacy_manual_takeover_is_recognized_without_trusting_bad_native_evidence(tmp_path):
    folder,ledger=valid_sample(tmp_path)
    assert review_sample(folder,ledger=ledger)[1] is None
    review=json.loads((folder/'review.json').read_text())
    review.update(benefit=.2,reviewed_by='human',notes='legacy manual tool correction')
    (folder/'review.json').write_text(json.dumps(review))
    catalog=dict(version=1,gifts=[dict(name='Alpha Gift',keywords=['Poise'])])
    result=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert result['row_count']==1 and result['episodes'][0]['rows'][0]['target']==.2
    (folder/'after.png').write_bytes(b'corrupt native image')
    result=training.load_reviewed_episodes(folder.parent,catalog,min_episodes=1,ledger=ledger)
    assert result['row_count']==0 and 'hash' in result['excluded'][0]['reason']
