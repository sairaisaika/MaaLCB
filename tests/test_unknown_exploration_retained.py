"""Historical map replay is optional; synthetic pending guards must always run."""
import json
from maalimbus.unknown_exploration import Exploration
from test_unknown_exploration import frame


def test_map_pan_is_bounded_and_pixel_motion_is_not_node_arrival(tmp_path):
    from pathlib import Path
    import shutil
    source=Path(__file__).resolve().parents[1]/'evidence/runtime/packaged-mirror-20261012-101555/frame-0131.json'
    before=tmp_path/'map.json'
    shutil.copyfile(source,before);shutil.copyfile(source.with_suffix('.png'),before.with_suffix('.png'))
    record=json.loads(before.read_text(encoding='utf-8'))
    e=Exploration(tmp_path/'state.json',tmp_path/'review','map-run')
    for _ in range(3):
        c=e.choose(record);assert c and c['action']=='swipe'
        x,y,w,h=c['box'];ex,ey,ew,eh=c['to_box']
        index=e.reserve(before,c,(x+2,y+2),600,(ex+2,ey+2))
        e.acknowledge(index)
        result=e.finish(before,'MAP')
        assert not result['success']
    assert e.choose(record) is None
    after,_=frame(tmp_path,'panel','NODE_PANEL',20)
    e.resolve_episode(after,'NODE_PANEL')
    assert e.data['attempts'][-1]['episode_resolved']
    assert not e.data['attempts'][-1]['success']
    assert e.choose(record)['kind']=='map_viewport_pan_down'


