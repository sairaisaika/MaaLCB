from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from maalimbus.shop_native import repair_replacement_evidence
from maalimbus.shop_skill_policy import propose_replacement
from maalimbus.shop_skill_vision import identity_skill_search, is_skill_service, named_skill_services, read_replacement_modal
from maalimbus.shop_transaction import ShopTransaction, _frame
from maalimbus.vision import Text
from maalimbus.pre_battle_identity import deployment_roles, submitted_identities, submitted_identity


@pytest.mark.parametrize(('heading', 'label', 'sinner'), [
    ('Shop', 'Replace Heathciffs Skill', 'Heathcliff'),
    ('Super Shop', "Replace Ryōshü's Skill", 'Ryoshu'),
    ('Shop', "Replace Ryðshü's Skill", 'Ryoshu'),
    ('Super Shop', 'Replace Meursault s Skill', 'Meursault'),
    ('Super Shop', "Replace Ryōshuux's Skill", None),
])
def test_skill_service_uses_measured_owner_spelling_without_a_shelf_price(heading, label, sinner):
    rows = [Text(heading, (190, 110, 130, 30), .99), Text(label, (580, 330, 180, 20), .99)]
    assert is_skill_service(label)
    services = named_skill_services(rows, (1280, 720))
    assert [offer['sinner'] for offer in services] == ([sinner] if sinner else [])
    assert all('price' not in offer for offer in services)


@pytest.mark.parametrize(('run', 'frame', 'sinner'), [
    ('packaged-mirror-20261117-010749', 'frame-0063', 'Heathcliff'),
    ('packaged-mirror-20261120-033906', 'frame-0219', 'Ryoshu'),
])
def test_original_shelf_png_enables_named_service_read(run, frame, sinner):
    from maalimbus.native_evidence import frame_reference

    path = Path(__file__).resolve().parents[1] / 'evidence/runtime' / run / f'{frame}.json'
    if not path.exists() or not path.with_suffix('.png').exists():
        pytest.skip('Original private shelf capture is not present')
    _, record = frame_reference(path)
    assert record['scene'] == 'SHOP'
    assert sinner in {offer['sinner'] for offer in named_skill_services(record['ocr'], record['size'])}


@pytest.mark.parametrize(('run', 'frame'), [
    ('packaged-mirror-20261119-222048', 'frame-0011'),
    ('packaged-mirror-20261120-033906', 'frame-0219'),
])
def test_generic_skill_search_reads_its_own_starlight_glyph_from_retained_shelf(run, frame):
    import cv2
    from maalimbus.native_evidence import frame_reference
    from maalimbus.runner import shop_state

    path = Path(__file__).resolve().parents[1] / 'evidence/runtime' / run / f'{frame}.json'
    if not path.exists() or not path.with_suffix('.png').exists():
        pytest.skip('Original private shelf capture is not present')
    _, record = frame_reference(path)
    pixels = cv2.imread(str(path.with_suffix('.png')))
    observed = identity_skill_search(record['ocr'], pixels)
    assert observed['currency'] == 'starlight' and observed['quote_read'] is False
    assert shop_state(record, wanted=['ID Skill Search'])['buy'] is None
    x,y,w,h = observed['badge_roi']
    muted = pixels.copy()
    muted[y:y+h, x:x+w] = 0
    assert identity_skill_search(record['ocr'], muted)['currency'] == 'unresolved'


@pytest.fixture
def modal_rows():
    return [
        Text("Replace Don Quixote's Skill", (208, 117, 360, 33), 1),
        Text('Skills Owned', (608, 105, 81, 22), .99),
        Text('SKILL1x3 SKILL2x2 SKILL3X1', (612, 129, 224, 23), .97),
        Text('2283', (1004, 117, 72, 41), 1),
        Text('Pay a moderate price.', (186, 187, 198, 23), .98),
        Text('Pay a large sum.', (520, 183, 181, 31), .99),
        Text('Pay a tremendous price.', (837, 186, 199, 25), .97),
        Text('75', (766, 205, 20, 20), 1),
        Text('120', (1054, 202, 60, 25), .99),
        Text('Cancel', (482, 528, 78, 27), 1),
        Text('Confirm', (773, 529, 83, 24), 1),
    ]


