"""Exercise installed external-helper recovery on a tiny interrupted-app fixture.

Uses the actual frozen launcher and its installed recovery code, with retained
GitHub metadata and no network, GUI or game input. This is not a full release
installation or a desktop-shortcut recovery claim.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from maalimbus.storage import read_json, write_json
from maalimbus.update_install import closed_app, file_digest, private_hashes
from maalimbus.update_session import UpdateSession, snapshot
from maalimbus.workspace import reserve_output, size
from verify_installed_launcher import invoke


def verify(launcher_report):
    app = ROOT/'dist/MaaLimbus'
    closed_app(app)
    known = read_json(launcher_report)
    helper = Path(known['helper_directory'])/'MaaLimbusLauncher.exe'
    if (known.get('passed') is not True or helper.parent.parent != app.parent or
            file_digest(helper) != known['launcher_sha256'] or
            file_digest(app/'launcher/MaaLimbusLauncher.exe') != known['launcher_sha256']):
        raise ValueError('Retained verification does not identify the installed helper')
    actual_private = private_hashes(app)
    canonical = snapshot(ROOT/'config')
    cache = read_json(app/'config/user-update-state.json')
    if (cache.get('payload') or {}).get('tag_name') != 'v0.2.0':
        raise ValueError('This offline scenario requires retained v0.2.0 metadata')
    reserve_output(ROOT/'build', 1_000_000)
    with tempfile.TemporaryDirectory(prefix='bounded-recovery-', dir=ROOT/'build') as temporary:
        fixture = Path(temporary).resolve()
        target = fixture/'dist/MaaLimbus'
        work = fixture/'dist/.maalimbus-startup'
        write_json(target/'interface.json', dict(name='MaaLimbus',interface_version=2,
            version='v0.2.0',github='https://github.com/sairaisaika/MaaLCB'))
        write_json(target/'config/private-sentinel.json',dict(keep='interruption fixture'))
        cache['retry_at'] = time.time()+3600
        write_json(target/'config/user-update-state.json',cache)
        before = snapshot(target)
        session = UpdateSession(target,work)
        if session.root.exists():
            raise ValueError('New isolated fixture unexpectedly has an existing session')
        # Explicit fault fixture: these are tiny synthetic app files, not a real
        # game's ledger or a claim that a production copy was interrupted.
        shutil.copytree(target,session.backup)
        write_json(session.report,dict(schema=1,install=str(target),
            status='replacement_pending',before=before,installed=False,rolled_back=False))
        preserved = fixture/'old-app-fixture'
        if (not target.resolve().is_relative_to(fixture) or
                not preserved.resolve().is_relative_to(fixture)):
            raise ValueError('Fixture move escaped its temporary directory')
        target.rename(preserved)
        target.mkdir();(target/'partial-copy').write_bytes(b'interrupted new app')
        assert not (target/'interface.json').exists()
        try:
            output = invoke(helper,'--app',target,'--update-only')
        except subprocess.CalledProcessError as error:
            # Preserve the actual frozen traceback locally, rather than a bare
            # exit-code claim. This fixture contains no account/game state.
            print(error.stderr, file=sys.stderr)
            raise
        recovery = read_json(session.report,limit=16*1024*1024)
        after = snapshot(target)
        restored = all(after.get(name)==digest for name,digest in before.items())
        extras = set(after)-set(before)
        passed = (output['status']=='current' and output['requested'] is False and
                  output['installed'] is False and recovery['status']=='rolled_back' and
                  restored and extras=={'build/startup-update-result.json'})
        result = dict(passed=passed,scope='actual frozen external helper, synthetic interrupted app, retained offline cache',
            launcher_sha256=known['launcher_sha256'],restored_original_files=restored,
            restored_file_count=len(before),recovery_status=recovery['status'],
            startup=output,network_requested=False,gui_launched=False,game_input=False,
            production_candidate_verified=False,desktop_shortcut_recovery_verified=False)
        # Retire only this verified terminal fixture session, never an unresolved
        # rollback or another installation's temporary directory.
        owner = session._owned()
        if owner['status']=='rolled_back' and owner['install']==str(target):
            for path in list(session.root.iterdir()):
                if path != session.report: session._remove(path)
            session.report.unlink();session.root.rmdir()
    result.update(actual_private_unchanged=actual_private==private_hashes(app),
                  canonical_config_unchanged=canonical==snapshot(ROOT/'config'),
                  workspace_bytes=size(ROOT))
    result['passed'] &= result['actual_private_unchanged'] and result['canonical_config_unchanged']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher-report',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.launcher_report)
    reserve_output(args.report,65536)
    write_json(args.report,result)
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
