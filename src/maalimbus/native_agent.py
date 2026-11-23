"""Private, writable native socket scratch space; no system permission changes."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from .workspace import live_writes, reserve_output


@contextmanager
def native_temp(application_root):
    """Keep one short per-process directory alive for the native process session.

    Maa/ZeroMQ uses TEMP internally even with its supported loopback TCP mode.
    Never change system/user environment settings or reuse another session's
    socket directory. The caller must keep this context alive through shutdown.
    """
    app=Path(application_root).resolve()
    workspace=app.parent.parent if app.parent.name=='dist' else app
    base=workspace/'build/native-agent-tmp'
    for parent in (base,*base.parents):
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():
            raise ValueError('Native scratch directory cannot use linked paths')
    # Starting the Agent is a live task: like the evidence it writes while running, its
    # socket scratch is checked against free disk space, not against the project-folder
    # warning line. A folder 4 MB over that line once refused the start outright and
    # left the GUI on "Starting" (2026-11-22); the run itself already only warns.
    with live_writes():
        reserve_output(base,1_000_000,application_root=app)
    base.mkdir(parents=True,exist_ok=True)
    previous={key:os.environ.get(key) for key in ('TEMP','TMP')}
    with tempfile.TemporaryDirectory(prefix='n-',dir=base,ignore_cleanup_errors=True) as directory:
        directory=Path(directory)
        if len(str(directory).encode('utf-8'))>80:
            raise ValueError('Native socket scratch path is too long')
        probe=directory/'write-probe'
        probe.write_bytes(b'owned native socket scratch');probe.unlink()
        try:
            for key in previous:os.environ[key]=str(directory)
            yield directory
        finally:
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value


def tcp_compatibility(settings):
    """One explicit app-setting repair, preserving every other configuration."""
    import copy
    if not isinstance(settings,dict) or not isinstance(settings.get('settings'),dict):
        raise ValueError('Existing MXU settings object required')
    result=copy.deepcopy(settings)
    result['settings']['tcpCompatMode']=True
    return result
