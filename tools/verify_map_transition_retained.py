"""Exercise the navigation judgement on a verified real pair and obscured-label controls.

No native controller, input, private-state update or training-label publication.
The unknown/loading controls are synthetic label obscuration, not real landings.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from maalimbus import map_dispatch,runner,window


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if not args.out.resolve().is_relative_to(ROOT/'build'):
        raise ValueError('Keep the local audit in build')
    directory=ROOT/'evidence/runtime/packaged-mirror-20261117-014047'
    pair=[]
    for name,scene in [('frame-0004','MAP'),('frame-0005','NODE_PANEL')]:
        path=directory/(name+'.json');record=json.loads(path.read_text(encoding='utf8'))
        assert record['scene']==scene and digest(path.with_suffix('.png'))==record['image_sha256']
        pair.append(dict(path=str(path.relative_to(ROOT)),json_sha256=digest(path),
                         png_sha256=record['image_sha256'],record=record))
    config={p:digest(p) for p in (ROOT/'config').rglob('*') if p.is_file()}
    events=[]
    class Journal:
        def record(self,event,**fields):events.append(dict(event=event,**fields))
    target=[1201,220,93,76]
    plan=window.plan_step('MAP',candidates=[target])
    with tempfile.TemporaryDirectory(prefix='maalimbus-transition-audit-') as temp:
        loop=runner.MirrorRunner(runner.FakeDevice(),directory=Path(temp),
                                 settings={},journal=Journal())
        pending=dict(target=target,frame='frame-0004',expect=plan['expect'],kind='lit_ring')
        loop.state['map_unjudged']=pending
        loop.state.update(map_pending=target,map_committed=target)
        controls=[]
        for label in ('UNKNOWN','LOADING','TUTORIAL','HOME'):
            outcome=loop._resolve_map_click(label,observation=dict(frame='synthetic-label-obscuration'))
            assert outcome=='unjudged' and loop.state['map_unjudged'] is pending
            assert not any(r['event']=='map_click_result' for r in events)
            controls.append(dict(synthetic_label=label,outcome=outcome,pending_preserved=True))
        outcome=loop._resolve_map_click('NODE_PANEL',observation=pair[1]['record'])
        assert outcome=='accepted' and loop.state['map_unjudged'] is None
        assert not loop.state.get('map_pending') and not loop.state.get('map_committed')
        accepted=[r for r in events if r['event']=='map_click_result']
        assert len(accepted)==1 and accepted[0]['after_image_sha256']==pair[1]['png_sha256']
        assert loop.device.clicks==[]
    assert all(digest(p)==sha for p,sha in config.items())
    report=dict(passed=True,real_pair=[{k:v for k,v in row.items() if k!='record'} for row in pair],
                synthetic_negative_controls=controls,accepted_event=accepted[0],
                private_files_unchanged=len(config),input_sent=False,game_controller=False,
                training_eligible=False,production_enabled=False,
                scope='retained positive judgement and synthetic uncertainty controls; not new live input acceptance')
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=True,positive_pairs=1,synthetic_controls=len(controls),input_sent=False)))


if __name__=='__main__':main()
