"""The actual frozen-entry preparation branch cannot update or start the GUI."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def launcher():
    spec=importlib.util.spec_from_file_location('launcher_prepare_entry',
        Path(__file__).resolve().parents[1]/'tools/launch_app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_prepare_only_reuses_bundle_and_never_calls_update_or_popen(tmp_path,monkeypatch,capsys):
    module=launcher();app=tmp_path/'dist/MaaLimbus';bundle=app/'launcher';bundle.mkdir(parents=True)
    executable=bundle/'MaaLimbusLauncher.exe';executable.write_bytes(b'launcher')
    (app/'interface.json').write_text(json.dumps(dict(name='MaaLimbus',interface_version=2,
        version='v0.1.2',github='https://github.com/sairaisaika/MaaLCB')))
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(executable))
    monkeypatch.setattr(sys,'argv',[str(executable),'--prepare-only'])
    def forbidden(*a,**k):pytest.fail('Preparation cannot update or open a process')
    monkeypatch.setattr(module,'startup_update',forbidden)
    monkeypatch.setattr(module.subprocess,'Popen',forbidden)
    module.main();first=json.loads(capsys.readouterr().out)
    module.main();second=json.loads(capsys.readouterr().out)
    assert first==second and first['prepared']
    assert first['gui_launched'] is first['update_requested'] is first['game_input'] is False
    assert len(list(app.parent.glob('.maalimbus-launcher-*')))==1


def test_prepare_only_refuses_source_entry_before_launch(monkeypatch):
    module=launcher()
    monkeypatch.delattr(sys,'frozen',raising=False)
    monkeypatch.setattr(sys,'argv',['launcher','--prepare-only'])
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2


def test_update_only_runs_startup_handling_then_returns_without_gui(tmp_path,monkeypatch,capsys):
    module=launcher();app=tmp_path/'app';app.mkdir()
    (app/'interface.json').write_text(json.dumps(dict(name='MaaLimbus',interface_version=2,
        version='v0.1.2',github='https://github.com/sairaisaika/MaaLCB')))
    monkeypatch.setattr(sys,'argv',['launcher','--app',str(app),'--update-only'])
    class Lease:
        def __init__(self,path):pass
        def close(self):pass
    monkeypatch.setattr(module,'ControllerLease',Lease)
    monkeypatch.setattr(module,'closed_app',lambda *a,**kw:None)
    calls=[]
    def update(target,work,**kw):
        calls.append(target)
        return dict(status='update_unavailable',installed=False,game_input_sent=False)
    monkeypatch.setattr(module,'startup_update',update)
    def forbidden(*a,**kw):pytest.fail('Update-only cannot open a GUI')
    monkeypatch.setattr(module.subprocess,'Popen',forbidden)
    module.main()
    assert calls==[app]
    assert json.loads(capsys.readouterr().out)['status']=='update_unavailable'


def test_external_entry_recovers_missing_app_before_reading_its_metadata(tmp_path,monkeypatch,capsys):
    module=launcher();app=tmp_path/'missing-app';order=[]
    monkeypatch.setattr(sys,'argv',['launcher','--app',str(app),'--update-only'])
    class Lease:
        def __init__(self,path):pass
        def close(self):pass
    class Session:
        def __init__(self,*a,**kw):pass
        def recover(self):
            order.append('recover');app.mkdir()
        def stage(self,*a,**kw):pass
        def install(self,*a,**kw):pass
    monkeypatch.setattr(module,'UpdateSession',Session)
    monkeypatch.setattr(module,'ControllerLease',Lease)
    monkeypatch.setattr(module,'closed_app',lambda *a,**kw:None)
    def metadata(target):
        assert target.is_dir();order.append('metadata')
    monkeypatch.setattr(module,'metadata',metadata)
    def update(*a,**kw):
        order.append('update');return dict(status='current')
    monkeypatch.setattr(module,'startup_update',update)
    module.main()
    assert order==['recover','metadata','update']
