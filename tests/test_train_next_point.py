"""The white intermediate destination must not be skipped for the red boss."""
from __future__ import annotations

import json
import pathlib
import sys

import cv2
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import map_vision  # noqa: E402

FIXTURE = ROOT / 'tests' / 'fixtures' / 'frames' / 'map-20261031-154323'


def _frame():
    path = FIXTURE / 'frame-0001.png'
    if not path.is_file():
        pytest.skip('真实地图帧 fixture 不在仓库里')
    return cv2.imread(str(path))


def test_the_train_icon_gives_the_next_tile():
    image = _frame()
    party = map_vision.party_point(image)
    assert party is not None
    nxt = map_vision.train_next_point(image, party)
    assert nxt is not None, '这一帧有车头图标，必须给出下一格'
    # Native pixels show a white intermediate node(1056,255) between the
    # party and red boss(1247,255). The old annotation named the boss and
    # therefore demanded a two-node skip. Keep a tighter one-node tolerance.
    assert abs(nxt[0] - 1056) <= 60 and abs(nxt[1] - 255) <= 60, nxt
    # 方向必须是“我方的右侧”，否则等于把队伍往回带
    assert nxt[0] > party[0]


def test_no_party_means_no_next_tile():
    assert map_vision.train_next_point(_frame(), None) is None


def test_destination_icon_fallback_is_not_extrapolated_a_second_time():
    image=_frame();party=map_vision.party_point(image)
    image[230:280,925:990]=0  # erase only the mid-edge chevrons, not either node
    assert map_vision.chevron_glyph_pairs(image)==[]
    point=map_vision.train_next_point(image,party)
    assert point is not None and abs(point[0]-1056)<=60 and abs(point[1]-255)<=60
    # The same native target cannot become eligible by changing reader paths.
    assert map_vision.train_next_point(image,party,previous=point,side=192) is None


def test_a_band_without_an_icon_answers_none():
    image = _frame()
    party = map_vision.party_point(image)
    # 把右侧整条带涂黑，模拟“这一帧没有车头图标可选”
    blanked = image.copy()
    blanked[:, party[0] + 40:] = 0
    assert map_vision.train_next_point(blanked, party) is None
