import json
from pathlib import Path

import numpy as np
import pytest

from maalimbus import anchors

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT/'assets'/'resource'/'base'/'anchors.json'


def page(identity, controls=()):
    return {'id': 'p', 'title': 'page', 'identity': list(identity), 'controls': list(controls)}


def registry(identity, controls=(), reference_width=1280):
    return {'version': 1, 'reference_width': reference_width,
            'pages': [page(identity, controls)]}


def observation(records, sha='sha-a', size=(1920, 1080)):
    return {'ocr': records, 'image_sha256': sha, 'size': list(size)}


@pytest.mark.parametrize('duplicates', [False, True])
def test_mirror_entry_descriptor_reads_this_capture_and_keeps_historical_geometry_separate(duplicates):
    from maalimbus.vision import Text, classify

    locale = json.loads((ROOT / 'assets/resource/en/locale.json').read_bytes())
    ocr = [dict(text='Exploring:', box=[1354, 216, 108, 34], score=.99),
           dict(text='Enter', box=[1610, 719, 104, 43], score=.99)]
    if duplicates:
        ocr.append(dict(text='Enter', box=[1500, 710, 100, 41], score=.98))
    scene = classify([Text(r['text'], tuple(r['box']), r['score']) for r in ocr], locale, (1920, 1080))
    assert scene == 'MIRROR_ENTRY'
    record = dict(observation(ocr), scene=scene,
                  frame_ref=dict(frame_id='frame-0002', png_sha256='a' * 64, size=[1920, 1080]))
    result = anchors.describe_page(anchors.load(REGISTRY), record, locale)
    components = {item['id']: item for item in result['components']}
    assert result['page'] == scene and result['owner'] == 'runner'
    assert result['image_sha256'] == record['frame_ref']['png_sha256']
    assert components['entry.status']['box'] == [1354, 216, 108, 34]
    assert components['entry.before_entry_tab']['state'] == 'unresolved'
    enter = components['entry.enter_button']
    if duplicates:
        assert enter['state'] == 'ambiguous' and enter['candidates'] == 2 and 'box' not in enter
    else:
        assert enter['state'] == 'observed' and enter['box'] == [1610, 719, 104, 43]


def test_missing_component_catalog_keeps_the_producer_page_name():
    record = dict(scene='UNKNOWN', frame_ref=dict(frame_id='frame-0001', png_sha256='b' * 64))
    result = anchors.describe_page(dict(pages=[]), record, {})
    assert result['page'] == 'UNKNOWN' and result['owner'] == 'wait'
    assert result['catalogued'] is False and result['components'] == []


def test_map_pack_component_uses_the_native_pack_box_not_the_floor_caption():
    metadata = dict(scene='MAP', floor=3, pack='Dizzying Waves',
                    header_box=[60,131,338,47], pack_box=[64,193,160,20],
                    frame_ref=dict(frame_id='frame-0012', png_sha256='c' * 64))
    record = dict(observation([dict(text='Exploring Floor 3', box=metadata['header_box'], score=.99)]),
                  **metadata)
    components = {i['id']:i for i in anchors.describe_page(anchors.load(REGISTRY), record, {})['components']}
    assert components['map.floor']['value'] == 3
    assert components['map.pack_name']['box'] == metadata['pack_box']
    assert components['map.pack_name']['value'] == 'Dizzying Waves'


def text(value, box, score=.99):
    return {'text': value, 'box': list(box), 'score': score}


def ocr_anchor(anchor_id='a.one', pattern='^Enter$', roi=(.82, .68, .95, .80), threshold=.85):
    return {'id': anchor_id, 'kind': 'ocr', 'pattern': pattern, 'roi': list(roi),
            'threshold': threshold}


def test_shipped_registry_files_validate():
    loaded = anchors.load(REGISTRY)
    ids = [entry['id'] for entry in loaded['pages']]
    assert ids == ['map', 'node_panel', 'pre_battle_team', 'battle_hud', 'battle_tip',
                   'battle_result', 'battle_victory', 'battle_defeat', 'run_claim', 'run_reward',
                   'run_reward_confirm', 'run_reward_bonus', 'home',
                   'drive', 'before_entry', 'tutorial',
                   'mirror_entry', 'entry_confirm', 'resume_dialog', 'window_reset', 'reward_card',
                   'shop', 'shop_leave', 'gift_get', 'gift_pick', 'gift_warning',
                   'theme_packs', 'cutscene', 'event_choice', 'event_check',
                   'event_check_result', 'event_check_ready', 'deployment',
                   'event_result', 'event_result_ready', 'dungeon_team',
                   'level_warning', 'star_graces', 'star_confirm', 'initial_gifts',
                   'gift_search', 'gift_search_forgo', 'ego_gift_popup',
                   'expired_session', 'pass_level_up']
    assert loaded['reference_width'] == 1280
    assert loaded['pending'], 'the registry must keep naming what is not proven yet'


