"""Exercise actual Agent reverse sizing and observer fallback on saved frames.

One input-forbidden ReplayController; no MainTask or game ledger. The ordinary
MirrorLoop is additionally exercised in its explicit observe-only mode.
Each worker and its owned Agent must exit before temporary evidence is removed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tools'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packaged',action='store_true')
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--_temporary',type=Path)
    args=p.parse_args()
    if args._temporary is None:
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='capture-profiles-') as temporary:
            command=[sys.executable,str(Path(__file__).resolve()),'--report',str(args.report),
                     '--_temporary',temporary]
            if args.packaged:command.append('--packaged')
            return subprocess.run(command).returncode
    import cv2
    from maa.library import Library
    from maa.tasker import Tasker
    from maalimbus import workspace
    from maalimbus.native_evidence import configure_host,bound_frame
    from maalimbus.jobs import wait_job,wait_task
    from maalimbus.replay import ReplayController
    from maalimbus.build_fingerprint import source_snapshot
    from verify_packaged_agent_ipc import verify
    directory=args._temporary;source=source_snapshot(ROOT)
    verifier_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    helper_sha=hashlib.sha256((ROOT/'tools/verify_packaged_agent_ipc.py').read_bytes()).hexdigest()
    installed=None
    if args.packaged:
        info=json.loads((ROOT/'dist/MaaLimbus/build-info.json').read_text())
        if info['source_snapshot']!=source or info['source_dirty'] is not False:
            raise ValueError('Frozen observer differs from reviewed source')
        installed=dict(source_commit=info['source_commit'],source_snapshot_matches=True,
            build_info_sha256=hashlib.sha256((ROOT/'dist/MaaLimbus/build-info.json').read_bytes()).hexdigest(),
            executable_sha256=hashlib.sha256((ROOT/'dist/MaaLimbus/agent/MaaLimbusAgent.exe').read_bytes()).hexdigest())
    inputs={}
    for key,name in [('hud','packaged-mirror-20261031-205402/frame-0011'),
                     ('shop','packaged-mirror-20261117-010749/frame-0055')]:
        path=ROOT/'evidence/runtime'/(name+'.json')
        binding,record=bound_frame(path)
        inputs[key]=dict(path=str(path),binding=binding,pixels=cv2.imread(str(path.with_suffix('.png'))))
    Library.open(ROOT/'dist/MaaLimbus/maafw',agent_server=False)
    configure_host(directory/'native')
    journal=directory/'journal';result={}
    def events():
        if not (journal/'events.jsonl').is_file():return []
        rows=[]
        for line in (journal/'events.jsonl').read_text(encoding='utf8').splitlines():
            try:rows.append(json.loads(line))
            except ValueError:pass  # Only a currently unfinished append in this diagnostic.
        return rows
    class Sequence(ReplayController):
        def __init__(self):super().__init__();self.reads=0;self.override=None
        def screencap(self):
            self.reads+=1
            if self.override is not None:return self.override.copy()
            complete=sum(r.get('event')=='capture_profile_probe_read' for r in events())
            return inputs['hud' if complete<2 else 'shop']['pixels'].copy()
    controller=Sequence()
    def probe(client,resource,process):
        assert 'limbus_capture_profile_probe' in client.custom_action_list
        for layer in ('base','en'):
            wait_job(resource.post_bundle(ROOT/f'dist/MaaLimbus/assets/resource/{layer}'),timeout=30)
        wait_job(controller.post_connection())
        tasker=Tasker();assert tasker.bind(resource,controller)
        assert resource.override_pipeline({'CaptureProfiles':dict(
            recognition='DirectHit',action='Custom',custom_action='limbus_capture_profile_probe',
            custom_action_param=dict(reads=3,budget=90),next=[])})
        try:wait_job(tasker.post_task('CaptureProfiles'),timeout=100)
        finally:
            result['events']=events()
            result['input_attempts']=controller.attempts
        rows=[r for r in events() if r.get('event')=='capture_profile_probe_read']
        assert [r['size'] for r in rows]==[[1920,1080],[1280,720],[1920,1080]],rows
        assert [r['scene'] for r in rows]==['BATTLE_HUD','BATTLE_HUD','SHOP']
        bindings=[]
        for row in rows:
            binding,record=bound_frame(Path(row['result_record']))
            assert record['scene']==row['scene'] and record['size']==row['size']
            reference=row['frame_ref']
            assert reference['record_path']==str(Path(row['result_record']).resolve())
            assert reference['frame_id']==Path(row['result_record']).stem
            assert reference['json_sha256']==binding['json_sha256']
            assert reference['png_sha256']==binding['png_sha256']
            assert reference['captured_at']==record.get('utc')
            assert reference['size']==record['size']
            bindings.append(dict(identity=binding,record_json=Path(row['result_record']).read_text()))
        from maalimbus.capture_geometry import frame_coordinates
        for row in rows[:2]:
            measured=[e for e in events() if e.get('event')=='battle_observed'
                      and e.get('frame')==Path(row['result_record']).stem][-1]
            expected=frame_coordinates((1325,746,123,151),row['size'])
            assert measured.get('start_box') and max(abs(a-b) for a,b in zip(measured['start_box'],expected))<=3
        fallback=[e for e in events() if e.get('event')=='capture_profile_full_reread']
        assert len(fallback)==1
        _,small_shop=bound_frame(Path(fallback[0]['before_record']))
        assert small_shop['scene']=='SHOP' and small_shop['size']==[1280,720]
        requests=[r for r in events() if r.get('event')=='capture_profile_requested']
        assert [r['requested_long_side'] for r in requests]==[1920,1280,1920]
        assert all(r['accepted'] for r in requests)
        assert not controller.attempts
        result['bindings']=bindings
        # Also enter the ordinary production actor. Observe-only is deliberately
        # one bounded step; it must expose the actual installed/read policy and
        # send no input, without running MainTask foreground/preparation.
        assert resource.override_pipeline({'MirrorLoop':dict(custom_action_param=dict(
            observe_only=True,steps=1,run_count=0,budget=45,run_store='',directory=str(journal)))})
        import time
        try:
            ordinary_task=wait_task(tasker,tasker.post_task('MirrorLoop'),
                                    deadline=time.monotonic()+60)
            result['ordinary_task']=ordinary_task
        finally:
            result['events']=events()
            if (journal/'agent-result.json').is_file():
                result['ordinary_mirror_loop']=json.loads((journal/'agent-result.json').read_text())
        ordinary=result['ordinary_mirror_loop']
        # The production actor deliberately returns False for observe_only:
        # it is a normal bounded read, never a completed dungeon. Accept only
        # that named result and an independently confirmed native task end.
        assert ordinary_task['stop_confirmed'] and not ordinary_task['timed_out']
        assert ordinary_task['verdict']=='stopped' and not ordinary_task['task_succeeded']
        assert ordinary.get('reason')=='observe_only' and ordinary.get('passed') is False
        assert ordinary.get('observe_only') is True and ordinary.get('clicks_sent')==0
        assert ordinary['capture_policy']['full_successor_size']==[1920,1080]
        assert not controller.attempts
        result['ordinary_mirror_loop']=ordinary
        title_path=ROOT/'evidence/runtime/window-20261117-043656/frame-0006.json'
        title_binding,title_record=bound_frame(title_path)
        title_image=cv2.imread(str(title_path.with_suffix('.png')))
        title_cases=[]
        for erased in (False,True):
            controller.override=title_image.copy()
            if erased:
                h,w=controller.override.shape[:2]
                controller.override[int(h*.72):int(h*.84),int(w*.36):int(w*.62)]=0
            task=wait_task(tasker,tasker.post_task('MirrorLoop'),deadline=time.monotonic()+60)
            ordinary=json.loads((journal/'agent-result.json').read_text())
            actual=[r for r in events() if r.get('event')=='map_observed'][-1]
            assert task['stop_confirmed'] and not task['timed_out']
            assert ordinary['reason']=='observe_only' and ordinary['clicks_sent']==0
            assert (actual['scene']=='TITLE') is (not erased),actual
            observed_binding,_=bound_frame(journal/(Path(actual['frame']).stem+'.json'))
            title_cases.append(dict(caption_erased=erased,scene=actual['scene'],
                                    observed=observed_binding,source=title_binding))
            assert not controller.attempts
        result['title_cases']=title_cases
        result['events']=events()
        return dict(passed=True,input_attempts=0,observations=len(rows))
    session=verify('tcp',source_agent=not args.packaged,directory=journal,
                   data_directory=directory/'config',probe=probe,timeout_ms=30000,
                   agent_args=('--capture-profile-probe',))
    assert source==source_snapshot(ROOT),'Source changed during native probe'
    assert verifier_sha==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert helper_sha==hashlib.sha256((ROOT/'tools/verify_packaged_agent_ipc.py').read_bytes()).hexdigest()
    value=dict(passed=session['passed'],source_snapshot=source,actual_frozen=args.packaged,
               installed=installed,
               session=session,probe=result,physical_controller=False,game_inputs=0,
               raw_inputs={k:{a:b for a,b in v.items() if a!='pixels'} for k,v in inputs.items()},
               verifier_sha256=verifier_sha,
               session_helper_sha256=helper_sha,
               native_library_sha256=hashlib.sha256((ROOT/'dist/MaaLimbus/maafw/MaaFramework.dll').read_bytes()).hexdigest(),
               scope='native controller/proxy/observer integration, not GUI, gameplay or learned quality')
    data=json.dumps(value,indent=2).encode();workspace.reserve_output(args.report,len(data),application_root=ROOT)
    args.report.write_bytes(data)
    print(json.dumps({k:value[k] for k in ('passed','actual_frozen','physical_controller','game_inputs')}))
    return 0 if value['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
