"""The map caption read with a full stop or a comma in place of its space is still the map.

Live `pi-20261126-181001` (2026-11-26, the sixth run, floor 1): with a node scrolled under
the caption the reader gave 'Exploring Floor.1' on frame-0044 and 'Exploring Floor,1' on
frame-0055, both at .97. Neither parsed, the page stayed unnamed, and the run ended on
`page_unreadable_after_waiting`. The rows below are retyped from those two frames.
"""
import pytest

from maalimbus.map_vision import map_header
from maalimbus.vision import Text

SIZE = (1920, 1080)


@pytest.mark.parametrize('caption, box, pack, pack_box', [
    ('Exploring Floor.1', (58, 129, 334, 47), 'To be Pierced', (62, 186, 132, 28)),
    ('Exploring Floor,1', (54, 119, 340, 61), 'Tobe Pierced', (66, 190, 126, 22)),
    ('Exploring Floor 1', (56, 125, 334, 55), 'TobePierced', (62, 190, 130, 22)),
])
def test_the_live_captions_name_the_map_and_its_floor(caption, box, pack, pack_box):
    header = map_header([Text(caption, box, .97), Text(pack, pack_box, .99)], SIZE)
    assert header is not None and header.floor == 1 and header.pack == pack


def test_a_separator_does_not_turn_other_text_into_a_map_caption():
    other = [Text('Explorers, Floor 1 and 2', (58, 129, 334, 47), .97), Text('To be Pierced', (62, 186, 132, 28), .99)]
    assert map_header(other, SIZE) is None
    # Without the pack line under it the caption alone is still not a map.
    assert map_header([Text('Exploring Floor.1', (58, 129, 334, 47), .97)], SIZE) is None
