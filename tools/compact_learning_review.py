"""Plan or remove exact legacy semantic-review mirrors; originals/labels stay."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.review_storage import compaction_plan,compact
from maalimbus.storage import write_json,read_json
from maalimbus.workspace import size


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--queue',choices=('frames','transitions'),default='frames')
    args=parser.parse_args();queue=ROOT/('build/learning-review/'+args.queue)
    if args.apply:
        result=compact(ROOT,queue,read_json(args.plan,limit=16*1024*1024))
        result['workspace_bytes']=size(ROOT)
        write_json(args.plan.with_suffix('.result.json'),result)
        print(json.dumps(result,ensure_ascii=False))
    else:
        plan=compaction_plan(ROOT,queue);write_json(args.plan,plan)
        print(json.dumps(dict(files=len(plan['files']),rejected=len(plan['rejected']),
                              reclaimable_bytes=plan['reclaimable_bytes'])))


if __name__=='__main__':main()
