"""Explicitly prepare/select a project-wiki work packet for MaaLimbus hooks.

Preparation may read Git and run only the reviewed project router. SessionStart
delivery itself stays saved-only. Existing hook trust and provider installation
are never edited. Private packets live under build/wiki, not the public Wiki.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.workspace import require_space
from wiki_hook import provider,SELECTION,deliver,selection


def prepare(root,*,version,query,files,task_id,outcome,acceptance,capabilities):
    root=Path(root).resolve();lifecycle=provider(version)
    spec=importlib.util.spec_from_file_location('maalimbus_selected_wiki_workflow',lifecycle.with_name('workflow.py'))
    workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
    runtime=['tools/wiki_context.py','tools/wiki_router.py','tools/wiki_hook.py',
             'tools/wiki_session.py','.codex/hooks.json','docs/wiki/routes.json','AGENTS.md']
    context=workflow.capture(root,query,files,[sys.executable,str(root/'tools/wiki_context.py')],
                             runtime,allow_execution=True)
    packet=workflow.start(context,task_id,'codex',outcome,files,acceptance,capabilities)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    folder=root/'build/wiki'/stamp
    bodies={name:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
            for name,value in [('capture.json',context),('packet.json',packet)]}
    require_space(root,sum(map(len,bodies.values()))+32768)
    folder.mkdir(parents=True)
    for name,body in bodies.items():(folder/name).write_bytes(body)
    value=dict(version=1,root=str(root),packet=str(folder/'packet.json'),
               packet_sha256=hashlib.sha256(bodies['packet.json']).hexdigest(),
               provider_version=version,provider_sha256=hashlib.sha256(lifecycle.read_bytes()).hexdigest(),
               workflow_sha256=hashlib.sha256(lifecycle.with_name('workflow.py').read_bytes()).hexdigest())
    # Test the actual upstream adapter before selecting it for future host events.
    spec=importlib.util.spec_from_file_location('maalimbus_prepared_lifecycle',lifecycle)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    result=adapter.deliver(dict(hook_event_name='SessionStart',source='startup',cwd=str(root)),value['packet'])
    context_text=(result or {}).get('hookSpecificOutput',{}).get('additionalContext','')
    if not context_text:
        raise ValueError('Installed hook cannot deliver this packet; previous selection retained')
    # 0.2.17 returns a nonempty warning context when its saved index is too big.
    # A transport response is not evidence that the actual index was delivered.
    rendered=json.loads(context_text.rsplit('\n',1)[-1])
    if not isinstance(rendered,dict) or rendered.get('index_delivered') is False:
        raise ValueError('Installed hook omitted the task index; previous selection retained')
    path=root/SELECTION;path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    body=(json.dumps(value,indent=2)+'\n').encode()
    require_space(root,len(body))
    with temporary.open('wb') as handle:
        handle.write(body);handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,path)
    receipt=dict(passed=True,provider_version=version,selection=str(path),
                 packet=str(folder/'packet.json'),packet_sha256=value['packet_sha256'],
                 local_adapter_replay=True,host_trigger_observed=False,
                 host_trust_changed=False,controller_created=False,input_sent=False,
                 context_utf8_bytes=len(context_text.encode('utf8')))
    (folder/'preparation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare')
    p.add_argument('--provider-version',required=True)
    p.add_argument('--query',required=True);p.add_argument('--files',nargs='+',required=True)
    p.add_argument('--task-id',required=True);p.add_argument('--outcome',required=True)
    p.add_argument('--acceptance',action='append',required=True)
    p.add_argument('--capability',action='append',required=True)
    sub.add_parser('status')
    p=sub.add_parser('replay');p.add_argument('--source',default='resume',choices=['startup','resume','clear','compact','fork'])
    args=parser.parse_args()
    if args.action=='prepare':
        result=prepare(ROOT,version=args.provider_version,query=args.query,files=args.files,
                       task_id=args.task_id,outcome=args.outcome,acceptance=args.acceptance,
                       capabilities=args.capability)
    elif args.action=='replay':
        result=deliver(dict(hook_event_name='SessionStart',source=args.source,cwd=str(ROOT)))
    else:
        value=selection(ROOT)
        result=dict(selected=value is not None,provider_version=value['provider_version'] if value else None,
                    host_trigger_observed=False,trust_records_changed=False)
    print(json.dumps(result,ensure_ascii=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
