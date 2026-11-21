"""Project Wiki protocol boundaries; no game, host trust or model calls."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess

import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import wiki_hook
from wiki_context import native_context


def selected(tmp_path,monkeypatch):
    monkeypatch.delenv('PROJECT_WIKI_PACKET',raising=False)
    root=tmp_path/'project';root.mkdir()
    packet=root/'build/wiki/task/packet.json';packet.parent.mkdir(parents=True)
    packet.write_text('{"saved":"data"}')
    home=tmp_path/'host'
    package=home/'plugins/cache/project-wiki-internal/project-wiki/0.2.17'
    manifest=package/'.codex-plugin/plugin.json';manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"project-wiki","version":"0.2.17"}')
    adapter=package/'skills/project-wiki/scripts/lifecycle.py';adapter.parent.mkdir(parents=True)
    # Transport double: real installed-provider compatibility is checked separately.
    adapter.write_text('def deliver(event, selected):\n return {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"saved:"+selected}}\n')
    adapter.with_name('workflow.py').write_text('# Saved reader transport double\n')
    value=dict(version=1,root=str(root),packet=str(packet),packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),
               provider_version='0.2.17',provider_sha256=hashlib.sha256(adapter.read_bytes()).hexdigest(),
               workflow_sha256=hashlib.sha256(adapter.with_name('workflow.py').read_bytes()).hexdigest())
    selection=root/wiki_hook.SELECTION;selection.parent.mkdir();selection.write_text(json.dumps(value))
    event=dict(hook_event_name='SessionStart',source='resume',cwd=str(root))
    return root,home,packet,adapter,selection,event


def test_explicit_selection_delegates_to_installed_provider_without_running_commands(tmp_path,monkeypatch):
    root,home,packet,adapter,path,event=selected(tmp_path,monkeypatch)
    result=wiki_hook.deliver(event,root=root,codex_home=home)
    assert result['hookSpecificOutput']['additionalContext']=='saved:'+str(packet)
    assert not list(root.rglob('__pycache__'))
    assert json.loads(path.read_text())['packet_sha256']==hashlib.sha256(packet.read_bytes()).hexdigest()


@pytest.mark.parametrize('fault',['packet','provider','workflow','root','foreign_cwd','outside_packet','nested_checkout','version'])
def test_bad_identity_or_changed_evidence_cannot_execute_provider(tmp_path,monkeypatch,fault):
    root,home,packet,adapter,path,event=selected(tmp_path,monkeypatch)
    value=json.loads(path.read_text())
    if fault=='packet':packet.write_text('changed')
    elif fault=='provider':adapter.write_text('raise AssertionError("must not load")')
    elif fault=='workflow':adapter.with_name('workflow.py').write_text('changed')
    elif fault=='root':value['root']=str(tmp_path/'another')
    elif fault=='foreign_cwd':event['cwd']=str(tmp_path)
    elif fault=='outside_packet':value['packet']=str(tmp_path/'outside.json')
    elif fault=='nested_checkout':
        nested=root/'nested';(nested/'.git').mkdir(parents=True);event['cwd']=str(nested)
    else:value['provider_version']='../other'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):wiki_hook.deliver(event,root=root,codex_home=home)


def test_no_selection_is_a_quiet_opt_out(tmp_path):
    assert wiki_hook.deliver(dict(hook_event_name='SessionStart',cwd=str(tmp_path)),root=tmp_path) is None


def test_same_ambient_selection_is_not_delivered_twice(tmp_path,monkeypatch):
    root,home,packet,adapter,path,event=selected(tmp_path,monkeypatch)
    monkeypatch.setenv('PROJECT_WIKI_PACKET',str(packet))
    assert wiki_hook.deliver(event,root=root,codex_home=home) is None
    monkeypatch.setenv('PROJECT_WIKI_PACKET',str(tmp_path/'foreign.json'))
    assert 'conflicts' in wiki_hook.deliver(event,root=root,codex_home=home)['systemMessage']


def test_full_owner_inventory_is_independent_of_query_top_two(tmp_path):
    path=tmp_path/'docs/wiki/routes.json';path.parent.mkdir(parents=True)
    routes=[dict(id=str(i),title='own '+str(i),aliases=['test'],sources=[dict(path='shared.py',symbol='foo')],
                 docs=['docs/wiki/en_us/8-agent-rules.md#section-'+str(i)],tests=[])
            for i in range(4)]
    path.write_text(json.dumps(dict(routes=routes)))
    result=native_context(tmp_path,'test',['shared.py','unknown.py'])
    assert len(result['cards'])==1 and len(result['impact'][0]['pages'])==4
    assert len(result['cards'][0]['sections'])==2
    assert {r['anchor'] for r in result['cards'][0]['sections']}=={'section-0','section-1'}
    assert result['impact'][1]['unregistered'] is True and result['impact'][1]['pages']==[]


@pytest.mark.parametrize('name',['../outside.py','C:/outside.py','bad\\path.py',''])
def test_router_declines_foreign_or_noncanonical_planned_files(tmp_path,name):
    path=tmp_path/'docs/wiki/routes.json';path.parent.mkdir(parents=True)
    path.write_text('{"routes":[]}')
    with pytest.raises(ValueError):native_context(tmp_path,'test',[name])


@pytest.mark.parametrize('rendered',[{'index_delivered':False,'reason':'Index exceeds hook budget'},[]])
def test_omitted_index_never_replaces_the_previous_selection(tmp_path,monkeypatch,rendered):
    import wiki_session
    root,home,packet,adapter,path,event=selected(tmp_path,monkeypatch)
    before=path.read_bytes()
    adapter.write_text('def deliver(event, selected):\n return '+repr({
        'hookSpecificOutput':{'additionalContext':'Saved-only context\n'+json.dumps(rendered)}})+'\n')
    adapter.with_name('workflow.py').write_text(
        'def capture(*args, **kwargs): return {"captured":True}\n'
        'def start(*args, **kwargs): return {"saved":True}\n')
    monkeypatch.setattr(wiki_session,'provider',lambda version:adapter)
    with pytest.raises(ValueError,match='omitted'):
        wiki_session.prepare(root,version='0.2.17',query='wiki',files=['tools/wiki_hook.py'],
            task_id='large-index',outcome='deliver index',acceptance=['real index'],capabilities=['read'])
    assert path.read_bytes()==before


def test_project_router_works_without_any_skill_directory(tmp_path):
    import shutil
    destination=tmp_path/'tools';destination.mkdir()
    for name in ('wiki_route.py','wiki_router.py'):
        shutil.copyfile(TOOLS/name,destination/name)
    manifest=tmp_path/'docs/wiki/routes.json';manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":1,"project":"fixture","routes":[]}')
    run=subprocess.run([sys.executable,str(destination/'wiki_route.py'),'--root',str(tmp_path),'--list'],
                       capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert not (tmp_path/'skills').exists()


def test_feature_expansion_has_verified_edit_locations_and_evidence_limits(tmp_path):
    wiki=tmp_path/'docs/wiki';wiki.mkdir(parents=True)
    (wiki/'runtime.md').write_text('# Runtime\n')
    source=tmp_path/'runner.py';source.write_text('def launch():\n    pass\n')
    route=dict(id='launch',title='Launch',aliases=[],sources=[dict(path='runner.py',symbol='launch')],
               docs=['docs/wiki/runtime.md'],tests=[],checks=['read-only check'],boundary='Not live proof')
    (wiki/'routes.json').write_text(json.dumps(dict(schema_version=1,project='fixture',routes=[route])))
    section=native_context(tmp_path,'launch',['runner.py'])['cards'][0]['sections'][0]
    assert section['locations'][0]['line']==1 and section['boundary']=='Not live proof'
    source.write_text('def renamed():\n    pass\n')
    stale=native_context(tmp_path,'launch',['runner.py'])['cards'][0]['sections'][0]
    assert stale['locations']==[] and 'warning' in stale
    assert stale['boundary']=='Not live proof'
