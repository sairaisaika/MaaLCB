"""Capture coordinates remain distinct from Maa's device conversion."""
import json
from pathlib import Path
import cv2
import pytest
from maalimbus.runner import controls_by_id,REGISTRY
from maalimbus.theme_vision import selection_header,selection_floor
from maalimbus.vision import Text


def test_verified_boxes_use_the_measured_frame_not_the_catalog_reference():
    registry=json.loads(REGISTRY.read_text(encoding='utf8'))
    before=json.dumps(registry)
    full=controls_by_id(registry)
    small=controls_by_id(registry,(1280,720))
    assert registry['reference_width']==1280
    assert full['pre_battle.card_01']==[355,236,190,248]
    assert small['pre_battle.card_01']==[237,157,127,165]
    assert controls_by_id(registry,(1280,720))==small
    assert controls_by_id(registry)==full and json.dumps(registry)==before
    assert all(x>=0 and y>=0 and x+w<=1280 and y+h<=720 for x,y,w,h in small.values())


def test_header_is_only_permission_for_a_narrow_read_not_page_identity():
    size=(1280,720)
    header=Text('SELECT FLOOR 3 THEME PACK',(510,104,258,28),.96)
    refresh=Text('Refresh',(1060,34,73,22),.99)
    search=Text('Pack Search',(174,31,69,25),.97)
    assert selection_header([header,refresh],size)==3
    assert selection_floor([header,refresh],size) is None
    assert selection_floor([header,refresh,search],size)==3
    assert selection_floor([header,refresh,Text(search.text,search.box,.89)],size) is None
    assert selection_header([header,header,refresh],size) is None
    assert selection_header([header],size) is None


@pytest.mark.parametrize('size',[(1280,720),(1920,1080)])
def test_native_pinch_endpoints_and_recovery_vectors_stay_in_capture(size,tmp_path):
    from types import SimpleNamespace
    from maalimbus.native_gestures import map_pinch,pinch_node
    from maalimbus.runner import MirrorRunner
    centre,radius=map_pinch(size)
    node=pinch_node(centre,radius,.55,.9)
    for swipe in node['swipes']:
        for name in ('begin','end'):
            x,y,w,h=swipe[name]
            assert 0<=x<x+w<=size[0] and 0<=y<y+h<=size[1]
    calls=[]
    device=SimpleNamespace(pinch=lambda *args:calls.append(('pinch',args)),
                           swipe=lambda *args:calls.append(('swipe',args)))
    loop=MirrorRunner(device,settings={},directory=tmp_path)
    loop.artifacts['capture_size']=size
    for action in ('pinch_out','drag_down','drag_up','pan_left','pan_right'):
        loop._recovery_gesture(action)
    assert calls[0]==('pinch',(centre,radius,.55,.9))
    for _,values in calls[1:]:
        assert 0<=values[0]<size[0] and 0<=values[2]<size[0]
        assert 0<=values[1]<size[1] and 0<=values[3]<size[1]


FRAME=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-142233/frame-0013.png'


@pytest.mark.skipif(not FRAME.is_file(),reason='Privately retained native map')
def test_small_capture_keeps_next_room_in_its_own_coordinate_system():
    from maalimbus.map_node_geometry import connected_ring_node
    from maalimbus.runner import node_badge_template
    image=cv2.resize(cv2.imread(str(FRAME)),(1280,720),interpolation=cv2.INTER_AREA)
    found=connected_ring_node(image,template=node_badge_template())
    assert found and abs(found['point'][0]-748)<8 and abs(found['point'][1]-323)<8
    assert found['party'][0]<found['point'][0]<1280
    # Destroy the actual forward path; the same room art must no longer suffice.
    image[315:330,640:718]=(90,90,90)
    assert connected_ring_node(image,template=node_badge_template()) is None


@pytest.mark.skipif(not FRAME.is_file(),reason='Privately retained native map')
def test_visible_connected_native_room_does_not_spend_a_viewport_gesture(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from maalimbus import runner
    from maalimbus.storage import write_json
    source=FRAME.with_suffix('.json');record=json.loads(source.read_text(encoding='utf8'))
    image=cv2.imread(str(FRAME));record['frame']='frame-0001'
    write_json(tmp_path/'frame-0001.json',record)
    (tmp_path/'frame-0001.png').write_bytes(FRAME.read_bytes())
    def forbidden(*a,**kw):raise AssertionError('fresh visible room does not need a gesture')
    device=SimpleNamespace(controller=object(),pinch=forbidden,swipe=forbidden)
    loop=runner.MirrorRunner(device,settings={},directory=tmp_path)
    monkeypatch.setattr(loop,'_observe',forbidden)
    assert loop._normalise_view_once(record) is record
    assert loop.state['view_normalised']
    # A previous failed navigation still earns the actual recovery path.
    loop.state.pop('view_normalised');loop.state['map_refused_streak']=1
    recovered=[]
    monkeypatch.setattr(runner,'normalise_view',lambda *a,**k:
        (recovered.append(True) or dict(centred=True,zoomed=False)))
    loop._normalise_view_once(record)
    assert recovered==[True]
