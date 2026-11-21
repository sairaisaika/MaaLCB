"""Retained original pixels, frame-space targets and absent monetary evidence."""
import json
from pathlib import Path

import cv2
import pytest

from maalimbus import star_vision
from maalimbus.grace_vision import conversion_state,observed_board
from maalimbus.native_evidence import bound_frame
from maalimbus.vision import Text

ROOT=Path(__file__).resolve().parents[1]
CAPTURES=ROOT/'evidence/runtime/packaged-mirror-20261116-192008'


def retained(name,side):
    path=CAPTURES/(name+'.json')
    if not path.is_file() or not path.with_suffix('.png').is_file():
        pytest.skip('retained private entry frames are not distributed')
    _,value=bound_frame(path)
    image=cv2.imread(str(path.with_suffix('.png')))
    sy=(side*9//16)/image.shape[0];sx=side/image.shape[1]
    records=[Text(t['text'],tuple(round(v*s) for v,s in zip(t['box'],(sx,sy,sx,sy))),t['score'])
             for t in value['ocr']]
    return cv2.resize(image,(side,side*9//16),interpolation=cv2.INTER_AREA),records


@pytest.mark.parametrize('side',[1280,1920])
def test_real_board_keeps_card_ordinals_prices_and_body_targets(side):
    image,records=retained('frame-0001',side)
    boxes=star_vision.grid(image)
    assert boxes is not None and len(boxes)==10
    board=observed_board(image,records,[2,4,5,7])
    assert board and [board['costs'][i-1] for i in (2,4,5,7)]==[10,20,30,40]
    for index,point in board['points'].items():
        x,y,w,h=boxes[index-1]
        assert x<point[0]<x+w and y<point[1]<y+h*.4
        cx,cy,cw,ch=star_vision.cost_roi(boxes[index-1])
        assert 0<=cx<cx+cw<=side and 0<=cy<cy+ch<=image.shape[0]


@pytest.mark.parametrize('side',[1280,1920])
@pytest.mark.parametrize('name,state,cost',[('frame-0010','checked',70),('frame-0011','unchecked',0)])
def test_real_modal_checkbox_and_cost_stay_independent(side,name,state,cost):
    image,records=retained(name,side)
    folder=ROOT/'assets/resource/base/image/navigation'
    result=conversion_state(image,records,folder)
    assert result['conversion']==state and result['cost']==cost
    x,y,w,h=result['conversion_box']
    assert .54*side<x<x+w<.60*side and .45*image.shape[0]<y<y+h<.56*image.shape[0]
    # Seeing the checkbox alone never proves a numerical conversion amount.
    without=[t for t in records if not .67<t.box[0]/side<.735]
    assert conversion_state(image,without,folder)['cost'] is None


@pytest.mark.parametrize('side',[1280,1920])
def test_missing_price_never_borrows_the_season_cost_table(side):
    image,records=retained('frame-0001',side)
    box=star_vision.cost_roi(star_vision.grid(image)[1]);x,y,w,h=box
    without=[t for t in records if not x<=t.box[0]+t.box[2]/2<=x+w
             or not y<=t.box[1]+t.box[3]/2<=y+h]
    assert observed_board(image,without,[2]) is None
