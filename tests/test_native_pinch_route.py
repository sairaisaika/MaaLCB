"""A callback proxy must use Maa's task-owned MultiSwipe, never reverse touch IDs."""
from types import SimpleNamespace

import pytest

from maalimbus import runner
from maalimbus.native_gestures import pinch_node


@pytest.mark.parametrize('identity', ['', None, 'present'])
def test_callback_pinch_uses_one_native_carrier_and_admits_before_dispatch(identity):
    calls=[]
    def forbidden(*args):pytest.fail('reverse touch route must remain unused')
    controller=SimpleNamespace(id=identity,post_touch_down=forbidden,
                               post_touch_move=forbidden,post_touch_up=forbidden)
    def post(entry,override):
        calls.append(('task',entry,override));return SimpleNamespace(done=True,succeeded=True)
    device=runner.MaaDevice(controller,target_long_side=0,
        tasker=SimpleNamespace(post_task=post),before_input=lambda *p:calls.append(('admit',*p)))
    device.pinch((960,540),320,.55,.9)
    assert [row[0] for row in calls]==['admit','task']
    _,entry,override=calls[1]
    assert entry=='MirrorPointPinch'
    node=override[entry]
    assert node['action']=='MultiSwipe' and node['next']==[]
    assert node['swipes']==[
        dict(begin=[640,540,1,1],end=[784,540,1,1],duration=900,starting=0,contact=0),
        dict(begin=[1280,540,1,1],end=[1136,540,1,1],duration=900,starting=0,contact=1)]
    assert device.pipeline_inputs==1


def test_refused_pinch_is_not_retried_as_individual_contacts():
    posted=[]
    def post(*args):posted.append(args);return SimpleNamespace(done=True,succeeded=False)
    device=runner.MaaDevice(SimpleNamespace(id=''),target_long_side=0,
                            tasker=SimpleNamespace(post_task=post))
    with pytest.raises(runner.RouteLost):device.pinch((960,540),320,.55,.9)
    assert len(posted)==1 and device.pipeline_inputs==0


def test_empty_standalone_reverse_route_refuses_before_touch():
    device=runner.MaaDevice(SimpleNamespace(id=''),target_long_side=0)
    with pytest.raises(RuntimeError,match='binding_is_empty'):
        device.pinch((960,540),320,.55,.9)


@pytest.mark.parametrize('radius,factor,seconds',[(0,.5,1),(320,1.2,1),(320,.5,10),(320,float('nan'),1)])
def test_invalid_geometry_never_constructs_a_native_input(radius,factor,seconds):
    with pytest.raises(ValueError):pinch_node((960,540),radius,factor,seconds)


@pytest.mark.parametrize('identity',['',None,'apparently-valid-id'])
@pytest.mark.parametrize('action',['click','swipe'])
def test_callback_click_and_swipe_use_context_even_with_an_apparently_valid_id(identity,action):
    calls=[]
    def reverse(*a):pytest.fail('callback input posted to reverse controller route')
    controller=SimpleNamespace(id=identity,post_click=reverse,post_swipe=reverse)
    def post(entry,override):
        calls.append(('task',entry,override));return SimpleNamespace(done=True,succeeded=True)
    tasker=SimpleNamespace(input_route='context',post_task=post)
    device=runner.MaaDevice(controller,target_long_side=0,tasker=tasker,
        before_input=lambda *p:calls.append(('admit',*p)))
    if action=='click':device.click(960,540)
    else:device.swipe(960,540,960,360,350)
    assert [c[0] for c in calls]==['admit','task']
    assert calls[1][1]==runner.PIPELINE_INPUT_NODES[action]
    node=calls[1][2][calls[1][1]]
    assert node['action']==('Click' if action=='click' else 'Swipe')
    assert getattr(device,'inputs_abandoned',0)==0
    assert device.pipeline_inputs==1
