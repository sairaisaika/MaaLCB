"""Replay the real Agent observer on hash-bound frames at a requested size.

Only an offline ReplayController is used; its input methods raise. Generated
images/logs live in one bounded temporary directory and are removed on return.
The report retains original hashes, resize profile and actual native results.
"""
import argparse,hashlib,json,sys,tempfile,subprocess,shutil
from contextlib import nullcontext
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'agent'))


def frozen_observe(pixels,expected,directory,transport):
    """Only the installed limbus_scene callback; no actions or real state."""
    import cv2,numpy as np
    from maa.tasker import Tasker
    from maa.pipeline import JRecognitionType,JCustomRecognition
    from maalimbus.jobs import wait_job
    from maalimbus.native_evidence import bound_frame
    from maalimbus.replay import blank_replay
    from verify_packaged_agent_ipc import verify
    journal=directory/'journal';captured={}
    def probe(client,resource,process):
        if 'limbus_scene' not in client.custom_recognition_list:
            raise ValueError('Frozen scene callback is not registered')
        for layer in ('base','en'):
            wait_job(resource.post_bundle(ROOT/f'dist/MaaLimbus/assets/resource/{layer}'),timeout=30)
        controller=blank_replay();wait_job(controller.post_connection())
        tasker=Tasker();assert tasker.bind(resource,controller)
        job=tasker.post_recognition(JRecognitionType.Custom,
            JCustomRecognition(custom_recognition='limbus_scene',
                               custom_recognition_param={'scene':expected}),pixels)
        wait_job(job,timeout=30)
        events=[json.loads(line) for line in (journal/'events.jsonl').read_text(encoding='utf8').splitlines()]
        failed=[e for e in events if e['event']=='callback_failed']
        recognized=[e for e in events if e['event']=='recognized']
        if failed or len(recognized)!=1:
            raise ValueError('Frozen observation was not independently recorded: '+str(failed[-1:] or events[-1:]))
        path=journal/(recognized[0]['frame']+'.json');binding,record=bound_frame(path)
        if not np.array_equal(cv2.imread(str(path.with_suffix('.png'))),pixels):
            raise ValueError('Frozen callback received different capture pixels')
        proposals=[e for e in events if e['event']=='semantic_frame_proposal']
        samples=[]
        for sample in (directory/'build/learning-review/frames').glob('*/proposal.json'):
            value=json.loads(sample.read_text(encoding='utf8'))
            samples.append({k:value.get(k) for k in ('scene_proposal','reviewed','training_eligible','input_authorized','boxes')})
        captured.update(record=record,journal_binding=binding,
            native_record_json=path.read_text(encoding='utf8'),semantic_proposals=proposals,samples=samples)
        assert not controller.attempts,'Frozen read-only callback attempted controller input'
        return dict(passed=record['scene']==expected,input_attempts=0,
                    semantic_proposals=len(proposals),isolated_pending_samples=len(samples))
    session=verify(transport,directory=journal,data_directory=directory/'config',probe=probe,timeout_ms=30000)
    if session.get('passed') is not True:
        raise RuntimeError('Frozen Agent probe failed: '+json.dumps(session,ensure_ascii=False))
    captured['session']=session
    return captured


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--side',type=int,choices=(1280,1920),default=1280)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--packaged',action='store_true',help='Execute the installed frozen observer over Maa IPC')
    p.add_argument('--transport',choices=('auto','ipc','tcp'),default='auto')
    p.add_argument('--_temporary',type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args._temporary is None:
        # Windows keeps Maa's log file open until the worker process exits.
        # The parent owns temporary cleanup only after native handles close.
        with tempfile.TemporaryDirectory(prefix='ipc-observe-' if args.packaged else 'maalimbus-native-scale-',
                dir=ROOT/'build' if args.packaged else None) as directory:
            command=[sys.executable,str(Path(__file__).resolve()),
                '--manifest',str(args.manifest),'--side',str(args.side),
                '--report',str(args.report),'--_temporary',directory]
            if args.packaged:command+=['--packaged','--transport',args.transport]
            child=subprocess.run(command)
        return child.returncode
    import cv2
    import numpy as np
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maalimbus.jobs import wait_job
    from maalimbus.replay import blank_replay
    from maalimbus.native_evidence import bound_frame,configure_host
    from maalimbus.build_fingerprint import source_snapshot
    from maalimbus.map_vision import map_header
    from maalimbus.runner import candidates_of,controls_by_id,REGISTRY
    from maalimbus.vision import Text
    if not args.packaged:
        from recognition import Journal,LimbusRecognition
    implementation=source_snapshot(ROOT)
    verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    native_library=ROOT/'dist/MaaLimbus/maafw/MaaFramework.dll'
    native_library_sha256=hashlib.sha256(native_library.read_bytes()).hexdigest()
    private={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'config').glob('*.json')}
    installed=None
    if args.packaged:
        app=ROOT/'dist/MaaLimbus';info=json.loads((app/'build-info.json').read_text(encoding='utf8'))
        if info.get('source_dirty') is not False or info.get('source_snapshot')!=implementation:
            raise ValueError('Installed observer source differs from reviewed current implementation')
        selected_transport=args.transport
        if args.transport=='auto':
            config=json.loads((app/'config/mxu-MaaLimbus.json').read_text(encoding='utf8'))
            args.transport='tcp' if config.get('settings',{}).get('tcpCompatMode') is True else 'ipc'
        installed=dict(source_commit=info['source_commit'],source_snapshot_matches=True,
            executable_sha256=hashlib.sha256((app/'agent/MaaLimbusAgent.exe').read_bytes()).hexdigest(),
            build_info_sha256=hashlib.sha256((app/'build-info.json').read_bytes()).hexdigest(),
            transport=args.transport,transport_selection=selected_transport,
            session_verifier_sha256=hashlib.sha256((ROOT/'tools/verify_packaged_agent_ipc.py').read_bytes()).hexdigest())
    Library.open(ROOT/'dist/MaaLimbus/maafw',agent_server=False)
    cases=json.loads(args.manifest.read_text(encoding='utf8'));results=[]
    with nullcontext(args._temporary) as temporary:
        tmp=Path(temporary);configure_host(tmp/'native')
        def close_case(index):
            if not args.packaged:return
            target=(tmp/str(index)).resolve()
            if target==tmp.resolve() or not target.is_relative_to(tmp.resolve()):
                raise ValueError('Replay cleanup left its owned temporary directory')
            if target.exists():shutil.rmtree(target)
        resource=Resource()
        for layer in ('base','en'):wait_job(resource.post_bundle(ROOT/f'assets/resource/{layer}'))
        controller=blank_replay();wait_job(controller.post_connection())
        tasker=Tasker();assert tasker.bind(resource,controller)
        class Context:
            def run_recognition_direct(self,kind,params,image):
                job=tasker.post_recognition(kind,params,image);wait_job(job,timeout=30)
                value=job.get()
                return value.nodes[-1].recognition if value and value.nodes else None
        for i,case in enumerate(cases):
            source=Path(case['path']);binding,original=bound_frame(source)
            from maalimbus.native_image_archive import read_png
            pixels=cv2.imdecode(np.frombuffer(read_png(source.with_suffix('.png')),dtype=np.uint8),cv2.IMREAD_COLOR)
            if pixels is None:raise ValueError('Original captured PNG is not decodable')
            factor=args.side/pixels.shape[1]
            pixels=cv2.resize(pixels,(args.side,round(pixels.shape[0]*factor)),interpolation=cv2.INTER_AREA)
            from maalimbus.native_gestures import frame_coordinates
            for calibration_box in case.get('erase',[]):
                x,y,w,h=frame_coordinates(calibration_box,(pixels.shape[1],pixels.shape[0]))
                pixels[y:y+h,x:x+w]=0
            output=tmp/str(i);frozen=None
            try:
                if args.packaged:
                    frozen=frozen_observe(pixels,case['scene'],output,args.transport)
                    record=frozen['record'];frame=record['frame'];scene=record['scene']
                    records=[Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']]
                    output=output/'journal'
                    controls=controls_by_id(json.loads(REGISTRY.read_text(encoding='utf8')),record['size'])
                    locale=json.loads((ROOT/'dist/MaaLimbus/assets/resource/en/locale.json').read_text(encoding='utf8'))
                    callback_failure=None
                else:
                    reader=LimbusRecognition('en',Journal(output))
                    records,scene,frame=reader.observe(Context(),pixels)
                    record=json.loads((output/(frame+'.json')).read_text(encoding='utf8'))
                    controls,locale,callback_failure=reader.controls,reader.locale,reader.callback_failure
            except Exception as error:
                row=dict(source=str(source),original=binding,expected=case['scene'],passed=False,
                         error=type(error).__name__+': '+str(error))
                results.append(row)
                print(json.dumps(dict(case=i,expected=case['scene'],passed=False,error=row['error'])),flush=True)
                close_case(i)
                continue
            row=dict(source=str(source),original=binding,expected=case['scene'],scene=scene,
                size=record['size'],resize='opencv_INTER_AREA',pixels_sha256=hashlib.sha256(pixels.tobytes()).hexdigest(),
                callback_failure=callback_failure,passed=scene==case['scene'],ocr=record.get('ocr'),
                local_ocr=record.get('local_ocr'))
            row['erased_calibration_boxes']=case.get('erase',[])
            row['neural_sinners']=record.get('neural_sinners')
            if frozen:
                row['frozen_observer']={k:v for k,v in frozen.items() if k!='record'}
            if case.get('require_neural'):
                neural=record.get('neural_sinners') or {}
                row['neural_participation_gate']=dict(required=True,
                    native_inference_executed=neural.get('native_inference_executed'),
                    verified_roi_count=len(neural.get('verified_rois') or []),box_count=len(neural.get('boxes') or []))
                row['passed']=bool(row['passed'] and neural.get('native_inference_executed') is True
                    and neural.get('boxes') and neural.get('model_trained') is True
                    and neural.get('training_eligible') is False and neural.get('production_enabled') is False
                    and neural.get('input_authorized') is False)
            if case['scene']=='MAP':
                header=map_header(records,record['size']);_,boxes=candidates_of(output,record,mode='box')
                row.update(floor=header.floor if header else None,pack=header.pack if header else None,
                    first_candidate=boxes[0] if boxes else None,connected=record.get('map_connected_step'),
                    local_ocr=record.get('local_ocr'))
                row['passed']=bool(row['passed'] and header and header.floor==case.get('floor') and header.pack==case.get('pack')
                    and (not case.get('connected') or record.get('map_connected_step')))
            if case['scene']=='PRE_BATTLE_TEAM':
                from maalimbus.runner import team_state
                from maalimbus.team_vision import carries_saved_order
                state=team_state(record,controls)
                row['deployment']=state
                order=[3,4,9,1,7,2,12,5,8,10,11,6]
                row['inherited_order']=carries_saved_order(state['numbers'],order,state['participants'])
                row['passed']=bool(row['passed'] and row['inherited_order'])
            if case['scene']=='BATTLE_HUD' and ('start_box' in case or case.get('reject_start')):
                from maalimbus.battle_vision import start_button
                found=start_button(records,record['size'],pixels)
                row['start_box']=found
                expected=frame_coordinates(case['start_box'],record['size']) if case.get('start_box') else None
                row['passed']=bool(row['passed'] and ((found is None) if case.get('reject_start')
                    else (found and max(abs(a-b) for a,b in zip(found,expected))<=3)))
            if case['scene']=='THEME_PACKS':
                from maalimbus.theme_vision import ThemeCatalog,theme_page,pack_candidates
                catalog=ThemeCatalog(ROOT/'assets/resource/base')
                mode=theme_page(pixels,catalog,records,locale)
                packs=pack_candidates(pixels,records,catalog)
                row.update(mode=mode,packs=[dict(name=p.name,box=p.box) for p in packs])
                row['passed']=bool(row['passed'] and mode=='hard' and any(p.name for p in packs))
            if case['scene']=='SHOP_PURCHASE':
                from maalimbus.shop_vision import matching_purchase_question,purchase_balances
                row['balances']=purchase_balances(records,record['size'])
                row['purchase_target']=matching_purchase_question(records,
                    case['name'],case['price'],record['size'],coins=case['coins'])
                row['passed']=bool(row['passed'] and row['purchase_target'])
            if case['scene'] in ('STAR_GRACES','STAR_CONFIRM'):
                from maalimbus.grace_vision import available_starlight,observed_board,conversion_state
                row['available']=available_starlight(records,record['size'])
                row['passed']=bool(row['passed'] and row['available']==case['available'])
                if case['scene']=='STAR_GRACES':
                    board=observed_board(pixels,records,case['wanted'])
                    row['board']=board
                    row['passed']=bool(row['passed'] and ((board is None) if case.get('reject_board')
                        else (board and board['costs']==case['costs'])))
                else:
                    state=conversion_state(pixels,records,ROOT/'assets/resource/base/image/navigation')
                    row['conversion']=state
                    row['passed']=bool(row['passed'] and state.get('conversion')==case['conversion']
                        and state.get('cost')==case['conversion_cost'])
            results.append(row)
            print(json.dumps(dict(case=i,scene=scene,expected=case['scene'],passed=row['passed'])),flush=True)
            close_case(i)
        assert not controller.inputs
        # Exercise Maa's actual MultiSwipe geometry against a declared offline
        # touch sink; this is separate from the input-forbidden OCR controller.
        import numpy as np
        from maalimbus.replay import ReplayController
        from maalimbus.native_gestures import map_pinch,pinch_node
        from maa.define import MaaControllerFeatureEnum
        gesture=ReplayController(np.zeros((round(args.side*9/16),args.side,3),np.uint8),
            expects=lambda *args:True,features=int(MaaControllerFeatureEnum.UseMouseDownAndUpInsteadOfClick))
        gesture.set_screenshot_target_long_side(args.side)
        wait_job(gesture.post_connection());wait_job(gesture.post_screencap())
        gesture_tasker=Tasker();assert gesture_tasker.bind(resource,gesture)
        centre,radius=map_pinch((args.side,round(args.side*9/16)))
        node=pinch_node(centre,radius,.55,.9)
        resource.override_pipeline({'CaptureScalePinch':node})
        job=gesture_tasker.post_task('CaptureScalePinch');wait_job(job,timeout=15)
        assert gesture.inputs and all(0<=row[2]<args.side and 0<=row[3]<round(args.side*9/16)
            for row in gesture.inputs if row[0] in ('touch_down','touch_move'))
        simulated_gesture=dict(passed=True,node=node,inputs=gesture.inputs,physical_controller=False)
    assert all(hashlib.sha256(f.read_bytes()).hexdigest()==h for f,h in private.items())
    assert implementation==source_snapshot(ROOT),'Source changed during native replay'
    assert verifier_sha256==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if installed:
        assert installed['session_verifier_sha256']==hashlib.sha256((ROOT/'tools/verify_packaged_agent_ipc.py').read_bytes()).hexdigest()
    result=dict(passed=all(r['passed'] for r in results),side=args.side,rows=results,
        actual_native_observer=True,physical_controller=False,game_inputs=0,private_files_unchanged=len(private),
        simulated_gesture=simulated_gesture,
        source_snapshot=implementation,verifier_sha256=verifier_sha256,
        native_library_sha256=native_library_sha256,
        actual_frozen_observer=args.packaged,installed=installed,
        main_task_dispatch_verified=False,gui_start_verified=False,production_training_samples_added=0,
        scope='retained resize/observer replay; not live full-run or independent model quality')
    from maalimbus.workspace import reserve_output
    payload=json.dumps(result,indent=2,ensure_ascii=False)
    reserve_output(args.report,len(payload.encode('utf8')),application_root=ROOT)
    args.report.write_text(payload,encoding='utf8')
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
