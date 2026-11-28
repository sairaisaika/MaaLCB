"""Native paid-offer recognition on the retained two-digit Claim frame; device input forbidden.

`verify_reward_cost_replay.py` proves the one-digit layout (6 modules, weekly 1/3) on
`window-20261008-144554/frame-0458`. This is its twin for the layout a second cost digit
produces: `pi-20261120-193352/frame-0269`, 18 modules with weekly bonuses 3/3, where the
currency icon and the deduction sign sit six pixels further left. The real Maa library
reads the frame through the same custom recognition the installed Agent registers.
"""
import pathlib as _pathlib
import sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1] / 'src'))
import argparse,json,time,cv2
from maalimbus.replay import ReplayController as Replay
ROOT=_pathlib.Path(__file__).resolve().parents[1]
_sys.path[:0]=[str(ROOT/'src'),str(ROOT/'agent')]
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker
from recognition import Journal,LimbusRecognition
from maalimbus.jobs import wait_job,wait_task

FRAME=ROOT/'dist/MaaLimbus/evidence/runtime/pi-20261120-193352/frame-0269.png'
OFFER=dict(currency='enkephalin_modules',cost=18,weekly=3)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame',type=_pathlib.Path,default=FRAME)
    parser.add_argument('--report',type=_pathlib.Path,default=ROOT/'build/reward-cost-two-digit-replay.json')
    args=parser.parse_args(argv)
    Library.open(ROOT/'dist/MaaLimbus/maafw',agent_server=False)
    original=cv2.imread(str(args.frame))
    if original is None:raise SystemExit('Retained two-digit Claim frame is not readable: %s'%args.frame)
    results=[]
    for case in ('actual','missing_currency','missing_sign','missing_digit','missing_title','one_digit_position'):
        image=original.copy()
        if case=='missing_currency':image[785:850,1364:1425]=0
        if case=='missing_sign':image[805:838,1423:1444]=0
        if case=='missing_digit':image[790:840,1446:1480]=0
        if case=='missing_title':image[145:205,780:1140]=0
        if case=='one_digit_position':
            # Marks drawn where a one-digit cost puts them, beside the two-digit cost:
            # two readings that disagree about the row are not an offer.
            marks=image[786:850,1364:1446].copy();image[786:850,1364:1446]=image[720:784,1364:1446]
            image[786:850,1370:1452]=marks
        journal=Journal(ROOT/f'evidence/runtime/reward-cost-two-digit-replay-{time.time_ns()}-{case}')
        rec=LimbusRecognition('en',journal);controller=Replay(image);resource=Resource()
        resource.register_custom_recognition('limbus_scene',rec)
        for layer in ('base','en'):wait_job(resource.post_bundle(ROOT/f'assets/resource/{layer}'),timeout=20)
        wait_job(controller.post_connection());controller.set_screenshot_target_long_side(1920)
        tasker=Tasker();assert tasker.bind(resource=resource,controller=controller)
        wait_task(tasker,tasker.post_task('Probe',{'Probe':{'recognition':'Custom','custom_recognition':'limbus_scene','custom_recognition_param':{'scene':'RUN_REWARD_DIALOG'},'action':'DoNothing','timeout':2000}}),deadline=time.monotonic()+12)
        data=json.loads((journal.directory/(rec.cache[3]+'.json')).read_text())
        target=data.get('reward_cost')
        assert bool(target)==(case=='actual'),(case,data.get('reward_cost_provenance'))
        if target:assert target==OFFER,target
        results.append(dict(case=case,target=target,scene=data.get('scene'),device_input=False,
                            marks=[dict(purpose=row['purpose'],layout=row.get('layout'),
                                        results=row['results'])
                                   for row in data.get('reward_cost_provenance') or []],
                            evidence=str(journal.directory)))
    args.report.write_text(json.dumps(dict(passed=True,frame=str(args.frame),cases=results),indent=2)+'\n')
    print(args.report)


if __name__=='__main__':main()
