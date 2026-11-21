from types import SimpleNamespace
import pytest
from maalimbus.game_launch import open_game
from maalimbus.storage import read_json


class Controller:
    info=dict(type='adb',adb_path='fake-adb',adb_serial='test-device')
    def __init__(self):self.starts=[]
    def post_start_app(self,intent):
        self.starts.append(intent)
        return SimpleNamespace(done=True,succeeded=True)


class Journal:
    def record(self,*args,**kwargs):pass


def test_existing_game_does_not_restart_or_touch_current_run(tmp_path):
    controller=Controller()
    result=open_game(controller,tmp_path,Journal(),
        check_any=lambda *args:'focus com.ProjectMoon.LimbusCompany/activity',
        check_game=lambda info:'independent foreground proof')
    assert result['passed'] and not result['input_sent'] and controller.starts==[]


def test_start_intent_survives_unknown_successor_and_refuses_retry(tmp_path):
    controller=Controller()
    def missing(info):raise RuntimeError('not the game')
    result=open_game(controller,tmp_path,Journal(),check_any=lambda *args:'launcher',check_game=missing,rounds=2,interval=0)
    assert not result['passed'] and result['pending'] and len(controller.starts)==1
    assert not read_json(tmp_path/'user-open-game-transaction.json')['completed']
    with pytest.raises(ValueError,match='second start'):
        open_game(controller,tmp_path,Journal(),check_any=lambda *args:'launcher',check_game=missing)
    assert len(controller.starts)==1
    result=open_game(controller,tmp_path,Journal(),
        check_any=lambda *args:'focus com.ProjectMoon.LimbusCompany/activity',check_game=lambda info:'verified game')
    assert result['passed'] and not result['input_sent']
    assert read_json(tmp_path/'user-open-game-transaction.json')['completed']


def test_actual_controller_identity_required_before_start(tmp_path):
    controller=Controller();controller.info={'type':'win32'}
    with pytest.raises(ValueError,match='Windows'):open_game(controller,tmp_path,Journal())
    assert controller.starts==[]


def test_post_job_success_alone_does_not_prove_open(tmp_path):
    controller=Controller()
    checks=[]
    def check(info):
        checks.append(info)
        return 'fresh foreground'
    result=open_game(controller,tmp_path,Journal(),check_any=lambda *args:'launcher',check_game=check)
    assert result['passed'] and result['foreground']=='fresh foreground' and checks


def test_slow_foreground_arrival_is_observed_without_a_second_launch(tmp_path):
    controller=Controller();checks=[];waits=[]
    def later(info):
        checks.append(info)
        if len(checks)<4:raise RuntimeError('activity is still opening')
        return 'independently observed foreground'
    result=open_game(controller,tmp_path,Journal(),check_any=lambda *a:'launcher',
                     check_game=later,pause=waits.append)
    assert result['passed'] and len(controller.starts)==1 and len(checks)==4
    assert waits==[.5,.5,.5]
    assert read_json(tmp_path/'user-open-game-transaction.json')['completed']


def test_invalid_launch_poll_policy_refuses_before_input_or_intent(tmp_path):
    controller=Controller()
    with pytest.raises(ValueError,match='bounded'):
        open_game(controller,tmp_path,Journal(),rounds=0)
    assert not controller.starts and not list(tmp_path.iterdir())
