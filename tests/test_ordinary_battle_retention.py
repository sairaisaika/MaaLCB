"""Ordinary HUD history has a quota; critical/reference proof has precedence."""
from pathlib import Path
import json
import pytest

from maalimbus import capture_retention as c, workspace
from maalimbus.storage import write_json


def fight(root, reason='start_button_submits_the_assigned_turn'):
    folder=root/'evidence/runtime/current';folder.mkdir(parents=True)
    rows=[]
    for n in range(1,33):
        name=f'frame-{n:04}';png=folder/(name+'.png');png.write_bytes(bytes([n])*10000)
        sha=c.digest(png)
        write_json(png.with_suffix('.json'),dict(scene='BATTLE_HUD',image_sha256=sha))
        rows.append(dict(event='battle_observed',frame=name,scene='BATTLE_HUD',image_sha256=sha))
        if n in (3,6,9,12,15):rows.append(dict(event='window_intent',page='BATTLE_HUD',reason=reason))
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    return folder,rows


def test_ongoing_fight_keeps_first_state_recent_window_and_last_two_input_pairs(tmp_path):
    folder,rows=fight(tmp_path)
    eligible={p.stem for p,r in c._run_rows(folder,True,8)}
    assert all(f'frame-{n:04}' in eligible for n in (3,4,6,7,9,10))
    assert all(f'frame-{n:04}' not in eligible for n in (1,12,13,15,16,25,32))
    assert c._older_hud_diagnostics(folder,rows)=={'frame-0003','frame-0006','frame-0009'}


@pytest.mark.parametrize('reason',['use_ego_skill','purchase','unknown_action'])
def test_a_nonordinary_action_never_gets_the_hud_storage_exemption(tmp_path,reason):
    folder,rows=fight(tmp_path,reason)
    assert c._older_hud_diagnostics(folder,rows)==set()
    eligible={p.stem for p,r in c._run_rows(folder,True,8)}
    assert all(f'frame-{n:04}' not in eligible for n in (3,4,6,7,9,10))


def test_missing_or_changed_next_read_does_not_answer_a_diagnostic(tmp_path):
    folder,rows=fight(tmp_path)
    for n in (4,5,6):
        (folder/f'frame-{n:04}.png').write_bytes(b'changed')
    assert 'frame-0003' not in c._older_hud_diagnostics(folder,rows)


def test_model_or_pending_reference_still_preserves_an_eligible_hud_pair(tmp_path):
    folder,rows=fight(tmp_path)
    config=tmp_path/'config';config.mkdir()
    write_json(config/'pending.json',dict(proof=str(folder/'frame-0003.json')))
    p=c.plan(tmp_path,folder,20000,budget=workspace.size(tmp_path)+19000)
    assert p['sufficient']
    assert not any(Path(row['path']).stem=='frame-0003' for row in p['files'])
