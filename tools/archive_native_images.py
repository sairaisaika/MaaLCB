"""Compact old diagnostics losslessly, retaining original logical frame paths."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus import native_image_archive as archive,workspace
from maalimbus.controller_lease import ControllerLease
from maalimbus.documents import write_document


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--apply',action='store_true')
    mode.add_argument('--enable-vault',action='store_true',
                      help='opt into bounded local external storage for sealed historical containers')
    mode.add_argument('--offload',action='store_true',help='fund space using an already enabled vault')
    mode.add_argument('--prepare-live',type=Path,metavar='CLOSED_RUN',
                      help='reclaim protected-policy headroom before opening the next game task')
    parser.add_argument('--vault-budget',type=int,
                        help='explicit local vault ceiling in bytes, only with --enable-vault')
    parser.add_argument('--target-free',type=int,default=65_000_000)
    parser.add_argument('--batch-bytes',type=int,default=8_000_000)
    parser.add_argument('--report',type=Path,default=ROOT/'build/native-image-archive-real-verification.json')
    args=parser.parse_args()
    if args.vault_budget is not None and (not args.enable_vault or
            not 0 < args.vault_budget <= archive.MAX_VAULT_BYTES):
        parser.error('--vault-budget requires --enable-vault and a supported positive limit')
    if not 0<args.batch_bytes<=archive.MAX_BATCH or not 0<=args.target_free<=workspace.BUDGET_BYTES:
        parser.error('Bounded batch and target required')
    lease=ControllerLease.acquire(ROOT/'build/controller.lock')
    try:
        before=workspace.size(ROOT);rows=[]
        if args.enable_vault or args.offload:
            from maalimbus.native_cold_vault import enable,offload
            if args.enable_vault:enable(ROOT,budget=args.vault_budget)
            elif archive.vault_policy(ROOT) is None:raise ValueError('Local image vault is not enabled')
            row=offload(ROOT,target_free=args.target_free,max_containers=64)
            rows.append(row)
            print(json.dumps(row),flush=True)
        elif args.prepare_live is not None:
            from maalimbus import capture_retention
            from maalimbus.native_cold_vault import offload_framework_logs
            root,runtimes=capture_retention.roots(ROOT)
            directory=args.prepare_live.resolve(strict=True)
            if directory.parent not in runtimes or not directory.is_dir():
                parser.error('Closed run must be a direct child of a native evidence directory')
            try:
                rows.append(offload_framework_logs(root,target_free=args.target_free))
            except PermissionError:
                rows.append(dict(framework_log_vault_unavailable=True))
            row=capture_retention.reserve(directory,args.target_free,application_root=root)
            rows.append({key:row[key] for key in ('used_bytes','sufficient','reclaimable_bytes',
                        'storage_maintenance','vault_project_bytes_freed') if key in row})
        elif args.apply:
            # Published duplicates are the sole resumable intermediate state.
            archive.retire(ROOT,list(archive.load_index(ROOT)['members']))
            while workspace.size(ROOT)+args.target_free>workspace.BUDGET_BYTES:
                row=archive.compact(ROOT,max_bytes=args.batch_bytes);rows.append(row)
                print(json.dumps(row),flush=True)
                if row.get('freed',0)<=0 and row.get('reason')!='no_lossless_gain':break
        else:
            eligible=archive.candidates(ROOT)
            print(json.dumps(dict(files=len(eligible),raw_bytes=sum(x['bytes'] for x in eligible))))
        index=archive.load_index(ROOT)
        archive.verify_all(ROOT)
        applied=bool(args.apply or args.enable_vault or args.offload or args.prepare_live)
        result=dict(passed=True,applied=applied,before_bytes=before,after_bytes=workspace.size(ROOT),
                    archived_images=len(index['members']),all_members_read_back=True,batches=rows,
                    target_free_bytes=args.target_free,target_met=workspace.size(ROOT)+args.target_free<=workspace.BUDGET_BYTES,
                    controller_created=False,input_sent=False)
        write_document(args.report,result,application_root=ROOT)
        return 0 if not applied or result['target_met'] else 1
    finally:lease.close()


if __name__=='__main__':raise SystemExit(main())
