"""Exercise installed preparation and startup fallback, never launch a GUI/game.

The fallback uses an isolated older metadata fixture and retained real GitHub
metadata with no uploaded assets. It is not an update installation acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.storage import read_json,write_json
from maalimbus.update_install import closed_app,private_hashes
from maalimbus.workspace import reserve_output,size


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(exe,*args):
    run=subprocess.run([str(exe),*map(str,args)],capture_output=True,text=True,
                       timeout=45,check=True,cwd=exe.parent)
    return json.loads(run.stdout)


def verify(app):
    app=app.resolve();closed_app(app)
    before=private_hashes(app)
    canonical={p.relative_to(ROOT).as_posix():digest(p) for p in (ROOT/'config').rglob('*') if p.is_file()}
    exe=app/'launcher/MaaLimbusLauncher.exe'
    first=invoke(exe,'--prepare-only');helper=Path(first['directory'])
    inventory=lambda:{p.relative_to(helper).as_posix():[digest(p),p.stat().st_mtime_ns]
                      for p in helper.rglob('*') if p.is_file()}
    saved=inventory();used=size(ROOT)
    second=invoke(exe,'--prepare-only')
    stable=first==second and saved==inventory() and used==size(ROOT)
    state=read_json(app/'config/user-update-state.json');release=state.get('payload') or {}
    if release.get('tag_name')!='v0.2.0' or release.get('assets')!=[]:
        raise ValueError('This retained-metadata scenario requires actual v0.2.0 with no uploaded assets')
    reserve_output(ROOT/'build',1_000_000)
    with tempfile.TemporaryDirectory(prefix='launcher-fallback-',dir=ROOT/'build') as temporary:
        target=Path(temporary)/'app'
        identity=dict(name='MaaLimbus',interface_version=2,
                      github='https://github.com/sairaisaika/MaaLCB',version='v0.1.2')
        write_json(target/'interface.json',identity)
        write_json(target/'config/private-sentinel.json',dict(keep='isolated fixture'))
        # Explicitly offline replay: the actual payload is retained; only the
        # isolated cache deadline changes to prevent a second public request.
        state['retry_at']=time.time()+3600
        write_json(target/'config/user-update-state.json',state)
        original=(target/'interface.json').read_bytes()
        fallback=invoke(helper/exe.name,'--app',target,'--update-only')
        preserved=((target/'interface.json').read_bytes()==original
                   and read_json(target/'config/private-sentinel.json')==dict(keep='isolated fixture'))
        assert fallback['status']=='update_unavailable' and not fallback['installed']
        assert fallback['install_attempted'] is False and fallback['requested'] is False
        assert preserved and not (Path(temporary)/'.maalimbus-startup/stages').exists()
    result=dict(scope='actual installed frozen launcher; isolated older metadata and retained release; offline fallback',
        passed=stable and preserved,helper_reused=stable,helper_files=len(saved),
        launcher_sha256=digest(exe),helper_directory=str(helper),startup_fallback=fallback,
        actual_release=dict(tag=release['tag_name'],uploaded_assets=0),
        private_files_unchanged=before==private_hashes(app),
        canonical_game_files_unchanged=all(digest(ROOT/name)==sha for name,sha in canonical.items()),
        workspace_bytes=size(ROOT),gui_launched=False,game_input=False,
        public_newer_download_verified=False)
    result['passed'] &= result['private_files_unchanged'] and result['canonical_game_files_unchanged']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'build/installed-launcher-verification.json')
    args=parser.parse_args();result=verify(ROOT/'dist/MaaLimbus')
    write_json(args.report,result);print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
