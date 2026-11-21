"""Pressure can evict intermediate pixels, never pending or boundary proof."""
from pathlib import Path
import json

import pytest

from maalimbus import capture_retention as retention,workspace
from maalimbus.learning_dataset import digest
from maalimbus.storage import write_json


def run(root,name='current',*,closed=False):
    folder=root/'evidence/runtime'/name;folder.mkdir(parents=True)
    events=[]
    for n in range(1,15):
        image=folder/f'frame-{n:04}.png';image.write_bytes(bytes([n])*10000)
        write_json(image.with_suffix('.json'),dict(scene='MAP',image_sha256=digest(image)))
        events.append(dict(event='map_observed',frame=image.name))
        if n==3:events.append(dict(event='window_intent'))
    if closed:events.append(dict(event='mirror_loop_stopped'))
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return folder


def make_pressure(root,reserve=26000):
    return workspace.size(root)+reserve-1000


def closed_shop_polls(root, *, mutation=None):
    folder = root/'evidence/runtime/old'
    folder.mkdir(parents=True)
    events = []
    for i in range(1, 5):
        name = f'frame-{i:04d}'
        image = folder/(name+'.png')
        pixels = 1 if mutation == 'transient_pixels' and i == 3 else i
        image.write_bytes(bytes([pixels])*30_000)
        image_hash = digest(image)
        write_json(image.with_suffix('.json'), dict(scene='SHOP', image_sha256=image_hash))
        events += [dict(event='loop_heartbeat',phase='step_start',step_attempt=i),
                   dict(event='map_observed',frame=name),
                   dict(event='step_observation',phase='observe',step_attempt=i,frame=name,
                        scene='SHOP',image_sha256=image_hash,input_sent=False)]
        if i == 2 and mutation == 'intent':
            events.append(dict(event='window_intent',step_attempt=i))
        if i != 2 or mutation != 'interrupted':
            row = dict(event='step_finished',step_attempt=i,page='SHOP',dispatched=False,waiting=True)
            if mutation != 'legacy':
                row['capture_role'] = 'diagnostic_poll'
            events.append(row)
            if i == 2 and mutation == 'reopened':
                events.append(dict(event='mirror_loop_stopped',passed=False))
    if mutation != 'open':
        events.append(dict(event='mirror_loop_stopped',passed=False))
    if mutation == 'late_input':
        events.append(dict(event='window_intent',input_sent=True))
    if mutation == 'hash':
        events[6]['image_sha256'] = '0'*64
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return folder


def test_closed_read_only_polls_retire_pixels_but_keep_metadata_and_references(tmp_path):
    folder = closed_shop_polls(tmp_path)
    current = tmp_path/'evidence/runtime/current'
    current.mkdir()
    config = tmp_path/'config'
    config.mkdir()
    write_json(config/'pending.json', dict(before=str(folder/'frame-0003.json')))
    journal = (folder/'events.jsonl').read_bytes()
    metadata = (folder/'frame-0002.json').read_bytes()
    result = retention.plan(tmp_path,current,26_000,recent=2,budget=workspace.size(tmp_path)+20_000)
    assert result['sufficient']
    assert [Path(row['path']).name for row in result['files']] == ['frame-0002.png']
    retention.apply(tmp_path,current,result)
    assert not (folder/'frame-0002.png').exists()
    assert all((folder/f'frame-{i:04d}.png').exists() for i in (1,3,4))
    assert (folder/'frame-0002.json').read_bytes() == metadata
    assert (folder/'events.jsonl').read_bytes() == journal


@pytest.mark.parametrize('mutation', [
    'legacy', 'open', 'intent', 'interrupted', 'late_input', 'hash', 'transient_pixels', 'reopened',
])
def test_poll_retirement_requires_declared_closed_uninterrupted_scope(tmp_path,mutation):
    folder = closed_shop_polls(tmp_path,mutation=mutation)
    current = tmp_path/'evidence/runtime/current'
    current.mkdir()
    groups = retention.diagnostic_groups(tmp_path,current,recent=2)
    assert not groups
    assert (folder/'frame-0002.png').exists()


