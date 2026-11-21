"""Read-only audit of the retained value candidate and an isolated flag flip.

The offers are hypothetical test inputs, not live shop quotes. No controller,
training, account setting, real model edit or purchase input is involved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maalimbus.shop_value_shadow import rank_preview,diagnostic
from maalimbus.shop_value_training import readiness_report,load_catalog
from maalimbus.storage import read_json,write_json
from maalimbus.update_install import private_hashes,closed_app
from maalimbus.workspace import reserve_output,size


def verify(*,installed=False):
    model=ROOT/'assets/resource/base/model/shop-value'
    before={name:hashlib.sha256((model/name).read_bytes()).hexdigest()
            for name in ('weights.json','modelcard.json')}
    private={str(base):private_hashes(base) for base in (ROOT,ROOT/'dist/MaaLimbus')}
    offers=[SimpleNamespace(name=n,price=100) for n in ('Prestige Card',"Devil's Share")]
    context=dict(coins=1000,reserve_coins=0,keywords=['Poise'])
    kept,baseline=rank_preview(offers,context,model)
    # A local synthetic change tests a known loophole; it never edits the model
    # loaded by the app. Reserve both small model files before making the copy.
    reserve_output(ROOT/'build',size(model)+65536)
    with tempfile.TemporaryDirectory(prefix='shop-promotion-audit-',dir=ROOT/'build') as temporary:
        isolated=Path(temporary)/'model';shutil.copytree(model,isolated)
        card=read_json(isolated/'modelcard.json')
        card['participation']='ranked'
        card.setdefault('curriculum',{}).update(pairs=99999,pairwise_accuracy=1.0)
        write_json(isolated/'modelcard.json',card)
        attempted,flipped=rank_preview(offers,context,isolated)
    ready=readiness_report(ROOT/'build/learning-review/shop-purchases',
        load_catalog(ROOT/'assets/resource/base/gift-catalog.json'),ledger=ROOT/'config/user-run-ledger.json')
    packaged=None
    parity=None
    if installed:
        app=ROOT/'dist/MaaLimbus';closed_app(app)
        run=subprocess.run([str(app/'agent/MaaLimbusAgent.exe'),'--self-test'],cwd=app,
            capture_output=True,text=True,timeout=60,check=True)
        proof=json.loads(run.stdout)
        packaged=proof.get('shop_value_diagnostic')
        expected=diagnostic(model)
        if (proof.get('device_controller') is not False or not isinstance(packaged,dict) or
                packaged.get('prediction_executed') is not True or
                packaged.get('model_sha256') != before['weights.json'] or
                packaged.get('game_input') is not False or packaged.get('neural_value_ranked') is not False):
            raise ValueError('Installed legacy shadow scorer diagnostic not verified')
        parity=(packaged.keys()==expected.keys() and
                all(packaged[k]==expected[k] for k in expected if k!='scores') and
                len(packaged['scores'])==len(expected['scores']) and
                all(a['name']==b['name'] and a['price']==b['price'] and
                    abs(a['predicted_review_value']-b['predicted_review_value'])<1e-12
                    for a,b in zip(packaged['scores'],expected['scores'])))
        if not parity:raise ValueError('Installed/source scorer prediction differs')
    unchanged=all(hashlib.sha256((model/name).read_bytes()).hexdigest()==sha for name,sha in before.items())
    private_unchanged=all(private[str(base)]==private_hashes(base) for base in (ROOT,ROOT/'dist/MaaLimbus'))
    passed=(kept==offers and attempted==offers and baseline['neural_value_shadow_applied']
            and flipped['neural_value_shadow_applied'] and not baseline['neural_value_ranked']
            and not flipped['neural_value_ranked'] and unchanged and private_unchanged)
    return dict(passed=passed,scope='retained actual legacy shadow candidate; hypothetical offers; isolated metadata flag flip',
        model_hashes=before,baseline=baseline,flag_flip=flipped,model_unchanged=unchanged,
        private_unchanged=private_unchanged,current_retraining_readiness=ready,
        installed_scorer_diagnostic=packaged,
        installed_matches_source=parity,
        packaged_prediction_verified=packaged is not None,
        game_input=False,controller_created=False,formal_purchase_policy_verified=False,
        workspace_bytes=size(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--installed',action='store_true',help='also execute the closed installed Agent self-test')
    args=parser.parse_args();result=verify(installed=args.installed)
    reserve_output(args.report,65536);write_json(args.report,result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
