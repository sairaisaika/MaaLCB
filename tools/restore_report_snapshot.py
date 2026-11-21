"""Reconstruct an old report ZIP byte-exactly from current immutable members.

Default is memory-only verification. --restore recreates the recipe's original
build ZIP only after its expected digest and the workspace budget pass.
"""
import argparse,base64,hashlib,io,json,os,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from maalimbus.evidence_reports import load_index,_verified_members,_plain
from maalimbus.workspace import require_space


def reconstruct(recipe,members):
    if recipe.get('version')!=1 or recipe.get('kind')!='report_snapshot_recipe':
        raise ValueError('Invalid report snapshot recipe')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        archive.comment=base64.b64decode(recipe['comment'],validate=True)
        for row in recipe['members']:
            data=members[row['filename']]
            if hashlib.sha256(data).hexdigest()!=row['sha256']:
                raise ValueError('Snapshot member changed')
            info=zipfile.ZipInfo(row['filename'],tuple(row['date_time']))
            for key in ('compress_type','create_system','create_version','extract_version',
                        'reserved','flag_bits','volume','internal_attr','external_attr'):
                setattr(info,key,row[key])
            info.extra=base64.b64decode(row['extra'],validate=True)
            info.comment=base64.b64decode(row['comment'],validate=True)
            archive.writestr(info,data,compress_type=info.compress_type,compresslevel=9)
    value=output.getvalue()
    if len(value)!=recipe['bytes'] or hashlib.sha256(value).hexdigest()!=recipe['sha256']:
        raise ValueError('Reconstructed container is not byte-exact; preserve existing copy')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe',type=Path);parser.add_argument('--restore',action='store_true')
    args=parser.parse_args();recipe=json.loads(args.recipe.read_text(encoding='utf8'))
    target=_plain(ROOT,recipe['path'],'.zip')
    index=load_index(ROOT)
    if index is None:raise ValueError('Current verified report archive required')
    members=dict(_verified_members(index['archive'].read_bytes(),index['value']))
    value=reconstruct(recipe,members)
    if args.restore:
        if target.exists():
            if target.read_bytes()!=value:raise ValueError('Existing snapshot differs')
        else:
            require_space(ROOT,len(value)+8192)
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as handle:
                staged=Path(handle.name);handle.write(value);handle.flush();os.fsync(handle.fileno())
            try:os.replace(staged,target)
            finally:staged.unlink(missing_ok=True)
    print(json.dumps(dict(passed=True,bytes=len(value),sha256=recipe['sha256'],
                          restored=args.restore,game_input=False)))


if __name__=='__main__':main()