def test_no_pressure_leaves_every_pair_and_metadata_unchanged(tmp_path):
    folder=run(tmp_path);before={p:p.read_bytes() for p in folder.iterdir()}
    result=retention.plan(tmp_path,folder,1000)
    assert result['sufficient'] and not result['files']
    assert all(p.read_bytes()==body for p,body in before.items())


def test_preferred_refresh_pair_uses_only_reclaimable_existing_diagnostics(tmp_path):
    folder=run(tmp_path)
    request=26_000
    budget=make_pressure(tmp_path)
    minimum=retention.plan(tmp_path,folder,request,budget=budget)
    preferred=retention.plan(tmp_path,folder,request,budget=budget,prefer_extra=8_000)
    assert preferred['sufficient'] and preferred['additional_bytes']==34_000
    assert len(preferred['files'])>len(minimum['files'])
    fallback=retention.plan(tmp_path,folder,request,budget=budget,prefer_extra=100_000)
    assert fallback==minimum
    retained={Path(row['path']).name for row in preferred['files']}
    assert not retained.intersection({'frame-0001.png','frame-0003.png','frame-0004.png'})


def test_reservation_may_reduce_diagnostic_tail_but_never_input_or_pending_pins(tmp_path,monkeypatch):
    folder=run(tmp_path)
    config=tmp_path/'config';config.mkdir()
    write_json(config/'pending.json',dict(pending=str(folder/'frame-0008.json')))
    metadata={p:p.read_bytes() for p in folder.glob('*.json')}
    # Physical pre-existing room covers the durable unlink trail, but the
    # future allocation requires more than the preferred eight-frame tail.
    budget=workspace.size(tmp_path)+50000
    monkeypatch.setattr(workspace,'BUDGET_BYTES',budget)
    preferred=retention.plan(tmp_path,folder,80000,budget=budget)
    assert not preferred['sufficient']
    result=retention.reserve(folder,80000,application_root=tmp_path)
    assert result['sufficient'] and result['recent']==2
    assert all((folder/f'frame-{n:04}.png').exists() for n in (1,3,4,8,13,14))
    assert all(p.read_bytes()==body for p,body in metadata.items())


def test_pressure_keeps_pending_input_boundaries_recent_and_json_history(tmp_path):
    folder=run(tmp_path);config=tmp_path/'config';config.mkdir()
    protected=folder/'frame-0002.json'
    write_json(config/'pending.json',dict(pending=dict(before=str(protected))))
    metadata={p:p.read_bytes() for p in folder.glob('*.json')}
    result=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    assert result['sufficient']
    # 1:first, 2:pending, 3/4:input before/after, 7..14:recent eight.
    assert [Path(r['path']).name for r in result['files']]==['frame-0005.png','frame-0006.png']
    retention.apply(tmp_path,folder,result)
    assert all(p.read_bytes()==body for p,body in metadata.items())
    assert all((folder/f'frame-{n:04}.png').exists() for n in [1,2,3,4,7,14])
    assert not (folder/'frame-0005.png').exists()
    trail=[json.loads(x) for x in (folder/'capture-retention.jsonl').read_text().splitlines()]
    assert len([x for x in trail if x['event']=='capture_reclaimed'])==2


