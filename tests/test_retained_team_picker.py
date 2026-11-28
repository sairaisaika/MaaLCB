"""The saved-team reader names the team the retained picker frame shows.

The real November16 trace reached Team1 while the old ledger still named Team2: no test
may relabel that entry or credit its STAR_GRACES successor to the old scope. This is a
reader check on a retained frame, not a Maa controller replay.

It used to sit beside graph checks of the pipeline entry chain (`MirrorEnter` ->
`MirrorEntryConfirm` -> `MirrorTeamReady`). The runner has not followed that chain since
2026-11-19 and its nodes were removed on 2026-11-27; the reader is what the runner uses.
"""
import hashlib
import json
from pathlib import Path

import pytest

from maalimbus.team_vision import selected_saved_team
from maalimbus.vision import Text


ROOT = Path(__file__).resolve().parents[1]


def test_retained_picker_names_team_one_and_never_team_two():
    # Retained integration preflight: all files and bytes must exist to use this
    # observation. This is reader evidence, not permission to re-send Confirm.
    path = ROOT / 'evidence' / 'runtime' / ('packaged-mirror-'+'20261116-132550') / 'frame-0014.json'
    png = path.with_suffix('.png')
    if not (path.is_file() and png.is_file()):
        pytest.skip('Retained November16 Team1 picker JSON/PNG unavailable; reader integration unverified')
    record = json.loads(path.read_text(encoding='utf-8'))
    assert hashlib.sha256(png.read_bytes()).hexdigest() == record['image_sha256']
    assert record['scene'] == 'DUNGEON_TEAM'
    records = [Text(row['text'], tuple(row['box']), row['score']) for row in record['ocr']]
    selected = selected_saved_team(records, record['size'])
    assert selected == 1
    assert selected != 2
