"""One native header-return to correct a proved, unspent entry-team mismatch.

Does not select a team, buy a grace, clear a pending transaction or edit a ledger.
The matched header arrow is read by the existing Maa recognition callback. A
durable attempted-input record precedes its action; an unresolved intent is not
replayed. Success retains a human-review transition candidate.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'agent')]
from maalimbus.storage import read_json,write_json
from maalimbus.unknown_exploration import proof
from maalimbus.vision import Text
from maalimbus.team_vision import selected_saved_team
from maalimbus.grace_vision import available_starlight
from maalimbus.controller_lease import ControllerLease
from maalimbus.adb_device import discover,foreground_of,build,pin_input
from maalimbus.jobs import wait_job,wait_task
from maalimbus.semantic_labels import candidate_transition
from recognition import Journal,LimbusRecognition


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--team-frame',type=Path,required=True)
    parser.add_argument('--star-frame',type=Path,required=True)
    parser.add_argument('--wanted-team',type=int,required=True)
    parser.add_argument('--address',default='127.0.0.1:16416')
    parser.add_argument('--intent',type=Path,default=ROOT/'build/unspent-entry-return-intent.json')
    args=parser.parse_args()
    if args.intent.exists():raise ValueError('Recovery intent exists; inspect its successor instead of replaying')
    team_proof,team_record=proof(args.team_frame)
    star_proof,star_record=proof(args.star_frame)
    def texts(record):return [Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']]
    selected=selected_saved_team(texts(team_record),team_record['size'])
    if team_record.get('scene')!='DUNGEON_TEAM' or selected is None or selected==args.wanted_team:
        raise ValueError('Independent entry-team mismatch required')
    if star_record.get('scene')!='STAR_GRACES':raise ValueError('Prior unspent grace page required')
    available=available_starlight(texts(star_record),star_record['size'])
    if available is None:raise ValueError('Prior grace balance is unreadable')
    directory=ROOT/'evidence/runtime'/('entry-return-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    journal=Journal(directory)
    private=[ROOT/'config'/name for name in ('user-run-ledger.json','user-mirror-settings.json',
        'user-floor-gift-transaction.json','user-reward-claim-transaction.json')]
    def private_hashes():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in private}
    before_private=private_hashes()
    result=dict(passed=False,device_inputs=0,wanted_team=args.wanted_team,actual_team=selected,
                directory=str(directory),canonical_state_changed=False)
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit
    Library.open(ROOT/'dist/MaaLimbus/maafw')
    lease=ControllerLease.acquire(ROOT/'build/controller.lock')
    tasker=None
    try:
        device=discover(args.address)
        result['foreground_before']=foreground_of(device)
        Toolkit.init_option(directory/'debug')
        controller=build(pin_input(device,'Maatouch'),input_enabled=True)
        wait_job(controller.post_connection(),timeout=15)
        controller.set_screenshot_target_long_side(1920)
        recognition=LimbusRecognition('en',journal)
        duration=random.randint(350,750)
        def intent_before_input():
            foreground_of(device)
            before_frame=sorted(directory.glob('frame-*.json'))[-1]
            bound,record=proof(before_frame)
            if record.get('scene')!='STAR_GRACES' or available_starlight(texts(record),record['size'])!=available:
                raise ValueError('Fresh unspent entry page changed; preserve original state')
            if args.intent.exists():raise ValueError('Entry-return input already attempted')
            write_json(args.intent,dict(version=1,pending=True,input_attempted=True,
                before=bound,prior_team=team_proof,prior_star=star_proof,actual_team=selected,
                wanted_team=args.wanted_team,native_template='navigation/tutorial-back.png',
                native_threshold=.92,duration_ms=duration,resource_inputs=0))
            result['device_inputs']=1
        recognition.input_validator=intent_before_input
        resource=Resource()
        resource.register_custom_recognition('limbus_scene',recognition)
        for layer in ('base','en'):
            wait_job(resource.post_bundle(ROOT/f'assets/resource/{layer}'),timeout=30)
        def observed(scene):return dict(recognition='Custom',custom_recognition='limbus_scene',
            custom_recognition_param=dict(scene=scene),action='DoNothing',next=[])
        node=observed('STAR_GRACES')
        node.update(custom_recognition_param=dict(scene='STAR_GRACES',tutorial_back=True),
                    action='LongPress',target=True,duration=duration,max_hit=1,
                    timeout=8000,next=['EntryReturnedTeam','EntryReturnedMenu'])
        assert resource.override_pipeline(dict(EntryReturnBack=node,
            EntryReturnedTeam=observed('DUNGEON_TEAM'),EntryReturnedMenu=observed('MIRROR_ENTRY')))
        tasker=Tasker();assert tasker.bind(resource,controller)
        result['task']=wait_task(tasker,tasker.post_task('EntryReturnBack'),deadline=time.monotonic()+30)
        files=sorted(directory.glob('frame-*.json'))
        after=files[-1];after_proof,record=proof(after)
        result['page_after']=record.get('scene')
        result['canonical_state_changed']=private_hashes()!=before_private
        result['passed']=bool(result['task']['task_succeeded'] and result['page_after'] in ('DUNGEON_TEAM','MIRROR_ENTRY')
                              and result['device_inputs']==1 and not result['canonical_state_changed'])
        if result['passed']:
            intent=read_json(args.intent)
            transition=dict(page='STAR_GRACES',allowed_operations=['matched_header_return'],bounded=True,
                steps_used=1,step_limit=1,before_frame=Path(intent['before']['record']).relative_to(ROOT).as_posix(),
                after_frame=after.relative_to(ROOT).as_posix(),
                action=dict(kind='matched_header_return',reason='correct_proven_unspent_team_mismatch',
                            expected_effect='return_to_entry_navigation'),
                success_assertion=dict(role='success',verified=True,teacher='independent_native_page_caption',
                    candidate_label=('unspent_entry_returns_to_team_picker' if result['page_after']=='DUNGEON_TEAM'
                                     else 'unspent_entry_returns_to_mirror_menu'),
                    postcondition='Fresh native '+result['page_after'],evidence=after_proof))
            result['review']=candidate_transition(ROOT,directory.name,'en',transition,ROOT/'build/learning-review/transitions')
            intent.update(pending=False,successor=after_proof,page_after=result['page_after'])
            write_json(args.intent,intent)
    finally:
        if tasker is not None and tasker.running:wait_job(tasker.post_stop(),timeout=5)
        write_json(directory/'result.json',result)
        lease.close()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
