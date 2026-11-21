"""Replay native event completion against two original retained page witnesses.

This is a protocol replay, not an SDK/device capture or proof of current gameplay.
Original files stay untouched. Temporary copies stay within the project budget.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    from maalimbus import runner,workspace
    from maalimbus.native_evidence import bound_frame
    sources=[ROOT/'evidence/runtime/packaged-mirror-20261031-205402/frame-0011.json',
             ROOT/'evidence/runtime/packaged-mirror-20261117-010749/frame-0055.json']
    originals=[dict(path=str(p.relative_to(ROOT)),binding=bound_frame(p)[0]) for p in sources]
    raw=[json.loads(p.read_text(encoding='utf8')) for p in sources]
    workspace.require_space(ROOT,sum(f.stat().st_size for p in sources for f in (p,p.with_suffix('.png')))+500_000)
    with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='observation-binding-') as temp:
        directory=Path(temp)
        for p in sources:
            for f in (p,p.with_suffix('.png')):shutil.copyfile(f,directory/f.name)
        class Reader:
            requires_frame_ref=True
            def __init__(self):self.directory=directory
            def observe(self,*,deadline=None):return dict(frame=sources[0].stem,scene='BATTLE_HUD')
        event=runner.observe(Reader())
        assert event['image_sha256']==raw[0]['image_sha256'] and event['ocr']==raw[0]['ocr']
        assert event['frame_ref']['json_sha256']==originals[0]['binding']['json_sha256']
        reference=dict(event['frame_ref']);reference['record_path']=originals[0]['path']
        (directory/sources[0].with_suffix('.png').name).unlink()
        try:runner.observe(Reader())
        except runner.ReadNeverReturned as error:missing=dict(refused=True,reason=str(error))
        else:raise AssertionError('Missing named PNG borrowed the newer shop')
    assert originals==[dict(path=str(p.relative_to(ROOT)),binding=bound_frame(p)[0]) for p in sources]
    value=dict(passed=True,inputs=originals,frame_ref=reference,missing_named_png=missing,
               protocol_fixture=True,native_sdk_run=False,controller_created=False,game_inputs=0,
               verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               scope='retained original-byte/event binding, not live observation or game completion')
    payload=json.dumps(value,indent=2).encode();workspace.reserve_output(args.report,len(payload),application_root=ROOT)
    args.report.write_bytes(payload);print(json.dumps(dict(passed=True,game_inputs=0)))
    return 0


if __name__=='__main__':raise SystemExit(main())