def test_a_folder_already_over_its_target_can_start_its_own_reclamation(tmp_path):
    # Measured 2026-11-21: at 3,327,430,918 bytes against a 3.0 GB target a 333 MB plan
    # was refused on its own 0.9 MB deletion trail, because the trail had to fit under
    # the target before the first unlink. The trail is admitted against what it frees.
    folder=run(tmp_path)
    budget=workspace.size(tmp_path)-15_000
    result=retention.plan(tmp_path,folder,1_000,recent=2,budget=budget)
    assert result['sufficient'] and len(result['files'])>=5
    assert workspace.size(tmp_path)+result['manifest_reservation']>budget
    retention.apply(tmp_path,folder,result)
    assert workspace.size(tmp_path)+1_000<=budget
    assert all((folder/f'frame-{n:04}.png').exists() for n in (1,3,4,13,14))
    trail=[json.loads(x) for x in (folder/'capture-retention.jsonl').read_text().splitlines()]
    assert len([x for x in trail if x['event']=='capture_reclaimed'])==len(result['files'])


@pytest.mark.parametrize('fault',['changed_image','changed_record','new_pending','missing_event_log'])
def test_changed_plan_refuses_before_removing_anything(tmp_path,fault):
    folder=run(tmp_path);result=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    target=tmp_path/result['files'][0]['path']
    if fault=='changed_image':target.write_bytes(b'changed')
    elif fault=='changed_record':target.with_suffix('.json').write_text('{}')
    elif fault=='missing_event_log':(folder/'events.jsonl').unlink()
    else:
        p=tmp_path/'config/pending.json';p.parent.mkdir()
        write_json(p,dict(proof=str(target)))
    before={p:p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(ValueError,match='plan changed'):
        retention.apply(tmp_path,folder,result)
    assert all(p.read_bytes()==body for p,body in before.items())
    assert not (folder/'capture-retention.jsonl').exists()


def test_source_and_report_references_are_retained(tmp_path):
    folder=run(tmp_path);docs=tmp_path/'docs';docs.mkdir()
    (docs/'case.md').write_text('evidence/runtime/current/frame-0002.png')
    build=tmp_path/'build';build.mkdir()
    write_json(build/'verification.json',dict(frame=str(folder/'frame-0005.json')))
    nested=build/'independent-audit';nested.mkdir()
    write_json(nested/'receipt.json',dict(frame=str(folder/'frame-0006.json')))
    kept=retention._reference_keep(tmp_path)
    assert folder/'frame-0002.png' in kept and folder/'frame-0005.png' in kept
    assert folder/'frame-0006.png' in kept


def test_module_run_alias_pins_a_distant_function_fixture_without_executing_source(tmp_path):
    folder=run(tmp_path);source=tmp_path/'tests/test_fixture.py';source.parent.mkdir()
    source.write_text("CAPTURES = ROOT / 'evidence/runtime/current'\n"+'# gap\n'*300+
        "def check():\n    raise AssertionError('never execute source')\n    return CAPTURES / 'frame-0005.png'\n")
    kept=retention._reference_keep(tmp_path)
    assert folder/'frame-0005.png' in kept and folder/'frame-0005.json' in kept
    plan=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    assert all(Path(row['path']).name!='frame-0005.png' for row in plan['files'])


def test_parametrized_frame_stems_bind_to_their_function_run(tmp_path):
    folder=run(tmp_path);source=tmp_path/'tests/test_fixture.py';source.parent.mkdir()
    source.write_text("@pytest.mark.parametrize('name', ['frame-0005','frame-0006'])\n"
        "def check(name):\n"+'    # gap\n'*100+
        "    path = ROOT / 'evidence/runtime/current' / (name + '.json')\n")
    kept=retention._reference_keep(tmp_path)
    assert all(folder/(name+suffix) in kept for name in ('frame-0005','frame-0006') for suffix in ('.json','.png'))


def test_unknown_python_syntax_cannot_silently_drop_source_pins(tmp_path):
    run(tmp_path);source=tmp_path/'tests/test_fixture.py';source.parent.mkdir()
    source.write_text('def unfinished(')
    with pytest.raises(SyntaxError):retention._reference_keep(tmp_path)


def test_saved_administrative_plan_does_not_pin_its_own_deletion_targets(tmp_path):
    folder=run(tmp_path);build=tmp_path/'build';build.mkdir()
    result=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    write_json(build/'plan.json',result)
    repeated=retention.plan(tmp_path,folder,26000,budget=result['budget'])
    assert repeated['files']==result['files']


def test_reference_added_during_durable_intent_preserves_pixels(tmp_path,monkeypatch):
    import os
    folder=run(tmp_path);config=tmp_path/'config';config.mkdir()
    result=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    target=tmp_path/result['files'][0]['path']
    original=target.read_bytes();sync=os.fsync;added=False
    def add_reference(handle):
        nonlocal added
        sync(handle)
        if not added:
            added=True
            write_json(config/'new-pending.json',dict(proof=str(target)))
    monkeypatch.setattr(os,'fsync',add_reference)
    with pytest.raises(ValueError,match='references changed'):
        retention.apply(tmp_path,folder,result)
    assert target.read_bytes()==original


def test_no_unproven_or_active_foreign_run_is_reclaimed(tmp_path):
    foreign=run(tmp_path,'aaa-active')
    for n in range(6):run(tmp_path,f'z{n}')
    current=tmp_path/'evidence/runtime/z5'
    result=retention.plan(tmp_path,current,26000,budget=make_pressure(tmp_path))
    assert not any('aaa-active' in row['path'] for row in result['files'])
    assert all(p.exists() for p in foreign.glob('frame-*.png'))


def test_non_runtime_diagnostics_do_not_gain_cleanup_permission(tmp_path):
    run(tmp_path);other=tmp_path/'build/replay';other.mkdir(parents=True)
    result=retention.plan(tmp_path,other,26000,budget=make_pressure(tmp_path))
    assert not result['sufficient'] and not result['files']


def test_installed_app_capture_uses_project_cap(tmp_path):
    folder=run(tmp_path);app=tmp_path/'dist/MaaLimbus';app.mkdir(parents=True)
    result=retention.plan(app,folder,26000,budget=make_pressure(tmp_path))
    assert result['root']==str(tmp_path) and result['sufficient']


def test_installed_runtime_model_pins_its_original_training_capture(tmp_path):
    folder=run(tmp_path)
    model=tmp_path/'dist/MaaLimbus/assets/resource/base/model/custom';model.mkdir(parents=True)
    write_json(model/'model-card.json',dict(training_frame=str(folder/'frame-0002.json')))
    assert folder/'frame-0002.png' in retention._reference_keep(tmp_path)


def test_view_gesture_intent_pins_its_before_and_first_successor_image(tmp_path):
    folder=run(tmp_path);path=folder/'events.jsonl'
    events=[json.loads(line) for line in path.read_text().splitlines()]
    at=next(i for i,r in enumerate(events) if r.get('frame')=='frame-0005.png')
    events.insert(at+1,dict(event='map_view_intent',frame='frame-0005',kind='zoom'))
    path.write_text('\n'.join(json.dumps(row) for row in events)+'\n')
    eligible={p.stem for p,record in retention._run_rows(folder,True,8)}
    assert 'frame-0002' in eligible
    assert 'frame-0005' not in eligible and 'frame-0006' not in eligible


@pytest.mark.parametrize('offline_maintenance',[False,True])
def test_journal_pressure_reclaims_only_old_intermediate_pixels_offline(tmp_path,monkeypatch,offline_maintenance):
    import sys
    import cv2
    import numpy as np
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
    import recognition
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current',history_maintenance=offline_maintenance)
    image=np.random.default_rng(4).integers(0,256,(200,300,3),dtype=np.uint8)
    for n in range(10):
        name=journal.frame(image,[],'MAP');journal.record('map_observed',frame=name+'.png')
    old=journal.directory/'frame-0002.json';original=old.read_bytes()
    _,encoded=cv2.imencode('.png',image,[cv2.IMWRITE_PNG_COMPRESSION,6])
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+2_000_000+len(encoded)-10000)
    if not offline_maintenance:
        assert journal.frame(image,[],'MAP') == 'frame-0011'
        assert old.with_suffix('.png').exists() and old.read_bytes()==original
        return
    name=journal.frame(image,[],'MAP')
    assert name=='frame-0011' and old.read_bytes()==original
    assert not old.with_suffix('.png').exists()
    assert (journal.directory/'frame-0001.png').exists()
    record=json.loads((journal.directory/(name+'.json')).read_text())
    assert record['image_sha256']==digest(journal.directory/(name+'.png'))
    assert workspace.size(tmp_path)<=workspace.BUDGET_BYTES


