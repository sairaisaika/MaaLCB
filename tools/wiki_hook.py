"""Project selection bridge to the installed project-wiki SessionStart hook.

Reads one explicitly prepared local selection and invokes the existing saved-only
adapter. It never captures context, calls Git, controls a device or writes trust.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
SELECTION='.codex/wiki-selection.json'
MAX_INPUT=65536


def provider(version,*,codex_home=None):
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('Explicit installed project-wiki version required')
    base=Path(codex_home or os.environ.get('CODEX_HOME',Path.home()/'.codex'))
    package=base/'plugins/cache/project-wiki-internal/project-wiki'/version
    manifest=json.loads((package/'.codex-plugin/plugin.json').read_text(encoding='utf8'))
    if manifest.get('name')!='project-wiki' or manifest.get('version')!=version:
        raise ValueError('Installed Wiki provider identity differs')
    path=package/'skills/project-wiki/scripts/lifecycle.py'
    if path.is_symlink() or not path.is_file():raise ValueError('Installed lifecycle adapter absent')
    return path


def selection(root):
    path=Path(root)/SELECTION
    if not path.is_file():return None
    if path.is_symlink() or path.stat().st_size>8192:raise ValueError('Invalid Wiki selection')
    value=json.loads(path.read_bytes())
    if value.get('version')!=1 or value.get('root')!=str(Path(root).resolve()):
        raise ValueError('Wiki selection belongs to another checkout')
    packet=Path(value['packet'])
    base=(Path(root)/'build/wiki').resolve()
    if (not base.is_relative_to(Path(root).resolve()) or not packet.is_absolute()
            or not packet.resolve().is_relative_to(base)):
        raise ValueError('Selected packet must be project-local private data')
    if packet.is_symlink() or not packet.is_file() or packet.stat().st_size>4_000_000:
        raise ValueError('Invalid selected packet')
    if hashlib.sha256(packet.read_bytes()).hexdigest()!=value['packet_sha256']:
        raise ValueError('Selected packet changed')
    return value


def deliver(event,*,root=ROOT,codex_home=None):
    if not isinstance(event,dict) or event.get('hook_event_name')!='SessionStart':return None
    cwd=Path(event.get('cwd',''))
    if not cwd.is_absolute() or not cwd.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Hook event belongs to another checkout')
    for parent in (cwd.resolve(),*cwd.resolve().parents):
        if parent==Path(root).resolve():break
        if (parent/'.git').exists():raise ValueError('Nested checkout requires its own selection')
    value=selection(root)
    if value is None:return None
    ambient=os.environ.get('PROJECT_WIKI_PACKET')
    if ambient:
        if Path(ambient).resolve()==Path(value['packet']).resolve():return None
        return dict(systemMessage='MaaLimbus project Wiki selection conflicts with PROJECT_WIKI_PACKET; reconcile the explicit selections. Project delivery skipped.')
    path=provider(value['provider_version'],codex_home=codex_home)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=value['provider_sha256']:
        raise ValueError('Selected lifecycle adapter changed; reprepare explicitly')
    if hashlib.sha256(path.with_name('workflow.py').read_bytes()).hexdigest()!=value['workflow_sha256']:
        raise ValueError('Selected saved-task reader changed; reprepare explicitly')
    spec=importlib.util.spec_from_file_location('maalimbus_installed_wiki_lifecycle',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.deliver(event,value['packet'])


def main():
    try:
        raw=sys.stdin.buffer.read(MAX_INPUT+1)
        if len(raw)>MAX_INPUT:raise ValueError('Hook event oversized')
        result=deliver(json.loads(raw.decode('utf8')))
        if result is not None:print(json.dumps(result,ensure_ascii=True))
    except (OSError,ValueError,KeyError,TypeError,AttributeError,ImportError,RecursionError):
        print(json.dumps(dict(systemMessage='MaaLimbus Wiki context was not delivered. Reprepare the selected task; no game command or completion check ran.')))
    return 0


if __name__=='__main__':raise SystemExit(main())
