"""Rebuild the closed local app's Agent with rollback and a bounded folder peak.

Build intermediates live in one temporary directory and are removed on return.
Only the final Agent and changed public runtime assets enter the project folder.
One bounded temporary rollback copy exists only during the swap and validation;
it is removed on return. No private settings, ledger or game input changes.
"""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.controller_lease import ControllerLease
from maalimbus.storage import write_json
from maalimbus.update_install import closed_app, plain_path, plain_tree, private_hashes, metadata
from maalimbus.workspace import require_space, size, BUDGET_BYTES
from maalimbus.build_fingerprint import source_snapshot
from make_local_app import freeze, packaged_interface


def digest(path):
    with Path(path).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def validate_agent(app):
    result=subprocess.run([str(app/'agent/MaaLimbusAgent.exe'),'--self-test'],cwd=app,
                          capture_output=True,text=True,timeout=120,check=True)
    proof=json.loads(result.stdout.strip())
    if not proof.get('passed') or Path(proof.get('application_root','')).resolve()!=app:
        raise ValueError('Frozen Agent self-test resolved the wrong application')
    return proof


def validate_launcher(app):
    result=subprocess.run([str(app/'launcher/MaaLimbusLauncher.exe'),
                           '--resource-diagnostics','--interval-ms','10'],cwd=app,
                          capture_output=True,text=True,timeout=30,check=True)
    snapshot=json.loads(result.stdout.strip())
    if not {'version','processes','system','gpu','process_gpu'}<=snapshot.keys():
        raise ValueError('Frozen launcher diagnostic contract differs')
    return dict(passed=True,check='read_only_resource_diagnostics',game_input=False,
                gui_launched=False)


def install_agent(root, app, candidate, *, validator=None, component='agent',
                  process_check=closed_app, lease_factory=ControllerLease):
    root,app,candidate=map(plain_path,(root,app,candidate))
    if component not in ('agent','launcher'):
        raise ValueError('Unsupported component')
    validator=validator or (validate_agent if component=='agent' else validate_launcher)
    target_component=app/component
    executable='MaaLimbusAgent.exe' if component=='agent' else 'MaaLimbusLauncher.exe'
    if app!=root/'dist/MaaLimbus' or candidate==target_component:
        raise ValueError('Invalid local component installation target')
    plain_tree(candidate)
    if not (candidate/executable).is_file():raise ValueError('Candidate component missing')
    metadata(app)
    process_check(app)
    plain_tree(target_component)
    if candidate.is_relative_to(root):
        raise ValueError('Candidate must be in the bounded external build directory')
    info_path=app/'build-info.json'
    previous_info=info_path.read_bytes()
    before=private_hashes(app)
    canonical={p.relative_to(root).as_posix():digest(p) for p in (root/'config').rglob('*') if p.is_file()}
    lease=lease_factory(root/'build/controller.lock')
    moved=False;changed=[]
    try:
        snapshot=source_snapshot(root)
        assets=[(root/name,app/name) for name in snapshot if name.startswith('assets/')
                and component=='agent' and (not (app/name).is_file() or digest(app/name)!=snapshot[name])]
        launcher_source=digest(root/'tools/launch_app.py') if component=='launcher' else None
        with tempfile.TemporaryDirectory(prefix='maalimbus-asset-rollback-') as undo:
            undo=Path(undo)
            if component=='agent':
                target=app/'interface.json'
                current=json.loads(target.read_text(encoding='utf-8-sig'))
                interface=packaged_interface(root)
                interface['version']=current['version']
                if interface!=current:
                    staged_interface=undo/'interface.json'
                    staged_interface.write_bytes(
                        (json.dumps(interface,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
                    assets.append((staged_interface,target))
            growth=max(0,size(candidate)-size(target_component))
            growth+=sum(max(0,p.stat().st_size-(target.stat().st_size if target.exists() else 0))
                        for p,target in assets)
            reservation=require_space(root,growth+1_000_000)
            backup=undo/component
            try:
                process_check(app)
                # Copy rollback before changing the installed directory, so a
                # partial removal or installation is recoverable as well.
                shutil.copytree(target_component,backup)
                moved=True
                shutil.rmtree(target_component)
                shutil.copytree(candidate,target_component)
                for number,(source,target) in enumerate(assets):
                    old=undo/str(number) if target.exists() else None
                    if old is not None:shutil.copyfile(target,old)
                    changed.append((target,old))
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,target)
                proof=validator(app)
                if not proof.get('passed'):raise ValueError('Installed component self-test failed')
                after=private_hashes(app)
                if after!=before or any(not (root/name).is_file() or digest(root/name)!=sha
                                        for name,sha in canonical.items()):
                    raise ValueError('Private configuration changed during installation')
                if snapshot!=source_snapshot(root):raise ValueError('Source changed during installation')
                if component=='launcher' and digest(root/'tools/launch_app.py')!=launcher_source:
                    raise ValueError('Launcher source changed during installation')
                if size(root)>BUDGET_BYTES:raise ValueError('Workspace exceeded its reserved budget')
                info=json.loads(previous_info)
                if component=='agent':
                    info.update(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                            source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=root)),
                            source_snapshot=snapshot,built_at=datetime.now(timezone.utc).isoformat(),
                            agent_self_test=proof,agent_rebuilt_from='tools/refreeze_agent.py',
                            agent_rebuild_note='Agent component rebuilt with source fingerprint, installed self-test and private-state preservation; MXU binary unchanged',
                                workspace_reservation=reservation)
                else:
                    info['launcher_component']=dict(source_snapshot=snapshot,
                        entry_sha256=launcher_source,installed_at=datetime.now(timezone.utc).isoformat(),
                        executable_sha256=digest(target_component/executable),self_test=proof,
                        scope='launcher only; Agent and MXU unchanged')
                write_json(info_path,info)
            except BaseException:
                for target,old in reversed(changed):
                    if old is not None:shutil.copyfile(old,target)
                    elif target.exists():target.unlink()
                if moved:
                    if target_component.exists():shutil.rmtree(target_component)
                    shutil.copytree(backup,target_component)
                info_path.write_bytes(previous_info)
                raise
        return dict(passed=True,app=str(app),component=component,rollback_agent=None,
                    rollback_policy='bounded temporary copy retained through validation only',
                    private_files_preserved=len(before),canonical_config_preserved=len(canonical),
                    changed_assets=len(changed),source_files=len(snapshot),workspace_bytes=size(root))
    finally:
        lease.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component',choices=('agent','launcher'),default='agent')
    args=parser.parse_args()
    app=ROOT/'dist/MaaLimbus'
    closed_app(app)
    snapshot=source_snapshot(ROOT)
    with tempfile.TemporaryDirectory(prefix='maalimbus-agent-build-') as work:
        entry='agent/main.py' if args.component=='agent' else 'tools/launch_app.py'
        name='MaaLimbusAgent' if args.component=='agent' else 'MaaLimbusLauncher'
        entry_sha=digest(ROOT/entry)
        candidate=freeze(ROOT/entry,name,Path(work))
        if snapshot!=source_snapshot(ROOT):raise ValueError('Source changed during freeze')
        if digest(ROOT/entry)!=entry_sha:raise ValueError('Component entry changed during freeze')
        result=install_agent(ROOT,app,candidate,component=args.component)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