def test_validate_rejects_a_geometry_anchor_without_proof():
    bad = registry(
        [{'id': 'a.bad', 'kind': 'geometry', 'roi': [0, 0, 1, 1]}])
    with pytest.raises(ValueError, match='verified_on'):
        anchors.validate(bad)


def test_validate_rejects_an_invalid_pattern():
    bad = registry([{'id': 'a.bad', 'kind': 'ocr', 'pattern': '(', 'roi': [0, 0, 1, 1]}])
    with pytest.raises(ValueError, match='invalid pattern'):
        anchors.validate(bad)


def test_ocr_anchor_hits_inside_its_roi_and_misses_outside():
    registry_ = registry([ocr_anchor()])
    inside = observation([text('Enter', (1668, 780, 124, 63))])
    report = anchors.evaluate(registry_, inside)
    assert report['pages'][0]['identity_ok'] is True
    assert report['pages'][0]['identity'][0]['observed']['box'] == [1668, 780, 124, 63]
    assert anchors.failures(report) == []

    outside = observation([text('Enter', (200, 200, 100, 40))])
    report = anchors.evaluate(registry_, outside)
    assert report['pages'][0]['identity_ok'] is False
    assert anchors.failures(report)[0][1] == 'a.one'


def test_geometry_is_proven_only_on_its_own_frame():
    anchor = {'id': 'a.button', 'kind': 'geometry',
              'verified_on': {'sha256': 'sha-a', 'box': [1674, 859, 144, 44],
                              'source': 'team_page_battle.py'}}
    registry_ = registry([ocr_anchor()], [anchor])
    same = anchors.evaluate(registry_, observation([text('Enter', (1668, 780, 124, 63))]))
    control = same['pages'][0]['controls'][0]
    assert control['hit'] is True
    assert control['observed']['box'] == [1674, 859, 144, 44]

    other = anchors.evaluate(registry_, observation([text('Enter', (1668, 780, 124, 63))],
                                                    sha='sha-b'))
    stale = other['pages'][0]['controls'][0]
    assert stale['hit'] is False and stale['stale'] is True
    assert anchors.failures(other, require_geometry=True)


def test_resolve_evidence_reads_the_referenced_frame(tmp_path):
    frame = tmp_path/'frame-0001.json'
    frame.write_text(json.dumps({'image_sha256': 'sha-from-file'}), encoding='utf-8')
    registry_ = registry([ocr_anchor()], [{'id': 'a.g', 'kind': 'geometry',
                                           'verified_on': {'frame': 'frame-0001.json',
                                                           'box': [1, 2, 3, 4]}}])
    anchors.resolve_evidence(registry_, tmp_path)
    assert registry_['pages'][0]['controls'][0]['verified_on']['sha256'] == 'sha-from-file'
    report = anchors.evaluate(registry_, observation([text('Enter', (1668, 780, 124, 63))],
                                                     sha='sha-from-file'))
    assert report['pages'][0]['controls'][0]['hit'] is True


def test_template_anchor_scales_a_reference_width_template(tmp_path):
    cv2 = pytest.importorskip('cv2')
    reference = np.random.default_rng(0).integers(0, 255, (90, 160), dtype=np.uint8)
    device = cv2.resize(reference, (320, 180), interpolation=cv2.INTER_NEAREST)
    template_dir = tmp_path/'templates'/'image'
    template_dir.mkdir(parents=True)
    assert cv2.imwrite(str(tmp_path/'device.png'), device)
    assert cv2.imwrite(str(template_dir/'patch.png'), reference[30:60, 40:80])

    anchor = {'id': 'a.glyph', 'kind': 'template', 'template': 'image/patch.png',
              'roi': [.25, .30, .55, .72], 'threshold': .8}
    registry_ = registry([anchor], reference_width=160)
    report = anchors.evaluate(registry_, observation([], size=(320, 180)),
                              image_path=tmp_path/'device.png', template_root=tmp_path/'templates')
    result = report['pages'][0]['identity'][0]
    assert result['hit'] is True, result
    assert result['observed']['box'] == [80, 60, 80, 60]

    without_image = anchors.evaluate(registry_, observation([], size=(320, 180)))
    assert without_image['pages'][0]['identity'][0]['hit'] is None


def test_template_anchor_reports_a_missing_template(tmp_path):
    cv2 = pytest.importorskip('cv2')
    image = tmp_path/'device.png'
    assert cv2.imwrite(str(image), np.zeros((180, 320), dtype=np.uint8))
    anchor = {'id': 'a.gone', 'kind': 'template', 'template': 'image/absent.png',
              'roi': [.25, .30, .55, .72]}
    registry_ = registry([anchor], reference_width=160)
    report = anchors.evaluate(registry_, observation([], size=(320, 180)),
                              image_path=image, template_root=tmp_path)
    result = report['pages'][0]['identity'][0]
    assert result['hit'] is None
    assert 'missing' in result['reason']
