"""Borrowed native controller lifetime across cold-start and capture consumers."""
import json
import shutil
import gc
import weakref
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from recognition import Journal, LimbusRecognition, MirrorLoopAction
import recognition
from maalimbus import runner
from test_agent_loop import FakeContext, FakeController, read_result


@pytest.fixture(autouse=True)
def clean_loop_environment(monkeypatch):
    for name in runner.settings().as_dict():
        monkeypatch.delenv('MAALIMBUS_LOOP_' + name.upper(), raising=False)
    for name in ('MAALIMBUS_LOOP_BUDGET', 'MAALIMBUS_RUN_DIR'):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize('cold_start', [False, True])
def test_callback_borrowed_controller_survives_capture_and_startup_checks(tmp_path, monkeypatch, cold_start):
    """Model pinned RemoteTasker::controller invalidating its previous proxy.

    The old three lookups left capture holding generation2 after the startup
    check acquired generation3. A constant SimpleNamespace cannot expose that.
    """
    source = ROOT / 'evidence/runtime/packaged-mirror-20261117-010749/frame-0055.json'
    directory = tmp_path / 'run'
    monkeypatch.setenv('MAALIMBUS_DATA_PATH', str(tmp_path / 'private'))
    monkeypatch.delenv('MAALIMBUS_TARGET_LONG_SIDE', raising=False)

    class Borrowed(FakeController):
        def __init__(self, owner, generation):
            super().__init__()
            self.owner, self.generation = owner, generation

        def check(self):
            if self.generation != self.owner.generation:
                raise OSError('borrowed remote controller was replaced')

        def set_screenshot_target_long_side(self, value):
            self.check()
            super().set_screenshot_target_long_side(value)
            return True

        @property
        def info(self):
            self.check()
            return {'adb_serial': 'unit-test-device'}

    class InvalidatingTasker:
        generation = 0

        @property
        def controller(self):
            self.generation += 1
            return Borrowed(self, self.generation)

    context = FakeContext(directory, frames=(source,))
    context.tasker = InvalidatingTasker()
    def page():
        # Preserve the actual record's own filename/frame identity; the legacy
        # helper renames files without updating metadata and predates FrameRef.
        for suffix in ('.json', '.png'):
            shutil.copyfile(source.with_suffix(suffix), directory/(source.stem+suffix))
        context.opened.append(source)
        return dict(json.loads(source.read_text(encoding='utf8')),
                    frame=source.stem, input_sent=False)
    monkeypatch.setattr(context, 'page', page)
    reader = LimbusRecognition('en', Journal(directory))
    if cold_start:
        reader.startup_window = dict(serial='unit-test-device', until=runner.time.monotonic()+60)
    action = MirrorLoopAction(reader)
    params = dict(directory=str(directory), observe_only=True, steps=1, interval=0, run_store='')
    action.run(context, SimpleNamespace(custom_action_param=json.dumps(params), node_name='MirrorLoop'))
    result = read_result(directory)
    assert result['reason'] == 'observe_only', result
    assert result['clicks_sent'] == 0 and not result['verified_clear']
    assert context.tasker.generation == 1
    assert context.entries == ['WindowMapObserve']


def test_foreground_validator_outlives_context_without_reborrowing_its_controller(tmp_path,monkeypatch):
    class Lease:
        @staticmethod
        def acquire(path):return SimpleNamespace(close=lambda:None)

    info={'type':'adb','adb_serial':'unit-test-device','adb_path':'unit-test-adb'}
    lookups=[];checks=[]
    class Tasker:
        @property
        def controller(self):
            lookups.append('borrow')
            return SimpleNamespace(info=info)

    context=SimpleContext(tasker=Tasker())
    reader=SimpleNamespace(journal=SimpleNamespace(record=lambda *a,**kw:None),input_validator=None)
    monkeypatch.setattr(recognition,'ControllerLease',Lease)
    monkeypatch.setattr(recognition.input_helpers,'report',lambda root:{})
    monkeypatch.setattr(recognition.input_helpers,'warning',lambda helpers:None)
    # This test is about the controller lifetime; the local-asset gate has its own tests.
    from maalimbus import local_assets
    monkeypatch.setattr(local_assets,'inventory',lambda root:{})
    def foreground(identity):
        checks.append(dict(identity))
        return 'fresh-'+str(len(checks))
    monkeypatch.setattr(recognition,'controller_foreground',foreground)
    assert recognition.InputPreflight(reader).run(context,SimpleNamespace()) is True
    reference=weakref.ref(context)
    del context
    gc.collect()
    assert reference() is None,'Validator must not keep an expired native callback alive'
    info['adb_serial']='another-device'
    assert reader.input_validator()=='fresh-2'
    assert reader.input_validator()=='fresh-3'
    assert lookups==['borrow'] and len(checks)==3
    assert all(row['adb_serial']=='unit-test-device' for row in checks)


class SimpleContext:
    def __init__(self,tasker):self.tasker=tasker