@pytest.mark.parametrize('scale', [1, 2])
def test_reads_each_quote_without_interpolating_a_missing_price(modal_rows, scale):
    rows = [Text(row.text, tuple(n * scale for n in row.box), row.score) for row in modal_rows]
    modal = read_replacement_modal(rows, (1280 * scale, 720 * scale))
    assert (modal.sinner, modal.counts, modal.balance) == ('Don Quixote', (3, 2, 1), 2283)
    assert [(q.from_tier, q.to_tier, q.price) for q in modal.quotes] == [
        (1, 2, None), (2, 3, 75), (1, 3, 120),
    ]


def test_ambiguous_badge_does_not_borrow_a_price_from_another_card(modal_rows):
    modal_rows.extend([Text('45', (420, 205, 20, 20), 1), Text('90', (756, 205, 20, 20), 1)])
    modal = read_replacement_modal(modal_rows, (1280, 720))
    assert [quote.price for quote in modal.quotes] == [45, None, 120]


@pytest.mark.parametrize('missing', ['Skills Owned', 'Pay a large sum.', 'Confirm'])
def test_requires_the_measured_chooser_layout(modal_rows, missing):
    rows = [row for row in modal_rows if row.text != missing]
    assert read_replacement_modal(rows, (1280, 720)) is None


@pytest.mark.parametrize('column, price', [(0, 45), (1, 75), (2, 120)])
@pytest.mark.parametrize('agrees', [True, False])
def test_native_badge_crops_must_agree(modal_rows, column, price, agrees):
    modal_rows.append(Text('45', (440, 205, 20, 20), 1))
    modal_rows = [row for row in modal_rows if row.text != str(price)] + tier_rows()
    answers = iter([str(price), str(price if agrees else price + 1)])

    def native(_kind, _params, _image):
        return SimpleNamespace(hit=True, filtered_results=[SimpleNamespace(text=next(answers), score=.99)])

    original = modal_rows[:]
    rows, proof = repair_replacement_evidence(native, np.zeros((720, 1280, 3), dtype=np.uint8), modal_rows)
    assert modal_rows == original
    assert len(proof) == 2
    expected = [45, 75, 120]
    expected[column] = price if agrees else None
    assert [quote.price for quote in read_replacement_modal(rows, (1280, 720)).quotes] == expected


def test_does_not_replace_two_conflicting_price_badges(modal_rows):
    modal_rows.extend([Text('45', (440, 205, 20, 20), 1),
                      Text('90', (756, 205, 20, 20), 1), *tier_rows()])

    def native(*args):
        pytest.fail('Do not replace a conflicting printed price')

    rows, proof = repair_replacement_evidence(native, np.zeros((720, 1280, 3), dtype=np.uint8), modal_rows)
    assert not proof
    assert [quote.price for quote in read_replacement_modal(rows, (1280, 720)).quotes] == [45, None, 120]


def tier_rows():
    return [Text(f'SKILL {tier}', (361 + 326 * column, y, 68, 27), 1)
            for column, tiers in enumerate(((1, 2), (2, 3), (1, 3)))
            for y, tier in zip((239, 383), tiers)]


def test_layout_does_not_override_a_conflicting_printed_tier(modal_rows):
    badges = tier_rows()
    badges[2] = Text('SKILL 1', badges[2].box, .99)
    modal = read_replacement_modal(modal_rows + badges, (1280, 720))
    assert [q.tiers_verified for q in modal.quotes] == [True, False, True]


@pytest.mark.parametrize('second_read, verified', [('SKILL3', True), ('SKILL 2', False)])
def test_native_tier_crops_must_agree(modal_rows, second_read, verified):
    modal_rows.extend(tier_rows()[:-1])
    modal_rows.append(Text('45', (420, 205, 20, 20), 1))
    answers = iter(['SKILL 3', second_read])

    def native(_kind, _params, _image):
        return SimpleNamespace(hit=True, filtered_results=[SimpleNamespace(text=next(answers), score=.99)])

    rows, proof = repair_replacement_evidence(native, np.zeros((720, 1280, 3), dtype=np.uint8), modal_rows)
    assert len(proof) == 2
    assert read_replacement_modal(rows, (1280, 720)).quotes[2].tiers_verified is verified


@pytest.fixture
def proven_modal(modal_rows):
    return read_replacement_modal(modal_rows + tier_rows(), (1280, 720))


def test_chooses_the_cheapest_proven_gain_and_predicts_exact_receipt(proven_modal):
    choice = propose_replacement(proven_modal, 'keep_one_each', 500)
    assert (choice.quote.from_tier, choice.quote.to_tier) == (2, 3)
    assert (choice.counts_after, choice.coins_after) == ((3, 1, 2), 2208)


