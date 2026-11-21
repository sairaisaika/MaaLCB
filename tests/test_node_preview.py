"""节点预览面板：点格子只会打开它，点 Enter 才真的进去（用户 2026-10-31 指出）。"""
from __future__ import annotations

import pathlib
import json
import hashlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from maalimbus import vision  # noqa: E402
from maalimbus import anchor, pages, window  # noqa: E402

SIZE = (1920, 1080)


def _records(*items):
    # `vision.find` 读的是属性而不是字典（ocr 记录在进程里是对象，落盘才变成 dict）
    return [types.SimpleNamespace(text=text, box=box, score=score)
            for text, box, score in items]


ENTER = ('Enter', (1660, 900, 120, 40), 0.95)
NAME = ('Thick Rumbling Hum', (820, 220, 520, 46), 0.93)
HEADER = ('Exploring Floor', (58, 127, 330, 51), 0.95)


def test_a_panel_with_its_own_enter_is_a_preview():
    found = vision.node_preview(_records(NAME, ENTER), SIZE)
    assert found is not None and 'enter' in found


def test_a_map_frame_that_also_reads_exploring_is_not_a_preview():
    # `-161115` 的 UNKNOWN 帧里有 'Exploring Floor'：那是地图本身缺 floor 数字，
    # 不是预览面板。这条守卫就是为此存在的。
    assert vision.node_preview(_records(HEADER, ENTER), SIZE) is None


def test_no_enter_means_no_preview():
    assert vision.node_preview(_records(NAME), SIZE) is None


def test_an_enter_outside_the_panel_zone_is_not_the_panels_enter():
    # 镜牢入口页也有一个 Enter，但它在画面中部偏下，不在预览面板的右下角。
    entry = ('Enter', (1100, 700, 120, 40), 0.95)
    assert vision.node_preview(_records(NAME, entry), SIZE) is None


@pytest.mark.parametrize('preview', [None, {}, {'enter': None}])
def test_a_missing_enter_is_a_counted_control_refusal(preview):
    plan = window.plan_step('NODE_PREVIEW', preview=preview)
    assert plan['action'] == window.RECORD
    assert plan['target'] is None
    assert plan['reason'] == 'the_preview_panel_has_no_enter_to_press'
    assert plan['stop_kind'] == anchor.ANCHOR_MISSING
    assert plan['anchor'] == 'node_preview_enter'
    assert pages.kind_of(plan_reason=plan['reason']) == 'missing_control'
    assert anchor.reread_allowed(plan, attempts=0, tries=2)
    assert not anchor.reread_allowed(plan, attempts=1, tries=2)


@pytest.mark.parametrize('successor', ['PRE_BATTLE_TEAM', 'SHOP', 'EVENT_CHOICE', 'MAP'])
def test_the_panels_own_enter_accepts_a_known_node_successor(successor):
    plan = window.plan_step('NODE_PREVIEW', preview={'enter': ENTER[1]})
    assert plan['target'] == list(ENTER[1])
    assert plan['action'] == window.CLICK
    assert window.successor_ok(plan, successor)


@pytest.mark.parametrize('successor', ['NODE_PREVIEW', 'UNKNOWN', 'HOME', 'RESOURCE_DIALOG'])
def test_a_changed_frame_does_not_prove_an_unrelated_successor(successor):
    plan = window.plan_step('NODE_PREVIEW', preview={'enter': ENTER[1]})
    result = window.step_result(plan, sent=True, before='NODE_PREVIEW', after=successor,
                                page=successor, frame_changed=True)
    assert result['passed'] is False
    assert result['reason'] == 'unexpected_successor'


def _preview_protocol(directory, *, stale=None, remove_enter=False):
    """Replay independent retained pages, not an observed adjacent transition."""
    from maalimbus import runner
    from maalimbus.native_image_archive import read_png
    sources=[ROOT/'evidence/runtime/packaged-mirror-20261117-010749/frame-0005.json',
             ROOT/'evidence/runtime/packaged-mirror-20261117-010749/frame-0009.json']
    original={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    records=[json.loads(p.read_text(encoding='utf8')) for p in sources]
    assert [r['scene'] for r in records]==['NODE_PREVIEW','PRE_BATTLE_TEAM']
    pixels=[read_png(p.with_suffix('.png')) for p in sources]
    assert all(hashlib.sha256(body).hexdigest()==row['image_sha256']
               for body,row in zip(pixels,records))
    assert records[0].get('node_preview') is None,'Actual native producer does not serialize this convenience field'
    if stale is not None:records[0]['node_preview']=stale
    if remove_enter:records[0]['ocr']=[t for t in records[0]['ocr'] if t['text']!='Enter']

    class Observer:
        requires_frame_ref=True
        def __init__(self):self.directory=directory;self.count=0
        def observe(self,*,deadline=None):
            i=0 if remove_enter else min(self.count,1);self.count+=1
            path=directory/sources[i].name
            path.write_text(json.dumps(records[i]),encoding='utf8')
            path.with_suffix('.png').write_bytes(pixels[i])
            return dict(records[i],frame=path.stem)

    device=runner.FakeDevice()
    loop=runner.MirrorRunner(device,directory=directory,observer=Observer(),
        settings=dict(steps=1,rounds=1,interval=0,stall_seconds=0,progress_seconds=0))
    result=loop.run(steps=1,round_limit=1,interval=0)
    assert original=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    return device,result


@pytest.mark.parametrize('stale',[None,{'enter':[10,10,30,30]}])
def test_incoming_native_preview_uses_its_own_enter_without_a_previous_map_step(tmp_path,stale):
    device,result=_preview_protocol(tmp_path,stale=stale)
    assert len(device.clicks)==1,result
    x,y=device.clicks[0]
    assert 1670<=x<1792 and 780<=y<841,'Only the current native Enter owns the target'
    assert result['steps'][0]['page_before']=='NODE_PREVIEW'
    assert result['steps'][0]['page_after']=='PRE_BATTLE_TEAM'
    assert result['steps'][0]['passed'] is True
    assert not result['verified_clear']


def test_missing_current_enter_cannot_borrow_a_serialized_preview_target(tmp_path):
    device,result=_preview_protocol(tmp_path,stale={'enter':[1670,780,122,61]},remove_enter=True)
    assert device.clicks==[] and device.swipes==[]
    assert not result['verified_clear'] and not result['passed']