def test_animation_scene_oscillation_keeps_examples_inputs_and_json_not_every_png(tmp_path):
    folder=run(tmp_path)
    for n,path in enumerate(sorted(folder.glob('frame-*.json')),1):
        data=json.loads(path.read_text());data['scene']='BATTLE_HUD' if n%2 else 'UNKNOWN'
        write_json(path,data)
    metadata={p:p.read_bytes() for p in folder.glob('*.json')}
    result=retention.plan(tmp_path,folder,26000,budget=make_pressure(tmp_path))
    assert result['sufficient']
    assert [Path(r['path']).name for r in result['files']]==['frame-0005.png','frame-0006.png']
    retention.apply(tmp_path,folder,result)
    assert all(p.read_bytes()==body for p,body in metadata.items())
    assert all((folder/f'frame-{n:04}.png').exists() for n in (1,2,3,4,7,14))


def test_real_page_boundaries_and_referenced_transient_frame_remain_protected(tmp_path):
    folder=run(tmp_path)
    scenes=['MAP']*4+['BATTLE_HUD','UNKNOWN','BATTLE_HUD','VICTORY','GIFT_PICK',
                      'BATTLE_HUD','UNKNOWN','BATTLE_HUD','UNKNOWN','UNKNOWN']
    for path,scene in zip(sorted(folder.glob('frame-*.json')),scenes):
        record=json.loads(path.read_text());record['scene']=scene;write_json(path,record)
    eligible={p.stem for p,record in retention._run_rows(folder,True,2)}
    assert 'frame-0012' in eligible
    assert all(f'frame-{n:04}' not in eligible for n in (1,3,4,5,6,7,8,9,10,11,13,14))
    config=tmp_path/'config';config.mkdir()
    write_json(config/'pending.json',dict(proof=str(folder/'frame-0012.json')))
    result=retention.plan(tmp_path,folder,26000,recent=2,budget=make_pressure(tmp_path))
    assert not any(Path(row['path']).stem=='frame-0012' for row in result['files'])


