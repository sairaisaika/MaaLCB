"""Production native counter fallback -> Journal -> FrameRef -> consumer, no device.

The primary counter is withheld in one diagnostic case. All fallback reads use
actual Maa OCR on the retained crash pixels. Optional learning writes are
quarantined, so diagnostic frames cannot enter the account's review/training pool.
"""
import argparse,hashlib,json,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'agent'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--_temporary',type=Path)
    args=parser.parse_args()
    if args.report.exists():raise FileExistsError('Use a distinct native verification report')
    if args._temporary is None:
        with tempfile.TemporaryDirectory(prefix='deployment-native-',dir=ROOT/'build') as temporary:
            return subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),
                '--report',str(args.report),'--_temporary',temporary]).returncode
    owned=args._temporary.resolve()
    if owned.parent!=(ROOT/'build').resolve() or not owned.name.startswith('deployment-native-'):
        raise ValueError('Owned native diagnostic directory required')
    import cv2
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.pipeline import JRecognitionType
    from maa.custom_action import CustomAction
    from maalimbus import workspace,runner
    from maalimbus.native_evidence import configure_host,bound_frame,observation_frame
    from maalimbus.jobs import wait_job,wait_task
    from maalimbus.controller_lease import ControllerLease
    from maalimbus.update_install import private_hashes,closed_app
    from maalimbus.build_fingerprint import source_snapshot
    from maalimbus.replay import ReplayController
    from recognition import LimbusRecognition,Journal
    app=ROOT/'dist/MaaLimbus';closed_app(app)
    snapshot=source_snapshot(ROOT);private=private_hashes(app)
    canonical={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'config').rglob('*') if p.is_file()}
    source=ROOT/'evidence/runtime/packaged-mirror-20261119-051846/frame-0026.json'
    binding,original=bound_frame(source)
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,source.with_suffix('.png'))}
    image=cv2.imread(str(source.with_suffix('.png')));results=[]
    Library.open(app/'maafw',agent_server=False);lease=ControllerLease.acquire(ROOT/'build/controller.lock')
    try:
        configure_host(owned/'native')
        resource=Resource()
        for layer in ('base','en'):wait_job(resource.post_bundle(ROOT/f'assets/resource/{layer}'),timeout=30)
        for forced in (False,True):
            controller=ReplayController(image);wait_job(controller.post_connection())
            tasker=Tasker();assert tasker.bind(resource=resource,controller=controller)
            hidden=[]
            class PrimaryGap:
                def __init__(self,context):self.context=context
                def __getattr__(self,name):return getattr(self.context,name)
                def run_recognition_direct(self,kind=None,param=None,image=None):
                    roi=getattr(param,'roi',None)
                    if (forced and kind==JRecognitionType.OCR and roi is not None
                            and list(roi)==[1610,745,250,80] and image.shape[:2]==(1080,1920)):
                        hidden.append(list(roi))
                        return SimpleNamespace(hit=False,all_results=[],filtered_results=[])
                    return self.context.run_recognition_direct(kind,param,image)
            journal=Journal(args.report.resolve().with_suffix('')/('forced' if forced else 'natural'))
            recognition=LimbusRecognition('en',journal=journal)
            class CounterProbe(CustomAction):
                def run(self,context,argv):
                    # Pass the bound1920image explicitly. Custom-recognition argv
                    # otherwise defaults to1280 reference pixels on this replay
                    # controller, which does not reproduce the original crop.
                    recognition.observe(PrimaryGap(context),image)
                    return True
            assert resource.register_custom_action('deployment_counter_read_probe',CounterProbe())
            assert resource.override_pipeline({'DeploymentCounterReadProbe':dict(recognition='DirectHit',
                action='Custom',custom_action='deployment_counter_read_probe',next=[],on_error=[])})
            with patch('maalimbus.semantic_labels.persist_frame_proposals',return_value={'status':'diagnostic_quarantined'}):
                task=wait_task(tasker,tasker.post_task('DeploymentCounterReadProbe'),deadline=time.monotonic()+180)
            assert task['task_succeeded'] and task['stop_confirmed'] and not task['timed_out'],task
            assert not controller.attempts and recognition.callback_failure is None
            path=sorted(journal.directory.glob('frame-*.json'))[-1]
            raw=json.loads(path.read_bytes());assert all(isinstance(row,dict) for row in raw['local_ocr'])
            assert raw['scene']=='PRE_BATTLE_TEAM' and raw['size']==[1920,1080]
            primary=[r for r in raw['local_ocr'] if r.get('purpose')=='deployment_participants']
            assert len(primary)==1 and primary[0]['only_rec'] is False
            fallback=[r for r in raw['local_ocr'] if r.get('purpose')=='deployment_participants_fallback']
            if forced:
                assert hidden and len(fallback)==1 and fallback[0]['scale']==4 and fallback[0]['results']
            observed,reference,_=observation_frame(journal.directory,dict(frame=raw['frame'],scene=raw['scene']))
            seen=runner.team_state(observed,runner.controls_by_id(recognition.control_registry,raw['size']))
            assert seen['participants']==(8,12) and seen['availability'] is None and seen['unavailable']==[]
            results.append(dict(primary_withheld=forced,task=task,frame=str(path.relative_to(ROOT)),
                binding=reference.as_dict(),participants=list(seen['participants']),fallback=fallback,
                typed_local_records=len(raw['local_ocr']),learning_writes='quarantined',device_inputs=0))
    finally:lease.close()
    assert snapshot==source_snapshot(ROOT) and private==private_hashes(app)
    assert all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in {**originals,**canonical}.items())
    result=dict(passed=True,source=str(source.relative_to(ROOT)),source_binding=binding,cases=results,
        device_inputs=0,game_controller_created=False,private_preserved=len(private),canonical_preserved=len(canonical),
        original_pairs_unchanged=True,source_snapshot_unchanged=True,
        scope='Actual source production observation/native OCR/Journaling/FrameRef/team_state on retained pixels; primary gap injected in one case. Not frozen callback or live continuation.')
    body=json.dumps(result,indent=2)+'\n';workspace.require_space(ROOT,len(body.encode())+32768)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(body,encoding='utf8')
    print(json.dumps(dict(passed=True,cases=len(results),device_inputs=0,report=str(args.report))))
    return 0


if __name__=='__main__':raise SystemExit(main())
