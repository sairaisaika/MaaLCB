"""Real static source declarations must protect raw and cold fixture bytes."""
import os
from pathlib import Path

import pytest

from maalimbus import capture_retention as retention,workspace,native_image_archive as archive,cold_retention as cold
from test_capture_retention import run
from test_cold_retention import corpus


@pytest.mark.parametrize('expression',[
    "ROOT/'evidence'/'runtime'/'current'",
    "ROOT/('evidence'+'/runtime')/'current'",
    "ROOT/'evidence'/'runtime'/('cur'+'rent')",
    "Path('evidence')/'runtime'/'current'",
    "ROOT.joinpath('evidence','runtime','current')",
    "Path('evidence','runtime','current')",
    "Path(ROOT,'evidence','runtime','current')",
    "ROOT/Path('evidence')/'runtime'/'current'",
    "ROOT/'evidence/runtime/current'",
])
def test_static_path_families_bind_module_alias_and_decorated_frame_set(tmp_path,expression):
    body=(f'RUN={expression}\n'+'# gap\n'*100+
          "@pytest.mark.parametrize('stem',['frame-0005','frame-0006'])\n"
          'def check(stem):\n    return RUN/(stem+".json")\n').encode()
    kept=retention._source_references(body,tmp_path,python=True)
    assert all(tmp_path/f'evidence/runtime/current/{name}{suffix}' in kept
               for name in ('frame-0005','frame-0006') for suffix in ('.png','.json'))


def test_split_source_pins_survive_actual_raw_pressure(tmp_path,monkeypatch):
    folder=run(tmp_path);source=tmp_path/'tests/consumer.py';source.parent.mkdir()
    source.write_text("RUN=ROOT/'evidence'/'runtime'/'current'\n"
                      "@pytest.mark.parametrize('stem',['frame-0005','frame-0006'])\n"
                      "def check(stem):return RUN/(stem+'.json')\n")
    before={folder/f'frame-{n:04d}.png':(folder/f'frame-{n:04d}.png').read_bytes() for n in (5,6)}
    monkeypatch.setattr(workspace,'BUDGET_BYTES',workspace.size(tmp_path)+50000)
    result=retention.reserve(folder,80000,application_root=tmp_path)
    assert result['sufficient'] and result['storage_maintenance']
    assert all(p.read_bytes()==body for p,body in before.items())


def test_split_source_pins_protect_the_same_exact_cold_original(tmp_path,monkeypatch):
    folder,originals,_=corpus(tmp_path,monkeypatch);source=tmp_path/'tests/consumer.py';source.parent.mkdir()
    source.write_text(f"RUN=ROOT/'evidence'/'runtime'/{folder.name!r}\n"
                      "def check():return RUN/'frame-0002.png'\n")
    target=folder/'frame-0002.png';relative=target.relative_to(tmp_path).as_posix()
    result=cold.reclaim(tmp_path)
    assert relative not in result['retired'] and archive.read_png(target)==originals[relative]


def test_same_size_same_time_split_path_edit_rebinds_current_protection(tmp_path):
    source=tmp_path/'tests/consumer.py';source.parent.mkdir()
    source.write_text("RUN=ROOT/'evidence'/'runtime'/'first'\ndef check():return RUN/'frame-0005.png'\n")
    stamp=source.stat();first=tmp_path/'evidence/runtime/first/frame-0005.png';second=tmp_path/'evidence/runtime/other/frame-0005.png'
    assert first in retention._reference_keep(tmp_path)
    source.write_text(source.read_text().replace("'first'","'other'"));os.utime(source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert source.stat().st_size==stamp.st_size
    kept=retention._reference_keep(tmp_path);assert second in kept and first not in kept


def test_distinct_function_aliases_do_not_cross_product_fixtures(tmp_path):
    body=b"A=ROOT/'evidence'/'runtime'/'first'\nB=ROOT/'evidence'/'runtime'/'other'\ndef a():return A/'frame-0005.png'\ndef b():return B/'frame-0006.png'\n"
    kept=retention._source_references(body,tmp_path,python=True)
    assert tmp_path/'evidence/runtime/first/frame-0005.png' in kept
    assert tmp_path/'evidence/runtime/other/frame-0006.png' in kept
    assert tmp_path/'evidence/runtime/first/frame-0006.png' not in kept
    assert tmp_path/'evidence/runtime/other/frame-0005.png' not in kept


def test_static_scan_never_executes_project_code(tmp_path):
    target=tmp_path/'executed'
    body=("RUN=ROOT.joinpath('evidence','runtime','current')\n"
          f"Path({str(target)!r}).write_text('forbidden')\n"
          "raise RuntimeError('must never run')\ndef case():return RUN/'frame-0005.png'\n").encode()
    assert tmp_path/'evidence/runtime/current/frame-0005.png' in retention._source_references(body,tmp_path,python=True)
    assert not target.exists()


def test_actual_white_fixture_declarations_are_pinned_even_if_original_is_missing():
    root=Path(__file__).resolve().parents[1];source=root/'tests/test_white_connected_node.py'
    kept=retention._source_references(source.read_bytes(),root,python=True)
    assert all(root/f'evidence/runtime/packaged-mirror-20261119-044504/frame-{n:04d}{suffix}' in kept
               for n in (42,48,50) for suffix in ('.png','.json'))


def test_indirect_fixture_dependencies_keep_frame_sets_with_their_own_runs(tmp_path):
    body=b"A=ROOT/'evidence'/'runtime'/'first'\nB=ROOT/'evidence'/'runtime'/'other'\n@pytest.fixture\ndef aa(request):return A/request.param\n@pytest.fixture\ndef bb(request):return B/request.param\n@pytest.mark.parametrize('aa',['frame-0005'],indirect=True)\ndef one(aa):pass\n@pytest.mark.parametrize('bb',['frame-0006'],indirect=True)\ndef two(bb):pass\n"
    kept=retention._source_references(body,tmp_path,python=True)
    assert tmp_path/'evidence/runtime/first/frame-0005.png' in kept
    assert tmp_path/'evidence/runtime/other/frame-0006.png' in kept
    assert tmp_path/'evidence/runtime/first/frame-0006.png' not in kept
    assert tmp_path/'evidence/runtime/other/frame-0005.png' not in kept


def test_local_fixture_dependency_chain_resolves_without_running_it(tmp_path):
    body=b"RUN=ROOT/'evidence'/'runtime'/'current'\n@pytest.fixture\ndef base(request):return RUN/request.param\n@pytest.fixture\ndef outer(base):return base\n@pytest.mark.parametrize('outer',['frame-0005'],indirect=True)\ndef check(outer):pass\n"
    assert tmp_path/'evidence/runtime/current/frame-0005.png' in retention._source_references(body,tmp_path,python=True)


def test_same_named_class_fixtures_conservatively_keep_both_owners(tmp_path):
    body=b"A=ROOT/'evidence'/'runtime'/'first'\nB=ROOT/'evidence'/'runtime'/'other'\nclass One:\n @pytest.fixture\n def pixels(self,request):return A/request.param\n @pytest.mark.parametrize('pixels',['frame-0005'],indirect=True)\n def one(self,pixels):pass\nclass Two:\n @pytest.fixture\n def pixels(self,request):return B/request.param\n @pytest.mark.parametrize('pixels',['frame-0006'],indirect=True)\n def two(self,pixels):pass\n"
    kept=retention._source_references(body,tmp_path,python=True)
    assert tmp_path/'evidence/runtime/first/frame-0005.png' in kept
    assert tmp_path/'evidence/runtime/other/frame-0006.png' in kept
