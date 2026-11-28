"""Every box a frame record carries is whole pixels inside the image.

Live pi-20261128-072916: the faint floor-name read scaled its box from 1280x720 into
1920x1080 and kept the fractions ([28.5, 259.5, 303.0, 88.5]). On the first map frame
the run closed the previous shop visit, the shop transaction's strict reader refused
the frame with "Invalid shop OCR record", and the run ended on its first step.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
import recognition  # noqa: E402
from maalimbus import shop_transaction  # noqa: E402
from maalimbus.vision import Text  # noqa: E402


def test_a_fractional_box_is_written_as_whole_pixels_and_the_shop_reader_accepts_the_frame(tmp_path):
    journal = recognition.Journal(tmp_path)
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    journal.frame(image, [Text('Tinmnekiliing Time', (28.5, 259.5, 303.0, 88.5), .81165),
                          Text('Exploring Floor 4', (60, 130, 350, 40), .98)], 'MAP')
    record = json.loads((tmp_path / 'frame-0001.json').read_text(encoding='utf-8'))
    assert [row['box'] for row in record['ocr']] == [[28, 260, 303, 88], [60, 130, 350, 40]]
    found = shop_transaction._frame(tmp_path / 'frame-0001.json')
    assert found[0]['scene'] == 'MAP'


def test_a_box_is_kept_inside_the_image():
    assert recognition.frame_box((1900.6, 1070, 50, 30), 1920, 1080) == [1901, 1070, 19, 10]
    assert recognition.frame_box((-3, -1, 10, 10), 1920, 1080) == [0, 0, 10, 10]