def test_only_keep_one_s2_permits_replacing_the_last_s1(proven_modal):
    modal = replace(proven_modal, counts=(1, 1, 4))
    assert propose_replacement(modal, 'keep_one_each', 500) is None
    choice = propose_replacement(modal, 'keep_one_s2', 500)
    assert (choice.counts_after, choice.coins_after) == ((0, 1, 5), 2163)


def test_disabled_reserve_and_missing_tier_block_the_proposal(proven_modal):
    assert propose_replacement(proven_modal, 'off', 0) is None
    assert propose_replacement(proven_modal, 'keep_one_each', 2209) is None
    quotes = tuple(replace(q, tier_badges=(None, None)) for q in proven_modal.quotes)
    assert propose_replacement(replace(proven_modal, quotes=quotes), 'keep_one_s2', 500) is None


def test_deployment_binding_uses_printed_position_and_requires_exact_caption():
    rows = [dict(grid_slot=2, sinner='Don Quixote', sinner_index=3, identity_id=10315, method='exact_alias'),
            dict(grid_slot=4, sinner='Meursault', sinner_index=5, identity_id=10512, method='unique_subsequence')]
    order = [3, 5, 4]
    badges = [None, None, 1, None, 2] + [None] * 7
    roles = {2: 'frontline', 4: 'backup'}
    assert submitted_identities(rows, order, badges, roles) == [
        dict(position=1, grid_slot=2, role='frontline', sinner='Don Quixote', identity_id=10315)]
    badges[3] = 1
    assert not submitted_identities(rows, order, badges, roles)
    badges[3], badges[2] = None, 0
    assert not submitted_identities(rows, order, badges, roles)


def test_frontline_reads_the_printed_role_and_refuses_a_conflicting_strip():
    selected = dict(text='SELECTED', box=[780, 357, 120, 36], score=.999)
    backup = dict(text='BACKUP', box=[1184, 353, 104, 42], score=.999)
    header = dict(text='Backup Deployed 5/5', box=[830, 168, 236, 40], score=.999)
    assert deployment_roles([selected, backup, header]) == {2: 'frontline', 4: 'backup'}
    assert deployment_roles([selected, dict(selected, text='BACKUP'), backup]) == {4: 'backup'}


@pytest.mark.parametrize('size', [(1920, 1080), (1280, 720)])
def test_shop_identity_requires_current_scope_settled_submission_and_original_bytes(tmp_path, size):
    import hashlib
    import json
    import cv2
    from maalimbus.native_evidence import frame_reference

    def retained_frame(index, scene, ocr):
        frame = tmp_path / f'frame-{index:04}.json'
        image = frame.with_suffix('.png')
        assert cv2.imwrite(str(image), np.full((size[1], size[0], 3), index, dtype=np.uint8))
        frame.write_text(json.dumps(dict(scene=scene, size=size, ocr=ocr,
                    image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())), encoding='utf-8')
        proof, _ = frame_reference(frame)
        return dict(record=proof.record_path, json_sha256=proof.json_sha256, png_sha256=proof.png_sha256)

    box = [round(n * size[0] / 1920) for n in (780, 357, 120, 36)]
    before = retained_frame(1, 'PRE_BATTLE_TEAM', [dict(text='SELECTED', box=box, score=.999)])
    battle = retained_frame(2, 'BATTLE_HUD', [])
    identity = dict(position=1, grid_slot=2, role='frontline', sinner='Don Quixote', identity_id=10315)
    deployment = dict(scope='current', submitted=True,
                      identity_witness=dict(before, roster=[identity], battle_hud=battle))
    assert submitted_identity(deployment, 'current', 'Don Quixote') == identity
    assert submitted_identity(deployment, 'previous', 'Don Quixote') is None
    assert submitted_identity(dict(deployment, submitted=False), 'current', 'Don Quixote') is None
    frame = tmp_path / 'frame-0002.json'
    frame.write_bytes(frame.read_bytes() + b' ')
    assert submitted_identity(deployment, 'current', 'Don Quixote') is None


