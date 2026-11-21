"""Plan or apply pressure-only intermediate capture reclamation, with no device."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus import capture_retention,workspace
from maalimbus.controller_lease import ControllerLease
from maalimbus.storage import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'evidence/runtime/capacity-reservation')
    parser.add_argument('--reserve-bytes',type=int,default=64_000_000)
    parser.add_argument('--apply-plan',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'build/capture-retention-plan.json')
    args=parser.parse_args()
    if not 0<=args.reserve_bytes<=workspace.BUDGET_BYTES:
        parser.error('Reservation must fit the project cap')
    # Reuse the single-controller lease so a live task cannot begin while an
    # offline compaction plan is being applied. This tool creates no controller.
    lease=ControllerLease.acquire(ROOT/'build/controller.lock')
    try:
        if args.apply_plan:
            expected=json.loads(args.apply_plan.read_text(encoding='utf8'))
            if expected.get('kind')!='capture_retention_plan':raise ValueError('Native retention plan required')
            result=capture_retention.apply(ROOT,Path(expected['directory']),expected)
            result={**result,'kind':'capture_retention_result','applied':True,
                    'after_bytes':workspace.size(ROOT),'game_inputs':0}
        else:
            result=capture_retention.plan(ROOT,args.directory,args.reserve_bytes)
        body=json.dumps(result,ensure_ascii=False,indent=2).encode('utf8')
        workspace.require_space(ROOT,len(body)+8192)
        write_json(args.report,result)
        print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))
        print('selected_files='+str(len(result['files'])))
        return 0 if result['sufficient'] else 1
    finally:lease.close()


if __name__=='__main__':raise SystemExit(main())