@pytest.mark.parametrize('current,passed,compact',[(True,True,False),(False,False,False),
    (False,None,False),(False,True,True)])
def test_only_old_successfully_closed_sessions_compact_ordinary_input_boundaries(tmp_path,current,passed,compact):
    folder=run(tmp_path,closed=True);path=folder/'events.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]['passed']=passed
    at=next(i for i,r in enumerate(rows) if r.get('frame')=='frame-0009.png')
    rows.insert(at+1,dict(event='window_intent'))
    path.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    eligible={p.stem for p,record in retention._run_rows(folder,current,2)}
    assert ('frame-0003' in eligible)==compact
    assert ('frame-0004' in eligible)==compact
    assert 'frame-0009' not in eligible and 'frame-0010' not in eligible
    assert 'frame-0001' not in eligible and 'frame-0014' not in eligible


def test_old_successful_session_still_keeps_unknown_exploration_before_after(tmp_path):
    folder=run(tmp_path,closed=True);path=folder/'events.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()];rows[-1]['passed']=True
    at=next(i for i,r in enumerate(rows) if r.get('frame')=='frame-0005.png')
    rows.insert(at+1,dict(event='unknown_exploration_intent'))
    path.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    eligible={p.stem for p,record in retention._run_rows(folder,False,2)}
    assert 'frame-0005' not in eligible and 'frame-0006' not in eligible


