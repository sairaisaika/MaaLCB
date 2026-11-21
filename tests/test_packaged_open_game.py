"""Cold-start verification cannot silently weaken the ordinary task preflight."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('packaged_open_game',ROOT/'tools/verify_packaged_mirror_loop.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


@pytest.mark.parametrize('package',['app.lawnchair','com.android.launcher3','com.ProjectMoon.LimbusCompany'])
def test_explicit_open_only_accepts_the_target_or_an_independent_launcher(package):
    driver.check_open_game_foreground('mCurrentFocus=Window{abc u0 '+package+'/.Activity}')


@pytest.mark.parametrize('foreground',[None,'','mCurrentFocus=Window{abc u0 com.hypergryph.arknights/.Unity}',
                                     'mCurrentFocus=Window{abc u0 com.bilibili.fatego/.Activity}'])
def test_foreign_or_unknown_foreground_does_not_authorize_launch(foreground):
    with pytest.raises(ValueError):driver.check_open_game_foreground(foreground)


def test_observe_only_never_authorizes_a_start_app_call():
    with pytest.raises(ValueError):
        driver.check_open_game_foreground('mCurrentFocus=Window{abc u0 app.lawnchair/.Launcher}',observe_only=True)


class Tasker:
    def __init__(self):self.tasks=[]
    def post_task(self,name):self.tasks.append(name);return 'own-job'


@pytest.mark.parametrize('fault',['none','already','missing_result','foreign_reason','task_failed','timeout','unconfirmed'])
def test_actual_task_end_and_owned_named_result_are_both_required(tmp_path,monkeypatch,fault):
    # Source protocol fixture; live acceptance is the actual frozen task.
    monkeypatch.setattr(driver,'ROOT',tmp_path)
    tasker=Tasker()
    def wait(tasker,job,*,deadline):
        assert job=='own-job' and deadline>0
        if fault!='missing_result':
            (tmp_path/'agent-result.json').write_text(json.dumps(dict(passed=True,input_sent=fault!='already',
                reason='foreign' if fault=='foreign_reason' else
                'game_already_foreground' if fault=='already' else 'game_foreground_after_native_launch')))
        return dict(task_succeeded=fault!='task_failed',timed_out=fault=='timeout',
                    interrupted=False,stop_confirmed=fault!='unconfirmed')
    result=driver.open_game_first(tasker,tmp_path,wait=wait)
    assert result['passed'] is (fault in ('none','already')) and tasker.tasks==['OpenGameTask']
    if fault!='missing_result':
        assert (tmp_path/'open-game-result.json').read_bytes()==(tmp_path/'agent-result.json').read_bytes()


def test_existing_result_is_not_overwritten_or_interpreted_as_a_new_launch(tmp_path):
    path=tmp_path/'agent-result.json';path.write_bytes(b'{"old":"retain"}')
    tasker=Tasker()
    with pytest.raises(ValueError,match='already used'):driver.open_game_first(tasker,tmp_path)
    assert tasker.tasks==[] and path.read_bytes()==b'{"old":"retain"}'


@pytest.mark.parametrize('changed',[False,True])
def test_mirror_result_cannot_be_the_preceding_open_game_success(tmp_path,changed):
    body=b'{"passed":true,"reason":"game_already_foreground"}'
    source=tmp_path/'agent-result.json';saved=tmp_path/'open-game-result.json'
    source.write_bytes(body);saved.write_bytes(body+b' ' if changed else body)
    if changed:
        with pytest.raises(ValueError,match='copy differs'):driver.handoff_open_game_result(tmp_path)
        assert source.read_bytes()==body
    else:
        driver.handoff_open_game_result(tmp_path)
        assert not source.exists() and saved.read_bytes()==body
