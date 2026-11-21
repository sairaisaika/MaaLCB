"""`map_click_size` 必须进日志，而不是只躺在 record 里。"""
from __future__ import annotations

from types import SimpleNamespace
from maalimbus import runner


def test_the_size_record_is_named_by_the_debug_note(tmp_path,monkeypatch):
    notes=[]
    journal=SimpleNamespace(record=lambda event,**fields:notes.append(dict(event=event,**fields)))
    record=dict(scene='MAP',frame=None,image_sha256='unit-frame',size=[1920,1080],ocr=[])
    loop=runner.MirrorRunner(runner.FakeDevice(),journal=journal,directory=tmp_path,
                             settings={'rounds':1,'interval':0})
    loop.observer=SimpleNamespace(directory=tmp_path,observe=lambda **kw:dict(record))
    def candidates(directory,record,**kw):
        record.update(map_click_size={'small':1,'kept':2},map_candidates=['bulky'],map_optional=None)
        return 'unit-frame',[]
    monkeypatch.setattr(runner,'candidates_of',candidates)
    loop.step()
    rows=[x for x in notes if x['event']=='map_candidates_debug']
    assert rows and rows[0]['map_click_size']=={'small':1,'kept':2}
    assert 'map_candidates' not in rows[0] and 'map_optional' not in rows[0]
    assert loop.device.clicks==[]
