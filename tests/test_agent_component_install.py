"""Agent-only installation preserves private state and rolls back actual files."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import refreeze_agent as installer


class Lease:
    def __init__(self,path):self.closed=False
    def close(self):self.closed=True


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'project';app=root/'dist/MaaLimbus';old=app/'agent'
    old.mkdir(parents=True);(old/'MaaLimbusAgent.exe').write_bytes(b'old-agent')
    (app/'build-info.json').write_text('{"project":"MaaLimbus"}')
    (app/'interface.json').write_text(json.dumps(dict(name='MaaLimbus',interface_version=2,
        version='v0.1.2',github='https://github.com/sairaisaika/MaaLCB')))
    for parent in (root/'config',app/'config'):
        parent.mkdir(parents=True);(parent/'user-run-ledger.json').write_bytes(b'private-state')
    (root/'assets').mkdir();(root/'assets/locale.json').write_bytes(b'new-resource')
    (root/'assets/interface.json').write_text(json.dumps(dict(
        name='MaaLimbus',interface_version=2,version='v0.0.0',
        icon='./icon.png',languages={'en_us':'./locale.json'},
        resource=[{'path':['./resource/base']}],option={'SkillMode':{}})))
    (app/'assets').mkdir();(app/'assets/locale.json').write_bytes(b'old-resource')
    candidate=tmp_path/'candidate';candidate.mkdir();(candidate/'MaaLimbusAgent.exe').write_bytes(b'new-agent')
    monkeypatch.setattr(installer,'source_snapshot',lambda root: {'assets/locale.json':installer.digest(root/'assets/locale.json')})
    monkeypatch.setattr(installer.subprocess,'check_output',lambda *a,**k: 'revision' if k.get('text') else b'')
    return root,app,candidate


def test_verified_candidate_replaces_only_public_components(tmp_path,monkeypatch):
    root,app,candidate=fixture(tmp_path,monkeypatch)
    report=installer.install_agent(root,app,candidate,validator=lambda a:dict(passed=True),
                                   process_check=lambda a:None,lease_factory=Lease)
    assert report['passed'] and report['changed_assets']==2
    interface=json.loads((app/'interface.json').read_text())
    assert interface['version']=='v0.1.2'
    assert interface['languages']['en_us']=='assets/locale.json'
    assert 'SkillMode' in interface['option']
    assert (app/'agent/MaaLimbusAgent.exe').read_bytes()==b'new-agent'
    assert report['rollback_agent'] is None
    assert not list(app.glob('agent.backup-*'))
    assert (app/'assets/locale.json').read_bytes()==b'new-resource'
    assert (root/'config/user-run-ledger.json').read_bytes()==b'private-state'
    assert (app/'config/user-run-ledger.json').read_bytes()==b'private-state'


@pytest.mark.parametrize('failure',['raised','negative_verdict'])
def test_failed_actual_validation_restores_agent_resources_and_metadata(tmp_path,monkeypatch,failure):
    root,app,candidate=fixture(tmp_path,monkeypatch)
    before=(app/'build-info.json').read_bytes()
    interface_before=(app/'interface.json').read_bytes()
    def validate(a):
        assert (a/'agent/MaaLimbusAgent.exe').read_bytes()==b'new-agent'
        assert 'SkillMode' in json.loads((a/'interface.json').read_text())['option']
        if failure=='raised':raise RuntimeError('injected validator failure')
        return dict(passed=False)
    with pytest.raises((RuntimeError,ValueError)):
        installer.install_agent(root,app,candidate,validator=validate,
                                process_check=lambda a:None,lease_factory=Lease)
    assert (app/'agent/MaaLimbusAgent.exe').read_bytes()==b'old-agent'
    assert (app/'assets/locale.json').read_bytes()==b'old-resource'
    assert (app/'build-info.json').read_bytes()==before
    assert (app/'interface.json').read_bytes()==interface_before


def test_insufficient_peak_space_does_not_start_swap(tmp_path,monkeypatch):
    root,app,candidate=fixture(tmp_path,monkeypatch)
    def refuse(*a,**k):raise ValueError('workspace budget exceeded')
    monkeypatch.setattr(installer,'require_space',refuse)
    with pytest.raises(ValueError,match='budget exceeded'):
        installer.install_agent(root,app,candidate,validator=lambda a:dict(passed=True),
                                process_check=lambda a:None,lease_factory=Lease)
    assert (app/'agent/MaaLimbusAgent.exe').read_bytes()==b'old-agent'
    assert not list(app.glob('agent.staging-*'))


@pytest.mark.parametrize('failure',[None,'raised','negative_verdict'])
def test_launcher_swap_preserves_agent_assets_and_independent_fingerprint(tmp_path,monkeypatch,failure):
    root,app,candidate=fixture(tmp_path,monkeypatch)
    (root/'tools').mkdir();(root/'tools/launch_app.py').write_bytes(b'launcher source')
    old=app/'launcher';old.mkdir();(old/'MaaLimbusLauncher.exe').write_bytes(b'old-launcher')
    (candidate/'MaaLimbusAgent.exe').unlink()
    (candidate/'MaaLimbusLauncher.exe').write_bytes(b'new-launcher')
    original=dict(project='MaaLimbus',source_snapshot={'agent':'unchanged'},source_commit='agent-revision')
    (app/'build-info.json').write_text(json.dumps(original))
    before=(app/'build-info.json').read_bytes()
    def validate(target):
        assert (target/'launcher/MaaLimbusLauncher.exe').read_bytes()==b'new-launcher'
        if failure=='raised':raise RuntimeError('injected launcher failure')
        return dict(passed=failure is None)
    options=dict(component='launcher',validator=validate,process_check=lambda a:None,lease_factory=Lease)
    if failure:
        with pytest.raises((RuntimeError,ValueError)):installer.install_agent(root,app,candidate,**options)
        assert (old/'MaaLimbusLauncher.exe').read_bytes()==b'old-launcher'
        assert (app/'build-info.json').read_bytes()==before
    else:
        report=installer.install_agent(root,app,candidate,**options)
        info=json.loads((app/'build-info.json').read_text())
        assert report['component']=='launcher' and report['changed_assets']==0
        assert info['source_snapshot']==original['source_snapshot']
        assert info['source_commit']==original['source_commit']
        assert info['launcher_component']['entry_sha256']==installer.digest(root/'tools/launch_app.py')
    assert (app/'agent/MaaLimbusAgent.exe').read_bytes()==b'old-agent'
    assert (app/'assets/locale.json').read_bytes()==b'old-resource'
    assert (root/'config/user-run-ledger.json').read_bytes()==b'private-state'
