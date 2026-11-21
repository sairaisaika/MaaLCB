"""A native connected forward ring must survive the entire candidate pipeline."""
import json
from pathlib import Path
import cv2,numpy as np,pytest
from maalimbus.map_node_geometry import connected_ring_node
from maalimbus import map_vision,runner
from maalimbus.window import plan_step


FRAME=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261117-142233/frame-0013.json'


@pytest.mark.skipif(not FRAME.exists(),reason='Native green map retained privately')
def test_native_first_candidate_is_the_right_connected_room_and_not_a_grey_return():
    record=json.loads(FRAME.read_text());before=FRAME.read_bytes()
    _,boxes=runner.candidates_of(FRAME.parent,record,mode='box')
    assert boxes and boxes[0]==[1102,460,40,40]
    assert record['map_connected_step']['party']==[910,484]
    assert record['map_connected_step']['measured_column_pitch']==192
    plan=plan_step('MAP',candidates=boxes)
    assert plan['action']=='click' and list(plan['target'])==boxes[0]
    loop=runner.MirrorRunner(runner.FakeDevice(),directory=FRAME.parent,settings={})
    loop.state.update(map_party=record['map_party'],map_step_reach=record['map_step_reach'])
    assert loop._map_click_allowed(record['map_connected_step']['point'])
    assert not loop._map_click_allowed([1500,480])
    assert loop.device.clicks==[]
    assert FRAME.read_bytes()==before
    # A readable ring without its outgoing path cannot use this shortcut.
    image=cv2.imread(str(FRAME.with_suffix('.png')))
    image[474:493,959:1078]=(90,90,90)
    assert connected_ring_node(image,template=runner.node_badge_template()) is None


def row(x,y,kind):return dict(kind=kind,box=[x-20,y-20,40,40])


def setup(monkeypatch,rings):
    image=np.zeros((1080,1920,3),np.uint8)
    monkeypatch.setattr(map_vision,'locomotive_marker',lambda image:(600,400))
    monkeypatch.setattr(map_vision,'map_clicks',lambda image,**kwargs:
        [row(400,400,'gold_badge_node'),row(600,560,'gold_badge_node'),*rings])
    return image


def test_grey_return_edge_is_not_a_saturated_forward_path(monkeypatch):
    image=setup(monkeypatch,[row(800,400,'lit_ring')])
    cv2.line(image,(600,400),(800,400),(170,170,170),7)
    assert connected_ring_node(image) is None


def test_bright_path_cannot_skip_an_independently_measured_column(monkeypatch):
    image=setup(monkeypatch,[row(1000,400,'lit_ring')])
    cv2.line(image,(600,400),(1000,400),(10,220,140),7)
    assert connected_ring_node(image) is None


def test_two_supported_rings_keep_normal_policy_in_charge(monkeypatch):
    image=setup(monkeypatch,[row(800,400,'lit_ring'),row(800,560,'lit_ring')])
    cv2.line(image,(600,400),(800,400),(10,220,140),7)
    cv2.line(image,(600,400),(800,560),(10,220,140),7)
    assert connected_ring_node(image) is None
