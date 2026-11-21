"""A registration/probe failure must still close its owned, non-game child."""
import json
from types import SimpleNamespace
import subprocess

import pytest

from tools import verify_packaged_agent_ipc as ipc


def fake_session(monkeypatch,tmp_path,mode='ready'):
    import maa.agent_client,maa.library,maa.resource
    state=SimpleNamespace(disconnected=False,terminated=False,waited=False)
    class Client:
        identifier='isolated-offline-probe'
        custom_action_list=['limbus_main_task']
        def bind(self,resource):return True
        def set_timeout(self,value):pass
        def connect(self):return mode!='not_connected'
        def disconnect(self):state.disconnected=True
    class Child:
        returncode=None
        def poll(self):return self.returncode
        def wait(self,timeout):
            state.waited=True
            if mode=='hang' and not state.terminated:
                raise subprocess.TimeoutExpired('owned input-free child',timeout)
            self.returncode=-15 if state.terminated else 0
            return self.returncode
        def terminate(self):
            assert state.disconnected,'Explicit disconnect must precede termination'
            state.terminated=True
    monkeypatch.setattr(ipc,'ROOT',tmp_path)
    monkeypatch.setattr(maa.library.Library,'open',lambda *a,**kw:None)
    monkeypatch.setattr(maa.resource,'Resource',lambda:object())
    monkeypatch.setattr(maa.agent_client,'AgentClient',Client)
    monkeypatch.setattr(ipc.subprocess,'Popen',lambda *a,**kw:Child())
    return state


def test_failed_connection_never_invokes_the_probe(monkeypatch,tmp_path):
    state=fake_session(monkeypatch,tmp_path,'not_connected')
    result=ipc.verify('ipc',probe=lambda *a:pytest.fail('Unconnected probe executed'))
    assert not result['passed'] and not result['connected']
    assert state.disconnected and state.waited


def test_probe_exception_remains_a_failure_and_the_child_is_closed(monkeypatch,tmp_path):
    state=fake_session(monkeypatch,tmp_path)
    def fail(*a):raise ValueError('independent observation absent')
    result=ipc.verify('ipc',probe=fail)
    assert not result['passed'] and result['error_type']=='ValueError'
    assert state.disconnected and state.waited and not state.terminated
    assert json.loads((tmp_path/'build/agent-ipc-ipc/result.json').read_text())['passed'] is False


def test_forced_cleanup_cannot_be_reported_as_success(monkeypatch,tmp_path):
    state=fake_session(monkeypatch,tmp_path,'hang')
    result=ipc.verify('ipc')
    assert not result['passed'] and result['terminated_after_disconnect']
    assert state.disconnected and state.terminated


@pytest.mark.parametrize('answer',[{'passed':'true'},{'passed':False},None])
def test_registration_does_not_substitute_for_a_positive_probe(monkeypatch,tmp_path,answer):
    state=fake_session(monkeypatch,tmp_path)
    result=ipc.verify('ipc',probe=lambda *a:answer)
    assert result['connected'] and not result['passed']
    assert state.disconnected and state.waited
