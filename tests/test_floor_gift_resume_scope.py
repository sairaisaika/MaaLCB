"""A sent pick survives process restart and unrelated trial OCR drift.

The retained gift-only frames are fixtures, independent of runtime cleanup.
They show 0/2 -> 1/2 for Layered Bandages; Painkiller's trial loses '+1'.
"""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from maalimbus.floor_gifts import observe
from maalimbus.floor_gift_transaction import FloorGiftTransaction
from maalimbus.gift_vision import GiftCatalog
from maalimbus.vision import Text
from maalimbus import runner
from maalimbus.storage import write_json

FIXTURES = Path(__file__).parent / 'fixtures/floor-gift-ocr-drift'
ROOT = Path(__file__).resolve().parents[1]
# The recovery proof reopens the captured frames; they are game screenshots, so a
# public checkout has only the JSON beside them (docs/local-assets.md).
FRAMES = pytest.mark.needs_local('tests/fixtures/floor-gift-ocr-drift/before.png',
                                 'tests/fixtures/floor-gift-ocr-drift/after.png')


def observations():
    catalog = GiftCatalog(ROOT / 'assets/resource/base')
    values = []
    for name in ('before', 'after'):
        path = FIXTURES / (name + '.json')
        record = json.loads(path.read_text(encoding='utf8'))
        offers, count = observe([Text(r['text'], tuple(r['box']), r['score'])
                                 for r in record['ocr']], record['size'], catalog)
        values.append((offers, count, path))
    return catalog, values


def reserved(tmp_path, *, legacy=False):
    catalog, (before, after) = observations()
    offers, count, proof = before
    tx = FloorGiftTransaction(tmp_path / 'gift.json')
    tx.prepare('game', offers, count, proof)
    tx.intent('Layered Bandages', count, proof)
    if legacy:
        tx.data.pop('offer_snapshot')
        write_json(tx.path, tx.data)
    return tx, catalog, after


@FRAMES
@pytest.mark.parametrize('legacy', [False, True])
def test_real_pick_recovers_in_a_new_process_directory(tmp_path, legacy):
    tx, catalog, (after, count, proof) = reserved(tmp_path, legacy=legacy)
    tx = FloorGiftTransaction(tx.path)
    raw = tx.path.read_bytes()
    assert tx.retire_from_another_run(tmp_path / 'new-recorder', scope='game') is None
    assert tx.retire_stale_run('game', tx.signature(after)) is None
    assert tx.path.read_bytes() == raw
    assert tx.recover_pick('game', after, count, proof, catalog) is True
    assert tx.data['selected'] == ['Layered Bandages']
    assert tx.data['pending'] is None
    assert tx.data['offer'] == tx.signature(after)
    # A further prepare continues at 1/2; it does not reserve that pick again.
    tx.prepare('game', after, count, proof)
    with pytest.raises(ValueError, match='would_repeat'):
        tx.intent('Layered Bandages', count, proof)


def test_unrelated_trial_drift_is_not_a_different_shelf(tmp_path):
    tx, _, (offers, count, proof) = reserved(tmp_path)
    assert tx.data['offer'] != tx.signature(offers)
    tx.observe_pick(offers, count, proof)
    assert tx.data['selected'] == ['Layered Bandages']
    assert next(o for o in offers if o.title == 'Painkiller').unpriced


def test_a_subsequent_read_refreshes_trials_without_resetting_picks(tmp_path):
    tx, _, (offers, count, proof) = reserved(tmp_path)
    tx.observe_pick(offers, count, proof)
    reread=[replace(o, unpriced='Defense Skill Final Power +1')
            if o.title=='Painkiller' else o for o in offers]
    tx.prepare('game',reread,count,proof)
    assert tx.data['selected']==['Layered Bandages']
    assert tx.data['screen_before']==0 and tx.data['pending'] is None
    assert tx.data['offer_revisions'][-1]['proof']==str(proof)


@pytest.mark.parametrize('defect', [pytest.param(d, marks=FRAMES) for d in
                                    ('target_trial', 'other_title', 'counter', 'required')] + ['scope'])
def test_drift_recovery_keeps_real_mismatches_pending(tmp_path, defect):
    tx, catalog, (offers, count, proof) = reserved(tmp_path)
    scope = 'game'
    if defect == 'target_trial':
        offers = [replace(o, unpriced='Unknown changed trial')
                  if o.title == 'Layered Bandages' else o for o in offers]
    elif defect == 'other_title':
        offers = [replace(o, title='Different gift') if o.title == 'Painkiller' else o
                  for o in offers]
    elif defect == 'counter': count = dict(count, chosen=2)
    elif defect == 'required': count = dict(count, required=3)
    else: scope = 'another-game'
    raw = tx.path.read_bytes()
    with pytest.raises(ValueError):
        tx.recover_pick(scope, offers, count, proof, catalog)
    assert tx.path.read_bytes() == raw
    assert FloorGiftTransaction(tx.path).data['pending']['title'] == 'Layered Bandages'


def test_missing_game_identity_cannot_retire_an_intent(tmp_path):
    tx, _, _ = reserved(tmp_path)
    raw = tx.path.read_bytes()
    assert tx.retire_from_another_run(tmp_path / 'recorder') is None
    assert tx.path.read_bytes() == raw


def test_resume_door_preserves_deployment_and_gift_intents(tmp_path):
    from maalimbus.deployment_transaction import DeploymentTransaction
    tx, _, _ = reserved(tmp_path)
    path = tmp_path / 'deployment.json'
    write_json(path, dict(scope='game', pending=dict(kind='card', card=2)))
    deployment = DeploymentTransaction(path)
    loop = runner.MirrorRunner.__new__(runner.MirrorRunner)
    loop.run_id = 'game'
    loop.directory = tmp_path / 'new-process'
    loop.floor_gift_transaction = tx
    loop.deployment_transaction = deployment
    loop.theme_transaction = loop.initial_transaction = None
    loop.note = lambda *a, **k: None
    raw = {p: p.read_bytes() for p in (path, tx.path)}
    loop._retire_foreign_pending()
    assert all(p.read_bytes() == data for p, data in raw.items())


@pytest.mark.parametrize('old_scope', [None, 'historical-game', 'current-game'])
def test_starting_the_loop_never_reassigns_a_saved_module_budget(tmp_path, old_scope):
    class EndOfPreparation(Exception): pass
    policy = tmp_path / 'user-mirror-settings.json'
    write_json(policy, dict(module_budget_pending=False, max_reward_modules=6,
                            reward_budget_scope=old_scope))
    raw = policy.read_bytes()
    loop = runner.MirrorRunner.__new__(runner.MirrorRunner)
    loop.run_id = 'current-game'
    loop.store = SimpleNamespace(path=tmp_path / 'user-run-ledger.json')
    loop.settings = SimpleNamespace(observe_only=True)
    loop._retire_foreign_pending = lambda: None
    loop.note = lambda *a, **k: None
    def stop(): raise EndOfPreparation
    loop._start_stall_watch = stop
    with pytest.raises(EndOfPreparation): loop._walk()
    assert policy.read_bytes() == raw
