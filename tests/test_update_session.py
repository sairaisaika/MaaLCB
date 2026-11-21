"""Real files, compressed ZIPs and interruption recovery under both byte caps."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from maalimbus import update_session as module
from maalimbus.storage import write_json
from maalimbus.update_session import UpdateSession, snapshot
from maalimbus.update_stage import StageError
from maalimbus.workspace import size


class Lease:
    def __init__(self, path): pass
    def close(self): pass


class Crash(BaseException): pass


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'HEADROOM', 1024)
    project = tmp_path/'project'
    app = project/'dist/MaaLimbus'
    identity = dict(name='MaaLimbus', interface_version=2, version='v0.1.0',
                    github='https://github.com/sairaisaika/MaaLCB')
    write_json(app/'interface.json', identity)
    (app/'MaaLimbus.exe').write_bytes(b'old executable')
    for name in ('config', 'evidence', 'logs', 'build'):
        (app/name).mkdir()
        (app/name/'private').write_bytes(b'private sentinel')
    original = snapshot(app)
    def session(**kw):
        return UpdateSession(app, project/'dist/.maalimbus-startup',
            temporary_root=tmp_path/'temporary', project_root=project,
            process_check=lambda p: None, validator=lambda p: dict(agent_self_test=True),
            lease_factory=Lease, **kw)
    return app, project, original, session


def release(binary_bytes=20000):
    identity = dict(name='MaaLimbus', interface_version=2, version='v0.2.0',
                    github='https://github.com/sairaisaika/MaaLCB')
    files = {name:b'new fixture' for name in ('MaaLimbus.exe', 'LICENSE', 'build-info.json',
             'agent/MaaLimbusAgent.exe', 'runner/MaaLimbusRunner.exe')}
    files['MaaLimbus.exe'] = b'N'*binary_bytes
    files['interface.json'] = json.dumps(identity).encode()
    files['package-manifest.json'] = json.dumps({n:hashlib.sha256(b).hexdigest()
                                                for n,b in files.items()}).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items(): archive.writestr(name,data)
    data = out.getvalue()
    payloads = {'MaaLimbus-win-x64.zip': data,
                'SHA256SUMS': (hashlib.sha256(data).hexdigest()+'  MaaLimbus-win-x64.zip').encode()}
    info = dict(tag_name='v0.2.0',assets=[dict(name=n,size=len(b),
        digest='sha256:'+hashlib.sha256(b).hexdigest(),browser_download_url=
        'https://github.com/sairaisaika/MaaLCB/releases/download/v0.2.0/'+n)
        for n,b in payloads.items()])
    def transport(url,path,*args): Path(path).write_bytes(payloads[url.rsplit('/',1)[1]])
    return info, transport


def stage(session, **kw):
    info, transport = release(**kw)
    return session.stage(info, session.work/'unused', transport=transport)


def test_real_stage_install_keeps_one_backup_without_project_candidate(fixture):
    app, project, original, factory = fixture
    s = factory(project_budget=100000, session_budget=100000)
    staged = stage(s)
    assert staged['status']=='staged'
    assert not list(s.root.rglob('*.zip'))
    assert snapshot(app)==original
    result = s.install(staged['stage'],app)
    assert result['status']=='installed' and result['installed']
    assert 'before' not in result and 'before' in json.loads(s.report.read_text())
    assert snapshot(s.backup)==original
    assert not (s.root/'stages').exists()
    assert size(project)<100000 and size(s.root)<100000
    assert result['session_reserved_peak']<=100000
    assert (app/'MaaLimbus.exe').read_bytes()==b'N'*20000
    assert not list(project.rglob('candidate'))
    for name in ('config','evidence','logs','build'):
        assert (app/name/'private').read_bytes()==b'private sentinel'
    # A later launch doesn't replace the new app with the old retained backup.
    assert factory(project_budget=100000,session_budget=100000).recover()['status']=='installed'
    assert (app/'MaaLimbus.exe').read_bytes()==b'N'*20000
    # A new attempt reuses this session, retires its terminal backup, no history.
    stage(s)
    assert not s.backup.exists()
    assert len(list(s.root.parent.iterdir()))==1


@pytest.mark.parametrize('failure', ['throw','false','private'])
def test_validator_failure_restores_every_old_file(fixture,failure):
    app, _, original, factory = fixture
    s=factory()
    staged=stage(s)
    def validate(path):
        if failure=='throw': raise RuntimeError('secret')
        if failure=='private':
            (path/'config/private').write_bytes(b'changed')
            return dict(agent_self_test=True)
        return dict(agent_self_test=False)
    s.validator=validate
    result=s.install(staged['stage'],app)
    assert result['status']=='rolled_back' and result['rolled_back']
    assert snapshot(app)==original
    assert not (s.root/'stages').exists()
    assert 'secret' not in s.report.read_text()


def test_download_reservation_rejects_before_transport(fixture):
    _, _, original, factory = fixture
    s=factory(session_budget=3000)
    info,_=release()
    calls=[]
    with pytest.raises(ValueError,match='budget'):
        s.stage(info,s.work,transport=lambda *args:calls.append(args))
    assert calls==[] and not (s.root/'stages').exists()
    assert snapshot(s.app)==original


def test_compressed_expansion_is_reserved_before_first_extracted_file(fixture):
    _, _, original, factory = fixture
    s=factory(session_budget=100000)
    result=stage(s,binary_bytes=200000)
    assert result['status']=='failed'
    assert not (s.root/'stages').exists()
    assert size(s.root)<100000 and snapshot(s.app)==original


def test_project_growth_rejected_before_backup_or_removal(fixture):
    app, project, original, factory = fixture
    s=factory(project_budget=size(project)+3000)
    staged=stage(s)
    result=s.install(staged['stage'],app)
    assert result['status']=='aborted_before_replace'
    assert not s.backup.exists() and snapshot(app)==original


def test_old_app_plus_candidate_must_fit_temporary_budget(fixture):
    app, _, _, factory=fixture
    (app/'old-asset').write_bytes(b'O'*80000)
    before=snapshot(app)
    s=factory(session_budget=100000)
    staged=stage(s)
    result=s.install(staged['stage'],app)
    assert result['status']=='aborted_before_replace'
    assert not s.backup.exists() and snapshot(app)==before


def interrupt_replacement(s, staged, monkeypatch):
    real=module.shutil.copytree
    def copy(source,dest,*args,**kw):
        if Path(source)==Path(staged['package']) and Path(dest)==s.app:
            (s.app).mkdir()
            (s.app/'partial').write_bytes(b'incomplete new app')
            raise Crash()
        return real(source,dest,*args,**kw)
    with monkeypatch.context() as m:
        m.setattr(module.shutil,'copytree',copy)
        with pytest.raises(Crash): s.install(staged['stage'],s.app)
    assert json.loads(s.report.read_text())['status']=='replacement_pending'


def test_next_launcher_restores_interrupted_cross_volume_copy(fixture,monkeypatch):
    app, _, original, factory=fixture
    s=factory()
    staged=stage(s)
    interrupt_replacement(s,staged,monkeypatch)
    assert not (app/'interface.json').exists()
    result=factory().recover()
    assert result['status']=='rolled_back' and snapshot(app)==original


def test_corrupt_backup_never_deletes_current_partial_app(fixture,monkeypatch):
    app, _, _, factory=fixture
    s=factory()
    staged=stage(s)
    interrupt_replacement(s,staged,monkeypatch)
    (s.backup/'MaaLimbus.exe').write_bytes(b'tampered')
    partial=snapshot(app)
    with pytest.raises(StageError,match='inspection'): factory().recover()
    assert snapshot(app)==partial
    assert json.loads(s.report.read_text())['status']=='rollback_failed'


def test_interrupted_backup_keeps_original_and_can_start_fresh(fixture,monkeypatch):
    app, _, original, factory=fixture
    s=factory()
    staged=stage(s)
    real=module.shutil.copytree
    def copy(source,dest,*args,**kw):
        if Path(dest)==s.backup:
            s.backup.mkdir();(s.backup/'partial').write_bytes(b'incomplete backup')
            raise Crash()
        return real(source,dest,*args,**kw)
    with monkeypatch.context() as m:
        m.setattr(module.shutil,'copytree',copy)
        with pytest.raises(Crash): s.install(staged['stage'],app)
    resumed=factory()
    assert resumed.recover()['status']=='aborted_before_replace'
    assert snapshot(app)==original
    assert stage(resumed)['status']=='staged' and not resumed.backup.exists()


def test_failed_restore_stays_pending_and_recovery_uses_same_backup(fixture,monkeypatch):
    app, _, original, factory=fixture
    s=factory();staged=stage(s)
    s.validator=lambda p: (_ for _ in ()).throw(ValueError('verification failed'))
    real=module.shutil.copytree
    def copy(source,dest,*args,**kw):
        if Path(source)==s.backup: raise OSError('injected restore failure')
        return real(source,dest,*args,**kw)
    with monkeypatch.context() as m:
        m.setattr(module.shutil,'copytree',copy)
        result=s.install(staged['stage'],app)
    assert result['status']=='rollback_failed'
    with pytest.raises(StageError,match='recovery'): stage(s)
    assert factory().recover()['status']=='rolled_back'
    assert snapshot(app)==original


def test_session_never_claims_or_cleans_an_unowned_directory(fixture):
    app, _, original, factory=fixture
    s=factory();s.root.mkdir(parents=True)
    (s.root/'keep').write_bytes(b'not owned')
    with pytest.raises(StageError,match='Unowned'): stage(s)
    assert (s.root/'keep').read_bytes()==b'not owned'
    assert snapshot(app)==original


@pytest.mark.parametrize('kwargs',[dict(project_budget=3000000001),dict(session_budget=1000000001)])
def test_caps_cannot_be_raised(fixture,kwargs):
    with pytest.raises(StageError,match='hard limits'): fixture[3](**kwargs)


def test_default_session_is_stable_even_when_temp_falls_back_inside_project(tmp_path,monkeypatch):
    import tempfile
    project=tmp_path/'project';app=project/'dist/MaaLimbus'
    monkeypatch.setattr(tempfile,'gettempdir',lambda: str(app/'launcher'))
    first=UpdateSession(app,project/'dist/.maalimbus-startup')
    monkeypatch.setattr(tempfile,'gettempdir',lambda: str(tmp_path/'another-os-temp'))
    second=UpdateSession(app,project/'dist/.maalimbus-startup')
    assert first.root==second.root and first.root.parent==project.parent
    assert not first.root.is_relative_to(project)
