"""Victory caption classifier contract, separate from retained integration proof.

`BATTLE_RESULT` is consumed by the pipeline (`PostBattleObserve` in
`assets/resource/base/pipeline/mirror.json`) and was, until now, only ever an
expected successor in `window.py` -- nothing produced it. These cases hold the
producer to the measured caption geometry, including the negative control. The
isolated text fixtures below are not live screenshots. The optional real-frame
verifier requires every historical JSON/PNG pair before claiming integration.
"""

import json
from pathlib import Path

from maalimbus.vision import Text, classify

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / 'assets' / 'resource'
FRAMES = ROOT / 'evidence' / 'runtime' / 'window-20261006-105647'
FRAME_NAMES = ('frame-0066', 'frame-0067')


def retained_victory_preflight(directory=FRAMES):
    """Availability of the complete real-frame pair; never infer missing evidence."""
    required = [Path(directory) / (name + suffix)
                for name in FRAME_NAMES for suffix in ('.json', '.png')]
    missing = [str(path) for path in required if not path.is_file()]
    return dict(available=not missing, required=[str(path) for path in required], missing=missing)


def verify_retained_victory_frames(directory=FRAMES):
    """Explicit retained integration entry; an incomplete archive fails preflight."""
    check = retained_victory_preflight(directory)
    if not check['available']:
        raise FileNotFoundError('Retained victory integration incomplete: ' + ', '.join(check['missing']))
    import hashlib
    words = json.loads((LOCALES / 'en' / 'locale.json').read_text(encoding='utf-8'))
    for name in FRAME_NAMES:
        path = Path(directory) / (name + '.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        assert hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest() == data['image_sha256']
        records = [Text(t['text'], tuple(t['box']), t['score']) for t in data['ocr']]
        assert classify(records, words, tuple(data['size'])) == 'BATTLE_RESULT', name
        without = [r for r in records if r.text.strip().upper() not in ('VICTORY', 'ICTORY')]
        assert classify(without, words, tuple(data['size'])) != 'BATTLE_RESULT', name
    return dict(verified=True, preflight=check)


def test_the_victory_caption_is_what_names_the_result_screen():
    words = json.loads((LOCALES / 'en' / 'locale.json').read_text(encoding='utf-8'))
    # The caption's first letter is optional: the post-battle story box sits over the V
    # on live evidence/runtime/window-20261007-174525/frame-0159.json, where OCR reads
    # 'ICTORY' and the run stalled as UNKNOWN (see tests/test_vision.py for that frame).
    # The negative control below still removes the whole word, so the branch is still lit
    # by the caption alone.
    assert words['victory'] == '^V?ICTORY$'
    for caption, box, score in (
            ('VICTORY', (732, 432, 470, 213), .999),
            ('VICTORY', (732, 434, 470, 209), 1.0),
            ('ICTORY', (830, 444, 342, 187), .85)):
        records = [Text(caption, box, score)]
        assert classify(records, words, (1920, 1080)) == 'BATTLE_RESULT', caption
        assert classify([], words, (1920, 1080)) != 'BATTLE_RESULT', caption
        assert classify([Text(caption, box, .849)], words, (1920, 1080)) != 'BATTLE_RESULT'
        assert classify([Text(caption, (0, 0, box[2], box[3]), score)],
                        words, (1920, 1080)) != 'BATTLE_RESULT'


def test_retained_integration_requires_every_json_and_png(tmp_path):
    import pytest
    check = retained_victory_preflight(tmp_path)
    assert check['available'] is False
    assert len(check['missing']) == 4
    (tmp_path / 'frame-0066.json').write_text('{}', encoding='utf-8')
    check = retained_victory_preflight(tmp_path)
    assert check['available'] is False and len(check['missing']) == 3
    with pytest.raises(FileNotFoundError, match='integration incomplete'):
        verify_retained_victory_frames(tmp_path)