@pytest.fixture
def reserved_skill(tmp_path, modal_rows):
    import hashlib
    from maalimbus.storage import write_json

    def capture(index, rows, scene='UNKNOWN_DIALOG', utc=None):
        path = tmp_path / f'frame-{index:04}.json'
        image = bytes([index])
        path.with_suffix('.png').write_bytes(image)
        write_json(path, dict(scene=scene, size=[1280, 720], utc=utc or f'2026-11-20T06:00:0{index}+00:00',
            ocr=[dict(text=row.text, box=list(row.box), score=row.score) for row in rows],
            image_sha256=hashlib.sha256(image).hexdigest()))
        return path

    shelf = _frame(capture(1, [], 'SHOP'))[3]
    rows = modal_rows + tier_rows()
    chooser_path = capture(2, rows)
    chooser = _frame(chooser_path)[3]
    tx_path = tmp_path / 'shop.json'
    write_json(tx_path, dict(version=1, scope='current', current_visit='1', bought=[],
        visits={'1': dict(entry=shelf, refreshes=0, closed=False)}, pending=dict(
            kind='skill_replacement', stage='skill_confirm_intent', scope='current', visit='1',
            question=chooser, before=shelf, shelf=[], price=75, coins=2283,
            skill=dict(sinner='Don Quixote', mode='keep_one_each', reserve_coins=500, from_tier=2))))
    return ShopTransaction(tx_path), capture, chooser_path, rows


def test_proven_skill_receipt_books_once_and_stays_out_of_gift_receipts(reserved_skill):
    tx, capture, _, rows = reserved_skill
    updated = {'2283': '2208', 'SKILL1x3 SKILL2x2 SKILL3X1': 'SKILL1x3 SKILL2x1 SKILL3X2'}
    after = capture(3, [replace(row, text=updated.get(row.text, row.text)) for row in rows])
    receipt = tx.reconcile_skill_replacement('current', '1', after)
    restarted = ShopTransaction(tx.path)
    assert restarted.data['pending'] is None and restarted.bought_names == []
    assert restarted.data['visits']['1']['skill_receipts'] == [receipt]
    assert (receipt['counts_after'], receipt['coins_after']) == ([3, 1, 2], 2208)
    with pytest.raises(ValueError, match='pending'):
        restarted.reconcile_skill_replacement('current', '1', after)


