"""HUD preflight/identity reads are distinct from the actor's before-image."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import cv2,pytest
from maalimbus.hud_evidence import diagnostic_index
from maalimbus import capture_retention as retention,workspace

SOURCE=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-134824/frame-0066.json'
pytestmark=pytest.mark.skipif(not SOURCE.with_suffix('.png').is_file(),reason='Private native HUD fixture')


def sample(tmp_path):
    run=tmp_path/'evidence/runtime/start';run.mkdir(parents=True)
    original=json.loads(SOURCE.read_text());image=cv2.imread(str(SOURCE.with_suffix('.png')))
    for n in (1,2,3):
        pixels=image.copy();pixels[0,0]=(n,n,n)
        path=run/f'frame-{n:04}.png';cv2.imwrite(str(path),pixels)
        data=deepcopy(original);data.update(frame=path.stem,utc=f'2026-11-17T20:00:0{n}+00:00',
            image_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        path.with_suffix('.json').write_text(json.dumps(data))
    rows=[dict(event='map_observed',scene='BATTLE_HUD',frame='frame-0001',input_sent=False,utc='2026-11-17T20:00:01+00:00'),
        dict(event='mirror_loop_start',run_scope='scope',utc='2026-11-17T20:00:01.5+00:00'),
        dict(event='map_observed',scene='BATTLE_HUD',frame='frame-0002',input_sent=False,utc='2026-11-17T20:00:02+00:00'),
        dict(event='battle_observed',scene='BATTLE_HUD',frame='frame-0003',utc='2026-11-17T20:00:03+00:00')]
    return run,rows


def projection(run,rows):
    (run/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    return diagnostic_index((run.parent,)).get(run,{})


def test_preflight_and_identity_replicas_are_superseded_before_first_input(tmp_path):
    run,rows=sample(tmp_path);value=projection(run,rows)
    assert value['startup_previews']=={'frame-0001','frame-0002'}
    assert value['required']=={'frame-0003'}
    eligible=retention._run_rows(run,True,2,hud_index={run:value})
    assert {p.stem for p,_ in eligible}=={'frame-0001','frame-0002'}


@pytest.mark.parametrize('fault',['turn','missing_caption','unknown','input_before_actor','foreign','stale','corrupt'])
def test_unproven_hud_equivalence_preserves_the_startup_captures(tmp_path,fault):
    run,rows=sample(tmp_path);path=run/'frame-0002.json';data=json.loads(path.read_text())
    if fault=='turn':
        for t in data['ocr']:
            if t['text'].strip().isdigit() and t['box'][0]<150 and 75<t['box'][1]<150:t['text']='99'
    elif fault=='missing_caption':data['ocr']=[t for t in data['ocr'] if t['text']!='Damage']
    elif fault=='unknown':rows[2]['scene']='UNKNOWN'
    elif fault=='input_before_actor':rows.insert(2,dict(event='unknown_exploration_intent'))
    elif fault=='foreign':rows.insert(2,dict(event='semantic_frame_proposal',episode='foreign'))
    elif fault=='stale':data['utc']='2026-11-17T20:01:02+00:00'
    else:path.with_suffix('.png').write_bytes(b'changed')
    path.write_text(json.dumps(data))
    assert not projection(run,rows).get('startup_previews')


def test_external_review_pin_wins_over_a_startup_diagnostic_role(tmp_path,monkeypatch):
    run,rows=sample(tmp_path);projection(run,rows)
    config=tmp_path/'config';config.mkdir();(config/'human-review.json').write_text(json.dumps(dict(before=str(run/'frame-0001.json'))))
    original=(run/'frame-0001.png').read_bytes();budget=workspace.size(tmp_path)+60000
    monkeypatch.setattr(workspace,'BUDGET_BYTES',budget)
    plan=retention.plan(tmp_path,run,100000,recent=2,budget=budget)
    assert plan['sufficient'] and [Path(r['path']).name for r in plan['files']]==['frame-0002.png']
    retention.apply(tmp_path,run,plan)
    assert (run/'frame-0001.png').read_bytes()==original and (run/'frame-0003.png').is_file()
