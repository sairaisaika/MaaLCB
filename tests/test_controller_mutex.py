"""Native controller exclusivity must hold across processes and threads."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

import pytest
from maalimbus import controller_lease as leases


pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows native mutex')


def test_named_controller_mutex_blocks_another_process(tmp_path,monkeypatch):
    name='Local\\MaaLimbus.Test.'+uuid.uuid4().hex
    monkeypatch.setattr(leases,'CONTROLLER_MUTEX_NAME',name)
    held=leases.ControllerLease(tmp_path/'controller.lock')
    code=('from maalimbus import controller_lease as l;import sys;'
          'l.CONTROLLER_MUTEX_NAME=sys.argv[1];'
          'x=l.ControllerLease("controller.lock");x.close()')
    environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    try:
        child=subprocess.run([sys.executable,'-c',code,name],capture_output=True,env=environment,timeout=10)
        assert child.returncode!=0 and b'another_controller_owns_game' in child.stderr
    finally:held.close()
    child=subprocess.run([sys.executable,'-c',code,name],capture_output=True,env=environment,timeout=10)
    assert child.returncode==0


def test_same_process_other_thread_cannot_reuse_controller_ownership(tmp_path,monkeypatch):
    monkeypatch.setattr(leases,'CONTROLLER_MUTEX_NAME','Local\\MaaLimbus.Test.'+uuid.uuid4().hex)
    path=tmp_path/'controller.lock';held=leases.ControllerLease.acquire(path)
    errors=[]
    def contender():
        try:leases.ControllerLease.acquire(path)
        except OSError as error:errors.append(str(error))
    try:
        thread=threading.Thread(target=contender);thread.start();thread.join(timeout=5)
        assert not thread.is_alive() and errors==['another_controller_owns_game']
        assert leases.ControllerLease.acquire(path) is held
    finally:held.close()
