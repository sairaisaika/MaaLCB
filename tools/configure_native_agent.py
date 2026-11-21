"""Enable MXU's existing native TCP compatibility setting in the closed app."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.native_agent import tcp_compatibility
from maalimbus.storage import read_json,write_json
from maalimbus.update_install import closed_app
from maalimbus.workspace import reserve_output


if __name__=='__main__':
    app=ROOT/'dist/MaaLimbus'
    closed_app(app)
    path=app/'config/mxu-MaaLimbus.json'
    before=path.read_bytes()
    original=json.loads(before)
    patched=tcp_compatibility(original)
    changed=patched!=original
    if changed:
        reserve_output(path,len(before)*2+8192,application_root=app)
        backup=path.with_name(path.name+'.pre-native-tcp')
        if backup.exists():raise ValueError('Compatibility backup exists; inspect before changing settings again')
        backup.write_bytes(before)
        write_json(path,patched)
        actual=read_json(path)
        if 'tcpCompatMode' in original['settings']:
            actual['settings']['tcpCompatMode']=original['settings']['tcpCompatMode']
        else:
            actual['settings'].pop('tcpCompatMode',None)
        if actual!=original:
            path.write_bytes(before)
            raise ValueError('Unexpected MXU setting change; original bytes restored')
    report=dict(changed=changed,tcp_compat_mode=True,other_values_preserved=True,
        before_sha256=hashlib.sha256(before).hexdigest(),
        after_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        game_input=False,resource_budget_changed=False)
    write_json(ROOT/'build/native-agent-compat-settings.json',report)
    print(json.dumps(report,indent=2))
