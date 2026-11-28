"""A name the observation writer uses must be bound in that module.

Measured twice this session: `party` and then `party_point` were referenced after the
local import was moved, producing `NameError` inside a callback -- which the loop then
reported as "the page could not be read". A missing name must fail here instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import agent.recognition as recognition  # noqa: E402


def test_the_party_reader_is_bound_at_module_level():
    assert hasattr(recognition, 'party_point'), \
        'party_point is used by the map writer but not imported'


def test_the_map_header_helpers_are_bound():
    for name in ('map_header', 'route_decision', 'node_panel'):
        assert hasattr(recognition, name), f'{name} is used but not imported'


def test_the_writer_no_longer_hardcodes_no_party():
    source = (ROOT / 'agent' / 'recognition.py').read_text(encoding='utf-8')
    # The header-path writer this was written for (`ThemeObservation`) was removed on
    # 2026-11-27; the remaining writer reads the party from its own frame.
    assert "party=party_point(image) if scene=='MAP' else None" in source, \
        'the map writer must read the party, not assume None'
    assert 'map_player=None if party is None else list(party)' in source


def test_actual_agent_adapter_keeps_context_route_after_a_composite_pinch():
    from types import SimpleNamespace
    from maalimbus.runner import MaaDevice
    calls=[]
    def native(entry,override):
        calls.append((entry,override));return SimpleNamespace(status=SimpleNamespace(succeeded=True))
    def forbidden(*a):raise AssertionError('actual callback adapter selected reverse input')
    tasker=recognition.AgentTasker(SimpleNamespace(run_task=native))
    controller=SimpleNamespace(id='apparently-live',post_click=forbidden,post_swipe=forbidden,
        post_touch_down=forbidden,post_touch_move=forbidden,post_touch_up=forbidden)
    device=MaaDevice(controller,target_long_side=0,tasker=tasker)
    device.click(960,540);device.pinch((960,540),320,.55,.9)
    device.swipe(960,540,960,360,350)
    assert [entry for entry,_ in calls]==['MirrorPointClick','MirrorPointPinch','MirrorPointSwipe']
    assert device.pipeline_inputs==3 and getattr(device,'inputs_abandoned',0)==0


def test_native_pipeline_trace_correlates_subtask_and_excludes_focus(tmp_path):
    import json
    from types import SimpleNamespace
    from maa.event_sink import NotificationType
    from agent.pipeline_trace import PipelineTrace

    trace = PipelineTrace()
    journal = recognition.Journal(tmp_path)

    def run(entry, _override):
        for task_id in (121, 122):
            detail = SimpleNamespace(task_id=task_id, name=entry, reco_id=33,
                                     focus={'unexpected': 'private OCR'})
            trace.on_node_recognition(None, NotificationType.Starting, detail)
            trace.on_node_recognition(None, NotificationType.Succeeded, detail)
        trace.on_node_action(None, NotificationType.Failed,
                             SimpleNamespace(task_id=122, name=entry, action_id=44))
        return SimpleNamespace(task_id=122, status=SimpleNamespace(succeeded=False))

    context = SimpleNamespace(run_task=run)
    job = recognition.AgentTasker(context, journal=journal, trace=trace).post_task('MirrorPointClick')
    text = (tmp_path / 'events.jsonl').read_text(encoding='utf8')
    event = json.loads(text)
    assert not job.succeeded
    assert event['task_id'] == 122
    assert [(r['phase'], r['status'], r['id']) for r in event['callbacks']] == [
        ('recognition', 'starting', 33), ('recognition', 'succeeded', 33),
        ('action', 'failed', 44),
    ]
    assert 'private OCR' not in text
