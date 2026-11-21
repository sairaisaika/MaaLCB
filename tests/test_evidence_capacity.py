"""Native input cannot spend the space needed to record its successor."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
import recognition
from maalimbus import evidence_capacity as capacity, runner, workspace


@pytest.fixture
def captured(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, 'ROOT', tmp_path)
    journal = recognition.Journal(tmp_path / 'evidence/runtime/current', history_maintenance=True)
    image = np.random.default_rng(3).integers(0, 256, (32, 64, 3), dtype=np.uint8)
    name = journal.frame(image, [], 'MAP')
    return journal, image, journal.directory / (name + '.json')


def test_live_native_admission_uses_volume_free_space_without_history(captured,tmp_path,monkeypatch):
    prepared,_,proof=captured
    journal=recognition.Journal(prepared.directory)
    pending=tmp_path/'pending.json'
    pending.write_bytes(b'{"stage":"confirm_intent"}')
    originals=(proof.read_bytes(),proof.with_suffix('.png').read_bytes(),pending.read_bytes())
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+2_000_000)
    monkeypatch.setattr(capacity.capture_retention,'reserve',
                        lambda *args,**kwargs:pytest.fail('live admission attempted history maintenance'))
    monkeypatch.setattr(workspace.shutil, 'disk_usage', lambda _root: type('Usage', (), {'free': 0})())
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='volume has 0 bytes free'):
        journal.before_input('plan', ('click',10,20))
    assert (proof.read_bytes(),proof.with_suffix('.png').read_bytes(),pending.read_bytes())==originals
    monkeypatch.setattr(workspace.shutil, 'disk_usage', lambda _root: type('Usage', (), {'free': 50_000_000})())
    assert journal.before_input('plan', ('click',10,20))['successor_pairs'] == 2


def test_live_receipt_can_write_over_project_target(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', 1)
    target = tmp_path / 'receipt.json'
    with pytest.raises(ValueError, match='Workspace budget exceeded'):
        workspace.reserve_output(target, 256, application_root=tmp_path)
    with workspace.live_writes():
        workspace.reserve_output(target, 256, application_root=tmp_path)
    with pytest.raises(ValueError, match='Workspace budget exceeded'):
        workspace.reserve_output(target, 256, application_root=tmp_path)


@pytest.mark.parametrize('shape,dtype', [((10,20),np.uint8),((10,20,4),np.uint8),((10,20,3),np.uint16)])
def test_native_producer_refuses_unbudgeted_format_before_files_or_credit(captured,shape,dtype):
    journal,_,_=captured
    before={p:p.read_bytes() for p in journal.directory.iterdir()};index=journal.index
    with pytest.raises(ValueError,match='uint8 BGR'):
        journal.frame(np.zeros(shape,dtype=dtype),[],'MAP')
    assert journal.index==index and {p:p.read_bytes() for p in journal.directory.iterdir()}==before


def test_complete_oversize_metadata_is_refused_without_trimming_or_credit_consumption(captured,tmp_path):
    journal,image,_=captured;journal.before_input('click',('click',10,20))
    pool=capacity.EvidenceCapacity(tmp_path);before=pool.load()
    snapshots={p:p.read_bytes() for p in journal.directory.iterdir()};index=journal.index
    with pytest.raises(ValueError,match='metadata exceeds'):
        journal.frame(image,[],'MAP',extra_payload='x'*capacity.METADATA_BYTES)
    assert pool.load()==before and journal.index==index
    assert {p:p.read_bytes() for p in journal.directory.iterdir()}==snapshots


def test_incompressible_rgb_successor_fits_the_enforced_pair_bound(captured,tmp_path):
    journal,image,_=captured;journal.before_input('click',('click',10,20))
    pool=capacity.EvidenceCapacity(tmp_path);owner=pool.load()['owner']
    assert owner['capture_profile']==capacity.CAPTURE_PROFILE
    name=journal.frame(image,[],'MAP')
    pair=sum((journal.directory/(name+suffix)).stat().st_size for suffix in ('.json','.png'))
    assert pair<=owner['pair_bound']


def test_fullhd_incompressible_native_png_is_below_scanline_overhead_bound(tmp_path,monkeypatch):
    import cv2
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    pixels=np.random.default_rng(81).integers(0,256,(1080,1920,3),dtype=np.uint8)
    name=journal.frame(pixels,[],'BATTLE_HUD')
    before=journal.directory/(name+'.json')
    admission=journal.before_input('click',('click',10,20))
    assert admission['reserved_bytes']==16_699_268
    limit=(1920*capacity.CAPTURE_CHANNELS+1)*1080*101//100+65536
    assert before.with_suffix('.png').stat().st_size<=limit


def test_small_before_reserves_two_full_fallbacks_before_input(tmp_path,monkeypatch):
    monkeypatch.setattr(recognition,'ROOT',tmp_path)
    journal=recognition.Journal(tmp_path/'evidence/runtime/current')
    journal.frame(np.zeros((720,1280,3),np.uint8),[],'BATTLE_HUD')
    journal.capacity_successor_size=(1920,1080)
    admission=journal.before_input('click',('click',10,20))
    assert admission['reserved_bytes']==16_699_268
    pool=capacity.EvidenceCapacity(tmp_path)
    assert pool.load()['owner']['successor_size']==[1920,1080]
    # The declared producer may now emit both incompressible full-size proofs
    # without asking for another byte reservation after the input boundary.
    def unexpected_reservation(*args,**kwargs):
        raise AssertionError('Unplanned successor reservation after input admission')
    monkeypatch.setattr(capacity.capture_retention,'reserve',unexpected_reservation)
    for seed in (81,82):
        image=np.random.default_rng(seed).integers(0,256,(1080,1920,3),np.uint8)
        journal.frame(image,[],'UNKNOWN',extra_payload='x'*800000)
    assert pool.load()['bytes']>=capacity.STOP_BYTES


@pytest.mark.parametrize('size',[[True,1080],[1920,-1],[1920],'1920'])
def test_invalid_successor_size_cannot_mutate_capacity(captured,tmp_path,size):
    journal,_,before=captured
    journal.capacity_successor_size=size
    original={p:p.read_bytes() for p in journal.directory.iterdir()}
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='successor capture size'):
        journal.before_input('click',('click',10,20))
    assert not capacity.EvidenceCapacity(tmp_path).exists
    assert original=={p:p.read_bytes() for p in journal.directory.iterdir()}


def test_rgba_before_image_cannot_acquire_rgb_successor_credit(captured,tmp_path):
    import cv2
    journal,_,before=captured
    cv2.imwrite(str(before.with_suffix('.png')),np.zeros((32,64,4),np.uint8))
    record=json.loads(before.read_text());record['image_sha256']=hashlib.sha256(before.with_suffix('.png').read_bytes()).hexdigest()
    before.write_text(json.dumps(record));original=before.read_bytes()
    with pytest.raises(capacity.EvidenceCapacityUnavailable,match='BGR8 capture profile'):
        journal.before_input('click',('click',10,20))
    assert not capacity.EvidenceCapacity(tmp_path).exists and before.read_bytes()==original


class Controller:
    def __init__(self):
        self.sent = []

    def post_click(self, x, y):
        self.sent.append(('click', x, y))
        return object()

    def post_swipe(self, *args):
        self.sent.append(('swipe', *args))
        return object()

    def post_key(self, key):
        self.sent.append(('key', key))
        return object()

    def post_touch_down(self, *args):
        self.sent.append(('down', *args))
        return object()


@pytest.mark.parametrize('kind', ['click', 'swipe', 'key', 'pinch'])
def test_no_native_input_when_successor_capacity_is_unavailable(captured, tmp_path, monkeypatch, kind):
    journal, _, _ = captured
    snapshot = {p: p.read_bytes() for p in journal.directory.iterdir()}
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(tmp_path) + 100)
    native = Controller()
    device = runner.MaaDevice(native, target_long_side=0,
                             before_input=journal.before_input, wait=lambda *a, **k: None)
    with pytest.raises(capacity.EvidenceCapacityUnavailable, match='Workspace budget exceeded'):
        if kind == 'click':
            device.click(10, 20)
        elif kind == 'swipe':
            device.swipe(10, 20, 30, 40, 500)
        elif kind == 'key':
            native.id = 'native-test'
            device.key(4)
        else:
            device.pinch((10, 20), 5, 0.5)
    assert native.sent == []
    assert {p: p.read_bytes() for p in journal.directory.iterdir()} == snapshot
    assert not capacity.EvidenceCapacity(tmp_path).exists


def test_real_journal_consumes_reserved_bytes_at_an_otherwise_full_limit(captured, tmp_path, monkeypatch):
    journal, image, _ = captured
    journal.capacity_scope = 'scope-test'
    admission = journal.before_input('click', ('click', 10, 20))
    pool = capacity.EvidenceCapacity(tmp_path)
    initial = pool.load()
    assert initial['owner']['scope'] == 'scope-test'
    assert admission['successor_pairs'] == 2
    assert initial['bytes'] > 2 * capacity.METADATA_BYTES + capacity.STOP_BYTES
    # Other code sees the physical credit in workspace.size; it cannot spend it.
    full = workspace.size(tmp_path)
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', full)
    with pytest.raises(ValueError):
        workspace.require_space(tmp_path, 1, budget=full)
    for scene in ('UNKNOWN', 'NODE_PANEL'):
        name = journal.frame(image, [], scene)
        document = journal.directory / (name + '.json')
        row = json.loads(document.read_text(encoding='utf-8'))
        assert row['image_sha256'] == hashlib.sha256(document.with_suffix('.png').read_bytes()).hexdigest()
        assert workspace.size(tmp_path) <= full
    assert pool.load()['bytes'] < initial['bytes']
    assert pool.load()['bytes'] >= capacity.STOP_BYTES


def test_growth_between_admission_and_capture_reclaims_only_eligible_closed_diagnostics(captured,tmp_path,monkeypatch):
    from test_capture_retention import run
    journal,_,_=captured
    closed=run(tmp_path,'closed',closed=True)
    disposable=closed/'frame-0005.png';disposable.write_bytes(b'diagnostic'*220000)
    metadata=disposable.with_suffix('.json');data=json.loads(metadata.read_text())
    data['image_sha256']=hashlib.sha256(disposable.read_bytes()).hexdigest();metadata.write_text(json.dumps(data))
    snapshots={p:p.read_bytes() for p in closed.glob('*.json')}
    journal.before_input('click',('click',10,20))
    full=workspace.size(tmp_path);monkeypatch.setattr(workspace,'BUDGET_BYTES',full)
    # Simulate an independent native text writer consuming the admission margin.
    (tmp_path/'native.log').write_bytes(b'x'*500)
    image=np.random.default_rng(8).integers(0,256,(128,256,3),dtype=np.uint8)
    name=journal.frame(image,[],'PRE_BATTLE_TEAM')
    assert (journal.directory/(name+'.png')).exists()
    assert not disposable.exists() and workspace.size(tmp_path)<=full
    assert all(p.read_bytes()==body for p,body in snapshots.items())
    assert (tmp_path/'native.log').read_bytes()==b'x'*500
    assert capacity.EvidenceCapacity(tmp_path).load()['owner']['kind']=='click'
    assert capacity.EvidenceCapacity(tmp_path).load()['bytes'] >= capacity.STOP_BYTES


@pytest.mark.parametrize('resized', [False, True])
def test_restart_reconciles_only_storage_resize_without_business_verdict(captured, tmp_path, resized):
    journal, _, _ = captured
    journal.before_input('click', ('click', 10, 20))
    pool = capacity.EvidenceCapacity(tmp_path)
    original = pool.load()
    interrupted = dict(original, sequence=original['sequence'] + 1, state='resizing',
                       before=original['bytes'], bytes=original['bytes'] - 1000)
    pool._store(interrupted)
    if resized:
        with pool.credit.open('r+b') as handle:
            handle.truncate(interrupted['bytes'])
    # Simulate a torn ready record; the preceding resize intent remains valid.
    pool.slots[(interrupted['sequence'] + 1) % 2].write_bytes(b'x' * capacity.SLOT_BYTES)
    restored = capacity.EvidenceCapacity(tmp_path).load()
    assert restored['state'] == 'ready'
    assert restored['bytes'] == (interrupted['bytes'] if resized else original['bytes'])
    assert restored['owner'] == original['owner']
    assert not any(key in restored for key in ('accepted', 'input_sent', 'reward_received', 'completed'))


def test_unexplained_credit_size_change_is_preserved_and_refused(captured, tmp_path):
    journal, _, _ = captured
    journal.before_input('click', ('click', 10, 20))
    pool = capacity.EvidenceCapacity(tmp_path)
    with pool.credit.open('ab') as handle:
        handle.write(b'x')
    before = {p: p.read_bytes() for p in pool.slots}
    with pytest.raises(ValueError, match='size changed'):
        pool.load()
    assert {p: p.read_bytes() for p in pool.slots} == before


def test_before_frame_corruption_refuses_before_pool_or_device_changes(captured, tmp_path):
    journal, _, frame = captured
    frame.with_suffix('.png').write_bytes(b'changed screenshot')
    with pytest.raises(capacity.EvidenceCapacityUnavailable, match='hash changed'):
        journal.before_input('click', ('click', 10, 20))
    assert not capacity.EvidenceCapacity(tmp_path).exists


def test_fresh_frame_pair_from_another_capture_session_uses_same_recovered_pool(captured, tmp_path):
    journal, image, _ = captured
    journal.before_input('click', ('click', 10, 20))
    before = capacity.EvidenceCapacity(tmp_path).load()['bytes']
    successor = recognition.Journal(tmp_path / 'evidence/runtime/resumed')
    successor.frame(image, [], 'NODE_PANEL')
    pool = capacity.EvidenceCapacity(tmp_path)
    assert pool.load()['bytes'] < before
    assert pool.release_for_result(tmp_path / 'evidence/runtime/unrelated') is False
    assert pool.release_for_result(successor.directory) is True
    assert pool.load()['bytes'] == 0
    assert pool.load()['owner']['directory'] == str(journal.directory.relative_to(tmp_path))


def test_result_writer_releases_capacity_but_preserves_unresolved_private_state(captured, tmp_path):
    journal, _, _ = captured
    pending = tmp_path / 'config/user-test-transaction.json'
    pending.parent.mkdir()
    pending.write_bytes(b'{"scope":"scope-test","pending":{"kind":"purchase"}}')
    before = pending.read_bytes()
    journal.before_input('click', ('click', 10, 20))
    recognition.write_loop_result(journal.directory, dict(passed=False, reason='test-end', clicks_sent=0))
    assert capacity.EvidenceCapacity(tmp_path).load()['bytes'] == 0
    assert pending.read_bytes() == before


def test_installed_root_reserves_in_the_containing_project(captured, tmp_path):
    journal, _, frame = captured
    app = tmp_path / 'dist/MaaLimbus'
    app.mkdir(parents=True)
    pool = capacity.EvidenceCapacity(app)
    pool.admit(frame, kind='click', payload=('click', 10, 20))
    assert pool.root == tmp_path
    assert pool.credit.is_relative_to(tmp_path / 'evidence/runtime')
    assert not (app / 'evidence').exists()


def test_linked_pool_path_is_never_followed(captured, tmp_path, monkeypatch):
    _, _, frame = captured
    pool = capacity.EvidenceCapacity(tmp_path)
    original = workspace._linked
    monkeypatch.setattr(workspace, '_linked', lambda p: Path(p) == pool.credit or original(p))
    with pytest.raises(ValueError, match='Linked capture path'):
        pool.admit(frame, kind='click', payload=('click', 10, 20))
    assert not pool.credit.exists()


def test_native_plan_admission_refuses_before_confirming_existing_deployment_intent(tmp_path, monkeypatch):
    """Exercise the actual step and actual retained modal, not a source-text order."""
    from maalimbus.deployment_transaction import DeploymentTransaction
    from maalimbus.storage import write_json
    source = Path(__file__).resolve().parents[1] / 'evidence/runtime/packaged-mirror-20261116-234249/frame-0004.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    assert original['scene'] == 'DEPLOYMENT_RESET'
    picture = source.with_suffix('.png').read_bytes()
    assert hashlib.sha256(picture).hexdigest() == original['image_sha256']
    monkeypatch.setattr(recognition, 'ROOT', tmp_path)
    journal = recognition.Journal(tmp_path / 'evidence/runtime/current')
    record = dict(original, frame='frame-0001')
    before = journal.directory / 'frame-0001.json'
    before.with_suffix('.png').write_bytes(picture)
    write_json(before, record)
    journal.index = 1
    native = Controller()
    device = runner.MaaDevice(native, target_long_side=0, before_input=journal.before_input)
    loop = runner.MirrorRunner(device, settings=dict(interval=0), directory=journal.directory)
    tx = DeploymentTransaction(tmp_path / 'config/user-deployment-transaction.json')
    wanted = [3,4,9,1,7,2,12,5,8,10,11,6]
    inherited = [11,9,3,10,4,8,12,2,5,1,7,6]
    tx.prepare('scope', wanted, (12,12), inherited)
    tx.intent('clear', (12,12))
    private_before = tx.path.read_bytes()
    loop.deployment_transaction = tx
    loop.run_id = 'scope'
    monkeypatch.setattr(loop, '_observe', lambda **kw: record)
    monkeypatch.setattr(runner, 'candidates_of', lambda *a, **kw: ('frame-0001.png', []))
    monkeypatch.setattr(workspace.shutil, 'disk_usage', lambda _root: type('Usage', (), {'free': 100})())
    with pytest.raises(capacity.EvidenceCapacityUnavailable):
        loop.step()
    assert native.sent == []
    assert tx.path.read_bytes() == private_before
    assert not tx.data['pending'].get('confirm_sent')
    assert loop.artifacts['last_step_sent'] is False


def test_capacity_provenance_follows_current_run_in_a_continuous_capture_session(captured, tmp_path):
    journal, _, _ = captured
    from types import SimpleNamespace
    current = SimpleNamespace(run_id='first-scope')
    journal.capacity_scope = 'stale-launch-scope'
    journal.capacity_scope_provider = lambda: current.run_id
    journal.before_input('click', ('click', 10, 20))
    assert capacity.EvidenceCapacity(tmp_path).load()['owner']['scope'] == 'first-scope'
    current.run_id = 'rotated-scope'
    journal.before_input('click', ('click', 10, 20))
    assert capacity.EvidenceCapacity(tmp_path).load()['owner']['scope'] == 'rotated-scope'


def test_unverified_pool_cannot_hide_stop_report_or_be_silently_released(captured, tmp_path):
    journal, _, _ = captured
    journal.before_input('click', ('click', 10, 20))
    pool = capacity.EvidenceCapacity(tmp_path)
    for p in pool.slots:
        p.write_bytes(b'x' * capacity.SLOT_BYTES)
    preserved = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (*pool.slots, pool.credit)}
    native = Controller()
    device = runner.MaaDevice(native, target_long_side=0, before_input=journal.before_input)
    with pytest.raises(capacity.EvidenceCapacityUnavailable):
        device.click(10, 20)
    assert native.sent == []
    path = recognition.write_loop_result(journal.directory,
        dict(passed=False, reason=capacity.EvidenceCapacityUnavailable.reason, clicks_sent=5))
    result = json.loads(path.read_text(encoding='utf-8'))
    assert 'metadata is unverified' in result['evidence_capacity_release_error']
    assert '本次待执行输入未发送' in result['user_message']
    assert result['clicks_sent'] == 5  # Earlier inputs are not relabelled zero.
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in preserved.items())


def test_physical_recheck_does_not_charge_plan_headroom_twice(captured, tmp_path, monkeypatch):
    journal, _, _ = captured
    journal.before_input('plan', ('click', [10,20,30,40]))
    reserved = capacity.EvidenceCapacity(tmp_path).load()['bytes']
    # A valid domain intent used some pre-admitted margin, leaving less than
    # JOURNAL_HEADROOM but still enough to record this attempted native dispatch.
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(tmp_path) + 4096)
    journal.before_input('click', ('click', 20, 30))
    assert capacity.EvidenceCapacity(tmp_path).load()['bytes'] == reserved
    assert workspace.size(tmp_path) <= workspace.BUDGET_BYTES