def test_named_skill_opener_is_one_per_visit_and_cannot_confirm_as_a_gift(reserved_skill, monkeypatch):
    from maalimbus import pre_battle_identity
    from maalimbus.shop_skill_policy import choose_skill_service
    from maalimbus.shop_skill_vision import named_skill_services
    from maalimbus.window import plan_step

    _, capture, _, modal_rows = reserved_skill
    rows = [Text('Super Shop', (193, 111, 123, 30), .99), Text('100', (567, 120, 53, 23), .99),
            Text('20', (610, 306, 20, 20), .99), Text('Oracle', (567, 329, 107, 20), .99),
            Text('77', (752, 307, 40, 21), .95), Text("Replace Ryōshū's Skill", (710, 330, 135, 18), .99)]
    before = capture(4, rows, 'SHOP')
    tx = ShopTransaction(before.parent / 'opener.json')
    tx.begin_visit('scope', '1', before)
    deployment = dict(submitted=True)
    monkeypatch.setattr(pre_battle_identity, 'submitted_identity', lambda value, scope, sinner:
        dict(role='frontline', identity_id=10416) if value == deployment and scope == 'scope' and sinner == 'Ryoshu' else None)

    services = named_skill_services(rows, (1280, 720))
    buy = choose_skill_service(services, 100, 20, deployment, 'scope', (), ())
    plan = plan_step('SHOP', shop=dict(buy=buy, currency=100))
    assert plan['reason'] == 'open_verified_frontline_skill_service'
    assert tx.reserve_skill_service('scope', '1', plan['detail']['name'], before,
        'keep_one_each', 20, deployment) == plan['target']
    restarted = ShopTransaction(tx.path)
    assert restarted.data['pending']['skill']['sinner'] == 'Ryoshu' and not restarted.bought_names
    assert 'price' not in restarted.data['pending']
    attempted = restarted.data['visits']['1']['skill_service_attempts']
    assert choose_skill_service(services, 100, 20, deployment, 'scope', attempted, ()) is None
    with pytest.raises(ValueError, match='Matching pending shop action'):
        restarted.reserve_confirm('scope', '1', capture(5, [], 'SHOP_PURCHASE'))
    changes = {"Replace Don Quixote's Skill":plan['detail']['name'], '2283':'100'}
    chooser_rows = [replace(row,text=changes.get(row.text,row.text)) for row in modal_rows]
    modal = capture(6, chooser_rows)
    assert restarted.reconcile_skill_service('scope', '1', modal) == 'chooser'
    reading = read_replacement_modal(chooser_rows,(1280,720))
    choice = propose_replacement(reading,'keep_one_each',20)
    selection_plan = plan_step('UNKNOWN_DIALOG',controls={'shop.skill_choice':list(choice.quote.select_box),
                                                          'shop.skill_cancel':list(reading.cancel_box)})
    assert selection_plan['reason'] == 'select_proven_shop_skill_replacement'
    assert selection_plan['control_id'] == 'shop.skill_choice'
    selection = restarted.reserve_skill_selection('scope','1',modal,'keep_one_each',20,deployment,
                                                  selection_plan['target'])
    assert (selection['from_tier'],selection['price'],selection['coins_after']) == (2,75,25)
    restarted = ShopTransaction(tx.path)
    with pytest.raises(ValueError,match='only once'):
        restarted.reserve_skill_selection('scope','1',modal,'keep_one_each',20,deployment,selection_plan['target'])
    with pytest.raises(ValueError,match='independent skill selection successor'):
        restarted.reconcile_skill_service('scope','1',modal)
    unchanged = tx.path.read_bytes()
    wrong_counts = [
        replace(row, text='SKILL1x2 SKILL2x2 SKILL3X2')
        if row.text == 'SKILL1x3 SKILL2x2 SKILL3X1' else row
        for row in chooser_rows
    ]
    wrong_chooser = capture(9, wrong_counts)
    with pytest.raises(ValueError, match='Unchanged skill counts'):
        restarted.reserve_skill_service_cancel('scope', '1', wrong_chooser, reading.cancel_box)
    with pytest.raises(ValueError, match='unspent Cancel'):
        restarted.reconcile_skill_service('scope', '1', capture(8, rows, 'SHOP'))
    assert tx.path.read_bytes() == unchanged
    after_selection = capture(7, chooser_rows)
    assert restarted.reconcile_skill_service('scope','1',after_selection) == 'chooser'
    cancel_plan = plan_step('UNKNOWN_DIALOG', controls={'shop.skill_cancel':list(reading.cancel_box)})
    assert cancel_plan['control_id'] == 'shop.skill_cancel'
    assert cancel_plan['expect'] == ['SHOP']
    restarted.reserve_skill_service_cancel('scope', '1', after_selection, cancel_plan['target'])
    restarted = ShopTransaction(tx.path)
    with pytest.raises(ValueError):
        restarted.reserve_skill_service_cancel('scope', '1', after_selection, [482, 528, 78, 27])
    after_cancel_intent = tx.path.read_bytes()
    earlier_shelf = capture(9, rows, 'SHOP', utc='2026-11-20T06:00:06.200+00:00')
    with pytest.raises(ValueError, match='must follow the reserved capture'):
        restarted.reconcile_skill_service('scope', '1', earlier_shelf)
    assert tx.path.read_bytes() == after_cancel_intent
    unspent = capture(8, rows, 'SHOP')
    assert restarted.reconcile_skill_service('scope', '1', unspent) == 'shelf'
    assert not restarted.data['pending'] and not restarted.bought_names


@pytest.mark.parametrize('failure', ['wrong_coins', 'wrong_counts', 'stale', 'earlier', 'wrong_sinner', 'edited_before'])
def test_uncertain_skill_receipt_and_generic_retirement_preserve_pending(reserved_skill, failure):
    tx, capture, chooser, rows = reserved_skill
    updated = {'2283': '2208' if failure != 'wrong_coins' else '2209',
               'SKILL1x3 SKILL2x2 SKILL3X1': 'SKILL1x3 SKILL2x1 SKILL3X2' if failure != 'wrong_counts' else 'SKILL1x2 SKILL2x2 SKILL3X2'}
    if failure == 'wrong_sinner':
        updated["Replace Don Quixote's Skill"] = "Replace Gregor's Skill"
    after = chooser if failure == 'stale' else capture(3, [replace(row, text=updated.get(row.text, row.text)) for row in rows],
        utc='2026-11-20T06:00:01+00:00' if failure == 'earlier' else None)
    if failure == 'edited_before':
        chooser.write_bytes(chooser.read_bytes() + b' ')
    original = tx.path.read_bytes()
    with pytest.raises(ValueError):
        tx.reconcile_skill_replacement('current', '1', after)
    with pytest.raises(ValueError, match='preserve pending'):
        tx.retire_pending('current', '1')
    assert tx.path.read_bytes() == original
