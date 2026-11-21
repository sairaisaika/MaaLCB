"""Small, local trace of the native sub-tasks owned by the Mirror runner."""
from collections import OrderedDict, deque
from threading import Lock
import time

from maa.context import ContextEventSink
from maa.event_sink import NotificationType


OBSERVATION_NODES = frozenset(('WindowMapObserve', 'WindowBattleObserve'))
ACTION_NODES = frozenset(('MirrorDrive', 'MirrorPointClick', 'MirrorPointSwipe', 'MirrorPointPinch'))
TRACKED_NODES = OBSERVATION_NODES | ACTION_NODES


class PipelineTrace(ContextEventSink):
    """Join callback phases by the sub-task ID the framework actually returns."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._tasks = OrderedDict()
        self._lock = Lock()

    def _capture(self, phase, status, detail, id_field):
        if detail.name not in TRACKED_NODES or status not in (
                NotificationType.Starting, NotificationType.Succeeded, NotificationType.Failed):
            return
        with self._lock:
            task = self._tasks.setdefault(detail.task_id, deque(maxlen=12))
            task.append((self._clock(), phase, status.name.lower(), getattr(detail, id_field)))
            self._tasks.move_to_end(detail.task_id)
            if len(self._tasks) > 16:
                self._tasks.popitem(last=False)

    def on_node_pipeline_node(self, context, noti_type, detail):
        self._capture('pipeline', noti_type, detail, 'node_id')

    def on_node_recognition(self, context, noti_type, detail):
        self._capture('recognition', noti_type, detail, 'reco_id')

    def on_node_action(self, context, noti_type, detail):
        self._capture('action', noti_type, detail, 'action_id')

    def finish(self, entry, started, job):
        detail = job.detail
        task_id = getattr(detail, 'task_id', None)
        with self._lock:
            callbacks = self._tasks.pop(task_id, ())
        return dict(entry=entry, task_id=task_id, succeeded=job.succeeded,
                    elapsed_ms=round((self._clock()-started)*1000),
                    callbacks=[dict(phase=phase, status=status, id=identifier,
                                    elapsed_ms=round((seen-started)*1000))
                               for seen,phase,status,identifier in callbacks if seen >= started])
