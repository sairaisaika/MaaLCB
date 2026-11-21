"""Actual Maa ROI reads and one expected Drive click on memory replay only.

This verifies the production repair helper, recognition and one-node handoff,
not a live game or frozen Agent callback. No device input is sent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import subprocess
from contextlib import nullcontext
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'agent'))
sys.path.insert(0, str(ROOT/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--_temporary',type=Path)
    args=parser.parse_args()
    if args._temporary is None:
        with tempfile.TemporaryDirectory(prefix='drive-native-',dir=ROOT/'build') as temporary:
            return subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),
                '--report',str(args.report),'--_temporary',temporary]).returncode
    owned=args._temporary.resolve()
    if owned.parent!=(ROOT/'build').resolve() or not owned.name.startswith('drive-native-'):
        raise ValueError('Owned native diagnostic directory required')
    import cv2
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.custom_action import CustomAction
    from maa.pipeline import JRecognitionType,JOCR
    from maalimbus import workspace
    from maalimbus.native_evidence import configure_host,bound_frame
    from maalimbus.jobs import wait_job,wait_task
    from maalimbus.controller_lease import ControllerLease
    from maalimbus.update_install import private_hashes,closed_app
    from maalimbus.replay import ReplayController
    from maalimbus.vision import Text,find,classify,inset_box,DRIVE_MIRROR_BAND
    from maalimbus.drive_menu_native import repair
    from maalimbus.build_fingerprint import source_snapshot
    from recognition import LimbusRecognition,Journal
    app=ROOT/'dist/MaaLimbus';closed_app(app)
    source_before=source_snapshot(ROOT)
    private=private_hashes(app)
    canonical={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'config').rglob('*') if p.is_file()}
    locale=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())
    inputs=[];originals={}
    run=ROOT/'evidence/runtime/packaged-mirror-20261118-190145'
    for name in ('frame-0018','frame-0019','frame-0020','frame-0022'):
        path=run/(name+'.json');binding,record=bound_frame(path)
        inputs.append((name,record,cv2.imread(str(path.with_suffix('.png')))))
        for p in (path,path.with_suffix('.png')):originals[p]=hashlib.sha256(p.read_bytes()).hexdigest()
    event_path=ROOT/'evidence/runtime/packaged-mirror-20261119-033031/frame-0010.json'
    _,event_record=bound_frame(event_path)
    event_image=cv2.imread(str(event_path.with_suffix('.png')))
    for p in (event_path,event_path.with_suffix('.png')):originals[p]=hashlib.sha256(p.read_bytes()).hexdigest()
    cases=[]
    for name,record,image in inputs:cases.append((name,True,image,record['ocr'],'bound_retained_native_ocr'))
    cases.append(('event_layout',True,event_image,event_record['ocr'],'bound_retained_native_ocr'))
    for name,roi in [('masked_heading',(1590,175,250,110)),('masked_mirror_card',(510,335,320,215))]:
        image=inputs[1][2].copy();x,y,w,h=roi;image[y:y+h,x:x+w]=0
        cases.append((name,False,image,None,'new_native_ocr_on_synthetic_negative'))
    for name,roi in [('event_masked_heading',(1590,175,250,110)),('event_masked_mirror',(510,260,320,145))]:
        image=event_image.copy();x,y,w,h=roi;image[y:y+h,x:x+w]=0
        cases.append((name,False,image,None,'new_native_ocr_on_synthetic_negative'))
    results=[];failures=[]
    Library.open(app/'maafw',agent_server=False)
    lease=ControllerLease.acquire(ROOT/'build/controller.lock')
    try:
        with nullcontext(str(owned)) as temporary:
            configure_host(Path(temporary)/'native')
            resource=Resource()
            for layer in ('base','en'):wait_job(resource.post_bundle(ROOT/f'assets/resource/{layer}'),timeout=30)
            controller=ReplayController(inputs[0][2]);wait_job(controller.post_connection())
            tasker=Tasker();assert tasker.bind(resource=resource,controller=controller)
            class Probe(CustomAction):
                def run(self,context,argv):
                    try:
                        for name,expected,image,retained,ocr_source in cases:
                            if retained is None:
                                detail=context.run_recognition_direct(JRecognitionType.OCR,JOCR(threshold=.2),image)
                                assert detail is not None
                                records=[]
                                for row in detail.all_results:
                                    if hasattr(row,'text'):
                                        b=row.box;box=(b.x,b.y,b.w,b.h) if hasattr(b,'x') else tuple(b)
                                        records.append(Text(row.text,box,row.score))
                            else:records=[Text(r['text'],tuple(r['box']),r['score']) for r in retained]
                            coarse=classify(records,locale,(image.shape[1],image.shape[0]))
                            repaired,local=repair(context.run_recognition_direct,image,records,locale)
                            scene=classify(repaired,locale,(image.shape[1],image.shape[0]))
                            matches=find(repaired,locale['mirror_menu'],DRIVE_MIRROR_BAND,(image.shape[1],image.shape[0]))
                            target=inset_box(LimbusRecognition.card_box([m.box for m in matches])) if scene=='DRIVE' and matches else None
                            row=dict(case=name,expected_drive=expected,coarse_scene=coarse,scene=scene,ocr_source=ocr_source,
                                     input_pixels_sha256=hashlib.sha256(image.tobytes()).hexdigest(),local_ocr=local,target=target)
                            results.append(row)
                            assert (scene=='DRIVE' and target is not None)==expected,row
                            if expected:
                                x,y,w,h=target;assert .27<=(x+w/2)/image.shape[1]<=.44 and .27<=(y+h/2)/image.shape[0]<=.53
                        return True
                    except Exception as error:
                        failures.append(dict(type=type(error).__name__,reason=str(error)));return False
            callback=Probe();assert resource.register_custom_action('drive_native_probe',callback)
            assert resource.override_pipeline({'DriveNativeProbe':dict(recognition='DirectHit',action='Custom',custom_action='drive_native_probe',next=[])})
            task=wait_task(tasker,tasker.post_task('DriveNativeProbe'),deadline=time.monotonic()+180)
            assert not tasker.running and task['stop_confirmed'] and not task['timed_out']
            assert not controller.attempts
            passed=bool(task['task_succeeded'] and len(results)==len(cases) and not failures)
            # The production Runner must return after its one owned Drive click.
            # The inherited standalone graph would otherwise also click Enter
            # and confirmation, bypassing a new loop observation/intent.
            from maalimbus.runner import run_node
            entry_path=ROOT/'evidence/runtime/packaged-mirror-20261118-200244/frame-0004.json'
            bound_frame(entry_path)
            entry_image=cv2.imread(str(entry_path.with_suffix('.png')))
            for p in (entry_path,entry_path.with_suffix('.png')):originals[p]=hashlib.sha256(p.read_bytes()).hexdigest()
            width,height=inputs[0][2].shape[1],inputs[0][2].shape[0]
            handoff_controller=ReplayController([inputs[0][2],entry_image],advance=True,
                expects=lambda kind,pos,*xy:kind=='click' and pos==0
                    and .27<=xy[0]/width<=.45 and .30<=xy[1]/height<=.53)
            wait_job(handoff_controller.post_connection())
            handoff_tasker=Tasker();assert handoff_tasker.bind(resource=resource,controller=handoff_controller)
            native_observer=LimbusRecognition('en',journal=Journal(owned/'handoff'))
            assert resource.register_custom_recognition('limbus_scene',native_observer)
            handoff=run_node(handoff_tasker,'MirrorDrive',time.monotonic()+40)
            assert handoff['task_succeeded'] and handoff['stop_confirmed'],handoff
            assert len(handoff_controller.inputs)==len(handoff_controller.attempts)==1
            handoff_proof=dict(task=handoff,memory_inputs=handoff_controller.inputs,
                successor_position=handoff_controller.position,standalone_graph_traversed=False,
                scope='Actual source Runner dispatch + production recognition/Click on a memory controller; no device input')
            event_controller=ReplayController([event_image,entry_image],advance=True,
                expects=lambda kind,pos,*xy:kind=='click' and pos==0
                    and .30<=xy[0]/1920<=.42 and .27<=xy[1]/1080<=.37)
            wait_job(event_controller.post_connection())
            event_tasker=Tasker();assert event_tasker.bind(resource=resource,controller=event_controller)
            event_handoff=run_node(event_tasker,'MirrorDrive',time.monotonic()+40)
            assert event_handoff['task_succeeded'] and event_handoff['stop_confirmed'],event_handoff
            assert len(event_controller.inputs)==len(event_controller.attempts)==1
            handoff_proof['event_layout']=dict(task=event_handoff,memory_inputs=event_controller.inputs,
                successor_position=event_controller.position,standalone_graph_traversed=False,
                scope='Production source one-action dispatch on retained new-layout pixels, not a live dungeon entry')
            # Two different menus in one enclosing callback reproduce Context's
            # shared hit counts. Separate Taskers above cannot prove reentry.
            reentry_controller=ReplayController([inputs[0][2],event_image,entry_image],advance=True,
                expects=lambda kind,pos,*xy:kind=='click' and pos in (0,1)
                    and .27<=xy[0]/1920<=.45
                    and ((.32<=xy[1]/1080<=.53) if pos==0 else (.27<=xy[1]/1080<=.37)))
            wait_job(reentry_controller.post_connection())
            reentry_tasker=Tasker();assert reentry_tasker.bind(resource=resource,controller=reentry_controller)
            reentry_results=[]
            class DriveReentryProbe(CustomAction):
                def run(self,context,argv):
                    from recognition import AgentTasker
                    proxy=AgentTasker(context)
                    for _ in range(2):
                        reentry_results.append(run_node(proxy,'MirrorDrive',time.monotonic()+40))
                    return True
            assert resource.register_custom_action('drive_reentry_probe',DriveReentryProbe())
            assert resource.override_pipeline({'DriveReentryProbe':dict(recognition='DirectHit',action='Custom',
                custom_action='drive_reentry_probe',next=[],on_error=[])})
            reentry_task=wait_task(reentry_tasker,reentry_tasker.post_task('DriveReentryProbe'),deadline=time.monotonic()+100)
            reentry_ok=(reentry_task['task_succeeded'] and reentry_task['stop_confirmed']
                and len(reentry_controller.inputs)==len(reentry_controller.attempts)==2
                and len(reentry_results)==2 and all(r['task_succeeded'] for r in reentry_results))
            handoff_proof['same_context_reentry']=dict(passed=bool(reentry_ok),task=reentry_task,
                children=reentry_results,memory_inputs=reentry_controller.inputs,
                successor_position=reentry_controller.position,device_inputs=0,
                scope='Two production Runner dispatches in one native Context; counter reset is not a business receipt')
            passed=passed and reentry_ok
            notice_path=ROOT/'evidence/runtime/packaged-mirror-20261118-200244/frame-0011.json'
            bound_frame(notice_path)
            for p in (notice_path,notice_path.with_suffix('.png')):originals[p]=hashlib.sha256(p.read_bytes()).hexdigest()
            notice_controller=ReplayController(cv2.imread(str(notice_path.with_suffix('.png'))))
            wait_job(notice_controller.post_connection())
            notice_tasker=Tasker();assert notice_tasker.bind(resource=resource,controller=notice_controller)
            assert resource.override_pipeline({'ServiceNoticeReadProbe':dict(recognition='Custom',
                custom_recognition='limbus_scene',custom_recognition_param={'scene':'UNKNOWN_DIALOG'},
                action='DoNothing',next=[],on_error=[])})
            notice_task=wait_task(notice_tasker,notice_tasker.post_task('ServiceNoticeReadProbe'),deadline=time.monotonic()+30)
            assert notice_task['task_succeeded'] and notice_task['stop_confirmed'],notice_task
            assert not notice_controller.attempts
            notice_record=json.loads(sorted((owned/'handoff').glob('frame-*.json'))[-1].read_bytes())
            from maalimbus.service_notice import from_record
            notice=from_record(notice_record)
            assert notice_record['scene']=='UNKNOWN_DIALOG' and notice['complete']
            notice_proof=dict(task=notice_task,scene=notice_record['scene'],notice=notice,
                              memory_input_attempts=0,scope='Actual production callback/native OCR on retained outage pixels; no device input')
            # The real GUI's cached modal must be dismissible through the SAME
            # Runner startup owner and Maa input carrier, not a verifier click.
            gui_notice=ROOT/'dist/MaaLimbus/evidence/runtime/pi-20261119-012451/frame-0002.json'
            bound_frame(gui_notice)
            for p in (gui_notice,gui_notice.with_suffix('.png')):originals[p]=hashlib.sha256(p.read_bytes()).hexdigest()
            service_controller=ReplayController([cv2.imread(str(gui_notice.with_suffix('.png'))),entry_image],
                advance=True,expects=lambda kind,pos,*xy:kind=='click' and pos==0
                    and .47<=xy[0]/1920<=.53 and .62<=xy[1]/1080<=.68)
            wait_job(service_controller.post_connection())
            service_tasker=Tasker();assert service_tasker.bind(resource=resource,controller=service_controller)
            service_journal=Journal(args.report.resolve().with_suffix('')/'evidence')
            from recognition import MapObservation
            service_recognition=LimbusRecognition('en',journal=service_journal)
            assert resource.register_custom_recognition('limbus_scene',service_recognition)
            assert resource.register_custom_action('limbus_map_observe',MapObservation(service_recognition))
            service_results=[]
            class ServiceProbe(CustomAction):
                def run(self,context,argv):
                    try:
                        from types import SimpleNamespace
                        from maalimbus.runner import MirrorRunner,MaaDevice,MaaObserver
                        from maalimbus.storage import RunStore
                        from recognition import AgentTasker
                        config=owned/'config';config.mkdir()
                        store=RunStore(config/'user-run-ledger.json',[SimpleNamespace(slot=2)])
                        subtasks=AgentTasker(context)
                        device=MaaDevice(context.tasker.controller,tasker=subtasks,
                                         target_long_side=0,deadline=time.monotonic()+90)
                        loop=MirrorRunner(device,settings={'rounds':1,'interval':0},store=store,
                            directory=service_journal.directory,journal=service_journal,
                            observer=MaaObserver(subtasks,service_journal.directory))
                        first=loop.step()
                        assert first['input_sent'] and not first['done'],first
                        successor=loop._observe()
                        assert successor['scene']=='MIRROR_ENTRY',successor['scene']
                        assert loop._startup_handoff(successor) is None
                        state=json.loads((config/'user-service-navigation.json').read_bytes())
                        assert state['pending'] is None and state['attempts'][0]['success']
                        assert state['attempts'][0]['dispatch_confirmed']
                        assert not store.path.exists(),'Notice dismissal must not write a business ledger'
                        service_results.append(dict(after=successor['scene'],
                            attempt=state['attempts'][0],input_count=len(service_controller.inputs)))
                        return True
                    except BaseException as error:
                        failures.append(dict(type=type(error).__name__,reason=str(error)));return False
            assert resource.register_custom_action('service_navigation_probe',ServiceProbe())
            assert resource.override_pipeline({'ServiceNavigationProbe':dict(recognition='DirectHit',action='Custom',
                custom_action='service_navigation_probe',next=[],on_error=[])})
            service_task=wait_task(service_tasker,service_tasker.post_task('ServiceNavigationProbe'),deadline=time.monotonic()+120)
            assert service_task['task_succeeded'] and service_task['stop_confirmed'],(service_task,failures)
            assert len(service_controller.inputs)==len(service_controller.attempts)==1
            assert len(service_results)==1
            notice_proof['bounded_navigation']=dict(task=service_task,results=service_results,
                memory_inputs=service_controller.inputs,device_inputs=0,
                scope='Actual source Runner step/MaaObserver/MaaDevice/native OCR + task input carrier; retained images only')
            client_source=ROOT/'build/login-after-stop-readonly.png'
            assert hashlib.sha256(client_source.read_bytes()).hexdigest()=='abad6219b59d171945b5ddfef40d4a3f08f63c6705776034ec9153397fd284dc'
            originals[client_source]=hashlib.sha256(client_source.read_bytes()).hexdigest()
            client_journal=Journal(ROOT/'evidence/runtime/client-update-20261119-023500')
            client_recognition=LimbusRecognition('en',journal=client_journal)
            assert resource.register_custom_recognition('limbus_scene',client_recognition)
            client_controller=ReplayController(cv2.imread(str(client_source)))
            wait_job(client_controller.post_connection())
            client_tasker=Tasker();assert client_tasker.bind(resource=resource,controller=client_controller)
            assert resource.override_pipeline({'ClientUpdateReadProbe':dict(recognition='Custom',
                custom_recognition='limbus_scene',custom_recognition_param={'scene':'UNKNOWN_DIALOG'},
                action='DoNothing',next=[],on_error=[])})
            client_task=wait_task(client_tasker,client_tasker.post_task('ClientUpdateReadProbe'),deadline=time.monotonic()+30)
            assert client_task['task_succeeded'] and client_task['stop_confirmed'],client_task
            assert not client_controller.attempts
            client_path=sorted(client_journal.directory.glob('frame-*.json'))[-1]
            client_binding,client_record=bound_frame(client_path)
            client_notice=from_record(client_record)
            from maalimbus.service_notice import close_candidates
            assert client_record['scene']=='UNKNOWN_DIALOG' and client_notice['kind']=='client_update_required'
            assert client_notice['complete'] and not close_candidates(client_record)
            notice_proof['client_update']=dict(task=client_task,notice=client_notice,binding=client_binding,
                fixture=str(client_path.relative_to(ROOT)),source_sha256=originals[client_source],
                memory_input_attempts=0,scope='Actual native OCR on preserved post-task readonly screenshot; not a live update or login')
            passed=passed and not failures
    finally:lease.close()
    assert all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in originals.items())
    assert private_hashes(app)==private and all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in canonical.items())
    assert source_before==source_snapshot(ROOT),'Source changed during native replay'
    report=dict(passed=passed,task=task,cases=results,failures=failures,handoff=handoff_proof,
        service_notice=notice_proof,device_input_attempts=0,
        replay_controller_created=True,game_controller_created=False,private_hashes_unchanged=len(private),
        canonical_hashes_unchanged=len(canonical),original_metadata_pixels_unchanged=True,
        helper_sha256=hashlib.sha256((ROOT/'src/maalimbus/drive_menu_native.py').read_bytes()).hexdigest(),
        vision_sha256=hashlib.sha256((ROOT/'src/maalimbus/vision.py').read_bytes()).hexdigest(),
        observer_adapter_sha256=hashlib.sha256((ROOT/'agent/recognition.py').read_bytes()).hexdigest(),
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_snapshot_sha256=hashlib.sha256(json.dumps(source_before,sort_keys=True).encode()).hexdigest(),
        native_dll_sha256=hashlib.sha256((app/'maafw/MaaFramework.dll').read_bytes()).hexdigest(),
        scope='Actual Maa ROI helper plus production recognition/Click and one-node Runner handoff on bound retained pixels; not frozen callback or live game')
    body=json.dumps(report,indent=2)+'\n';workspace.require_space(ROOT,len(body.encode())+32768)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(body,encoding='utf8')
    print(json.dumps(dict(passed=passed,cases=len(results),failures=failures,device_input_attempts=0,report=str(args.report))))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