@pytest.mark.parametrize('fault',[None,'input','not_null','not_stopped','timeout','current'])
def test_closed_null_observation_can_compact_repeated_nonmap_captures_only_with_complete_proof(tmp_path,fault):
    folder=run(tmp_path,'map-live-probe');events=folder/'events.jsonl'
    rows=[json.loads(line) for line in events.read_text().splitlines()]
    rows=[r for r in rows if r['event']!='window_intent']
    if fault=='input':rows.append(dict(event='party_intent',input_sent=True))
    events.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    for path in folder.glob('frame-*.json'):
        record=json.loads(path.read_text());record['scene']='STAR_GRACES';write_json(path,record)
    result=dict(controller='Maa AdbController',input_method='Null',input_sent=False,
        stop_confirmed=True,task_result=dict(stop_confirmed=True,timed_out=False,interrupted=False))
    if fault=='not_null':result['input_method']='Maatouch'
    elif fault=='not_stopped':result['task_result']['stop_confirmed']=False
    elif fault=='timeout':result['task_result']['timed_out']=True
    write_json(folder/'result.json',result)
    eligible={p.stem for p,record in retention._run_rows(folder,fault=='current',8)}
    if fault is None:assert eligible=={f'frame-{n:04}' for n in range(2,7)}
    else:assert eligible==set()


@pytest.mark.parametrize('fault', [None, 'no_home', 'wrong_before', 'extra_input', 'bad_wait'])
def test_answered_login_preserves_causal_pair_and_retires_repeated_waits(tmp_path, fault):
    import cv2
    import numpy as np

    folder = tmp_path / 'evidence' / 'runtime' / 'login'
    folder.mkdir(parents=True)
    rows = [dict(event='mirror_loop_start', run_scope='team2')]
    scenes = ('TITLE', 'TITLE', 'UNKNOWN', 'TITLE', 'TITLE', 'LOADING', 'LOADING', 'HOME')
    for number, scene in enumerate(scenes, 1):
        name = f'frame-{number:04}'
        png = folder / (name + '.png')
        assert cv2.imwrite(str(png), np.full((12, 16, 3), number, dtype=np.uint8))
        image_hash = digest(png)
        write_json(png.with_suffix('.json'), dict(scene=scene, image_sha256=image_hash,
                                                  size=[16, 12], utc='2026-11-20T00:00:00+00:00'))
        rows.append(dict(event='map_observed', frame=name, scene=scene,
                         image_sha256=image_hash, input_sent=False))
        if number == 1:
            rows.append(dict(event='window_intent', reason='resume_login_with_its_own_start_caption',
                             frame=name, page=scene, image_sha256=image_hash))
            rows.append(dict(event='login_start_sent', frame=name, input_sent=True))
        elif scene != 'HOME':
            wait_page = 'TITLE' if fault == 'bad_wait' and number == 7 else scene
            rows.append(dict(event='login_response_wait', frame=name, page=wait_page, input_sent=False))
        if number == 4 and fault == 'extra_input':
            rows.append(dict(event='additional_input', input_sent=True))
    if fault != 'no_home':
        rows.append(dict(event='login_successor_observed', before='frame-0002' if fault == 'wrong_before'
                         else 'frame-0001', after='frame-0008', page='HOME', input_sent=False))
    rows.append(dict(event='mirror_loop_stopped'))
    (folder / 'events.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf8')
    config = tmp_path / 'config'
    config.mkdir()
    write_json(config / 'pending.json', dict(pending=str(folder / 'frame-0005.json')))
    for directory in (None, folder):
        groups = retention.diagnostic_groups(tmp_path, directory, recent=2)
        eligible = {path.stem for group in groups for path, _, _ in group}
        assert eligible == ({'frame-0004'} if fault is None else set())
