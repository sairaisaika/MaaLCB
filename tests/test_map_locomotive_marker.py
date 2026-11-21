"""Locomotive identity needs the flame, body structure and a unique object."""
import cv2
import numpy as np
import pytest

from maalimbus.map_vision import locomotive_marker


def scene():
    image=np.zeros((1080,1920,3),np.uint8)
    add_train(image,600,300)
    return image


def add_train(image,x,y):
    image[y:y+14,x:x+10]=(0,20,240)
    image[y+30:y+42,x-8:x-2]=(0,20,240)
    image[y+30:y+48,x+2:x+14]=(0,170,230)


def test_unique_flame_and_two_body_bands_give_a_bounded_node_anchor():
    image=scene();before=image.copy()
    point=locomotive_marker(image)
    assert point is not None and abs(point[0]-605)<=2 and abs(point[1]-372)<=2
    assert np.array_equal(image,before)


@pytest.mark.parametrize('missing',['flame','outline','body'])
def test_each_required_object_part_is_independently_necessary(missing):
    image=scene()
    if missing=='flame':image[300:314,600:610]=0
    elif missing=='outline':image[330:342,592:598]=0
    else:image[330:348,602:614]=0
    assert locomotive_marker(image) is None


def test_two_eligible_objects_are_ambiguous_instead_of_nearest_to_the_screen_centre():
    image=scene();add_train(image,1000,300)
    assert locomotive_marker(image) is None


@pytest.mark.parametrize('location',[(600,20),(600,960),(1800,300)])
def test_header_footer_and_right_controls_are_not_the_map_party(location):
    image=np.zeros((1080,1920,3),np.uint8);add_train(image,*location)
    assert locomotive_marker(image) is None


def test_reference_width_scaling_preserves_the_same_sprite_identity():
    image=scene();smaller=cv2.resize(image,(1280,720),interpolation=cv2.INTER_NEAREST)
    point=locomotive_marker(smaller)
    assert point is not None and abs(point[0]-403)<=2 and abs(point[1]-248)<=2


def test_flame_cannot_borrow_a_neighbouring_icons_body():
    image=np.zeros((1080,1920,3),np.uint8)
    image[300:314,600:610]=(0,20,240)
    image[340:352,580:586]=(0,20,240)
    image[330:348,581:591]=(0,170,230)
    assert locomotive_marker(image) is None


@pytest.mark.parametrize('relative,expected',[
    ('packaged-mirror-20261117-124654/frame-0071.png',(864,484)),
    ('packaged-mirror-20261117-142233/frame-0013.png',(910,484))])
def test_retained_green_map_currency_badge_is_not_a_second_locomotive(relative,expected):
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'evidence/runtime'/relative
    if not path.exists():pytest.skip('Native floor3 map retained privately')
    image=cv2.imread(str(path));point=locomotive_marker(image)
    assert point is not None and abs(point[0]-expected[0])<=4 and abs(point[1]-expected[1])<=4
    from maalimbus.map_vision import party_point
    assert party_point(image)==point
    # Removing only the independently visible flame cannot preserve this
    # positive result using the currency badge on the next node.
    x,y=expected;image[y-75:y-55,x-12:x+12]=0
    assert locomotive_marker(image) is None


def test_a_flat_glowing_node_edge_is_not_a_flame():
    image=scene();image[300:314,600:610]=0
    image[300:309,596:613]=(0,20,240)
    assert locomotive_marker(image) is None
