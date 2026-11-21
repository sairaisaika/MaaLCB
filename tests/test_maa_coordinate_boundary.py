"""Maa owns screenshot-to-device conversion for direct and Pipeline inputs."""
from maalimbus.runner import MaaDevice


class Job:
    done = True
    succeeded = True


class Controller:
    def __init__(self):
        self.inputs = []
    def set_screenshot_target_long_side(self, side):
        self.long_side = side
    def post_click(self, *point):
        self.inputs.append(('click', *point))
        return Job()
    def post_swipe(self, *vector):
        self.inputs.append(('swipe', *vector))
        return Job()


class Tasker:
    def __init__(self): self.inputs = []
    def post_task(self, entry, override):
        self.inputs.append((entry, override[entry]))
        return Job()


def device(*,task_owned=True):
    controller, tasker = Controller(), Tasker()
    value = MaaDevice(controller, tasker=tasker if task_owned else None,
                      wait=lambda job, **kwargs: job)
    value.frame_size = (1920, 1080)
    # Regression for the old D369 conversion when raw size was already cached.
    value._screen = (1280, 720)
    return value, controller, tasker


def test_direct_route_passes_screenshot_coordinates_once():
    value, controller, _ = device(task_owned=False)
    value.click(960, 540)
    value.swipe(600, 300, 900, 600, 500)
    assert controller.inputs == [('click', 960, 540),
                                 ('swipe', 600, 300, 900, 600, 500)]


def test_pipeline_route_uses_the_same_screenshot_coordinates():
    value, controller, tasker = device()
    value.route_suspect = True
    value.click(960, 540)
    value.route_suspect = True
    value.swipe(600, 300, 900, 600, 500)
    assert controller.inputs == []
    assert tasker.inputs[0][1]['target'] == [960, 540, 1, 1]
    assert tasker.inputs[1][1]['begin'] == [600, 300, 1, 1]
    assert tasker.inputs[1][1]['end'] == [900, 600, 1, 1]


def test_observer_route_does_not_require_a_device_screencap_first():
    value, controller, tasker = device()
    value.frame_size = None
    value.click(960, 540)
    assert controller.inputs == [] and tasker.inputs[0][1]['target']==[960,540,1,1]
