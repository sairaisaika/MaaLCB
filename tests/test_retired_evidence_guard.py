"""The retired-evidence guard decides per test, not per module.

This module must name no retained run itself: the guard reads string constants, and a
test here that spelled a real retired run as a path would be skipped by the guard it is
testing. Every run below is therefore assembled from parts (`RETIRED`, `KEPT`) and only
ever appears inside generated source text.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import conftest
from conftest import reachable_runs, retained_dependencies

RETIRED = '-'.join(('window', '20260101', '000001'))
OTHER = '-'.join(('window', '20260101', '000002'))
KEPT = '-'.join(('window', '20260101', '000003'))


def module(tmp_path, source, name='test_sample.py'):
    path = tmp_path / name
    path.write_text(textwrap.dedent(source).replace('RETIRED', RETIRED)
                    .replace('OTHER', OTHER).replace('KEPT', KEPT), encoding='utf-8')
    return str(path)


def test_this_module_names_no_retained_run():
    text = pathlib.Path(__file__).read_text(encoding='utf-8')
    assert retained_dependencies(text) == frozenset()


def test_a_path_in_one_test_does_not_reach_its_neighbour(tmp_path):
    path = module(tmp_path, '''
        def test_reads_the_frame():
            return open('evidence/runtime/RETIRED/frame-0001.json')

        def test_reads_nothing():
            assert 1 + 1 == 2
        ''')
    assert reachable_runs(path, 'test_reads_the_frame') == {RETIRED}
    assert reachable_runs(path, 'test_reads_nothing') == frozenset()


def test_a_module_constant_reaches_only_the_tests_that_read_it(tmp_path):
    path = module(tmp_path, '''
        import pathlib
        ROOT = pathlib.Path(__file__).parents[1]
        FRAME = ROOT / 'evidence/runtime/RETIRED/frame-0001.json'
        PAIR = (FRAME, ROOT / 'evidence/runtime/OTHER/frame-0002.json')
        LIMIT = 3

        def load(path=FRAME):
            return path.read_text()

        def wrapped():
            return load()

        def test_direct():
            assert FRAME.exists()

        def test_through_a_default_argument():
            assert load()

        def test_through_two_helpers():
            assert wrapped()

        def test_through_a_derived_constant():
            assert PAIR

        def test_another_constant():
            assert LIMIT == 3 and ROOT
        ''')
    assert reachable_runs(path, 'test_direct') == {RETIRED}
    assert reachable_runs(path, 'test_through_a_default_argument') == {RETIRED}
    assert reachable_runs(path, 'test_through_two_helpers') == {RETIRED}
    assert reachable_runs(path, 'test_through_a_derived_constant') == {RETIRED, OTHER}
    assert reachable_runs(path, 'test_another_constant') == frozenset()


def test_a_local_name_does_not_reach_the_module_name_it_shadows(tmp_path):
    path = module(tmp_path, '''
        FRAME = 'evidence/runtime/RETIRED/frame-0001.json'

        def test_own_local(tmp_path):
            FRAME = tmp_path / 'frame.json'
            assert [FRAME for _ in range(2)]

        def test_own_parameter(FRAME=None):
            assert FRAME is None

        def test_inner_function_reads_the_module_name():
            def inner():
                return FRAME
            assert inner()

        def test_declared_global():
            global FRAME
            FRAME = None
        ''')
    assert reachable_runs(path, 'test_own_local') == frozenset()
    assert reachable_runs(path, 'test_own_parameter') == frozenset()
    assert reachable_runs(path, 'test_inner_function_reads_the_module_name') == {RETIRED}
    assert reachable_runs(path, 'test_declared_global') == {RETIRED}


def test_fixtures_and_parametrize_arguments_are_followed(tmp_path):
    path = module(tmp_path, '''
        import pytest
        FRAMES = ['evidence/runtime/RETIRED/frame-0001.json']

        @pytest.fixture
        def frame():
            return 'evidence/runtime/OTHER/frame-0001.json'

        @pytest.fixture
        def page(frame):
            return frame

        def helper(frame):
            return frame

        def test_requests_the_fixture(frame):
            assert frame

        def test_requests_a_fixture_built_on_it(page):
            assert page

        @pytest.mark.usefixtures('frame')
        def test_names_the_fixture_in_a_mark():
            pass

        @pytest.mark.parametrize('path', FRAMES)
        def test_parametrized(path):
            assert path

        def test_a_helper_parameter_is_not_a_fixture_request():
            assert helper(1)
        ''')
    assert reachable_runs(path, 'test_requests_the_fixture') == {OTHER}
    assert reachable_runs(path, 'test_requests_a_fixture_built_on_it') == {OTHER}
    assert reachable_runs(path, 'test_names_the_fixture_in_a_mark') == {OTHER}
    assert reachable_runs(path, 'test_parametrized') == {RETIRED}
    assert reachable_runs(path, 'test_a_helper_parameter_is_not_a_fixture_request') == frozenset()


def test_what_pytest_runs_unasked_reaches_every_test(tmp_path):
    autouse = module(tmp_path, '''
        import pytest

        @pytest.fixture(autouse=True)
        def prepared():
            return open('evidence/runtime/RETIRED/frame-0001.json')

        def test_plain():
            pass
        ''', 'test_autouse.py')
    setup = module(tmp_path, '''
        def setup_module():
            open('evidence/runtime/RETIRED/frame-0001.json')

        def test_plain():
            pass
        ''', 'test_setup.py')
    marked = module(tmp_path, '''
        import pathlib
        import pytest
        SOURCE = pathlib.Path('evidence/runtime/RETIRED/frame-0001.json')
        pytestmark = pytest.mark.skipif(not SOURCE.is_file(), reason='private')

        def test_plain():
            pass
        ''', 'test_marked.py')
    for path in (autouse, setup, marked):
        assert reachable_runs(path, 'test_plain') == {RETIRED}


def test_a_list_filled_in_place_carries_what_was_added(tmp_path):
    path = module(tmp_path, '''
        FRAMES = []
        FRAMES.append('evidence/runtime/RETIRED/frame-0001.json')
        TABLE = {}
        TABLE['home'] = 'evidence/runtime/OTHER/frame-0001.json'

        def test_list():
            assert FRAMES

        def test_table():
            assert TABLE

        def test_neither():
            pass
        ''')
    assert reachable_runs(path, 'test_list') == {RETIRED}
    assert reachable_runs(path, 'test_table') == {OTHER}
    assert reachable_runs(path, 'test_neither') == frozenset()


def test_methods_of_a_test_class_are_decided_one_by_one(tmp_path):
    path = module(tmp_path, '''
        class TestPages:
            LIMIT = 3

            def load(self):
                return open('evidence/runtime/RETIRED/frame-0001.json')

            def test_uses_the_helper(self):
                assert self.load()

            def test_uses_the_constant(self):
                assert self.LIMIT == 3

        class TestShared:
            FRAME = 'evidence/runtime/OTHER/frame-0001.json'

            def test_any(self):
                pass

        def test_builds_the_class():
            assert TestPages()
        ''')
    assert reachable_runs(path, 'test_uses_the_helper', 'TestPages') == {RETIRED}
    assert reachable_runs(path, 'test_uses_the_constant', 'TestPages') == frozenset()
    # A class attribute is read through `self` in ways no name shows, so it reaches them all.
    assert reachable_runs(path, 'test_any', 'TestShared') == {OTHER}
    assert reachable_runs(path, 'test_builds_the_class') == {RETIRED}


def test_a_helper_borrowed_from_another_test_module_brings_its_reach(tmp_path):
    module(tmp_path, '''
        LIMIT = 3

        def frame():
            return open('evidence/runtime/RETIRED/frame-0001.json')

        def blank():
            return {}
        ''', 'test_lender.py')
    path = module(tmp_path, '''
        import test_lender as lender
        from test_lender import frame, blank as empty, LIMIT

        def test_borrows_the_frame():
            assert frame()

        def test_borrows_the_blank_page():
            assert empty() == {} and LIMIT

        def test_uses_the_whole_module():
            assert lender.blank() == {}
        ''', 'test_borrower.py')
    assert reachable_runs(path, 'test_borrows_the_frame') == {RETIRED}
    assert reachable_runs(path, 'test_borrows_the_blank_page') == frozenset()
    # `lender.anything` is not resolved name by name: the whole lender counts.
    assert reachable_runs(path, 'test_uses_the_whole_module') == {RETIRED}


def test_a_test_the_source_does_not_define_falls_back_to_the_whole_module(tmp_path):
    path = module(tmp_path, '''
        FRAME = 'evidence/runtime/RETIRED/frame-0001.json'

        def test_plain():
            pass
        ''')
    assert reachable_runs(path, 'test_generated_elsewhere') == {RETIRED}
    assert reachable_runs(path, 'test_method', 'TestGenerated') == {RETIRED}


def test_pytest_skips_only_the_test_that_needs_the_retired_run(tmp_path):
    tests = tmp_path / 'tests'
    tests.mkdir()
    shutil.copy(conftest.__file__, tests / 'conftest.py')
    (tmp_path / 'evidence' / 'runtime' / KEPT).mkdir(parents=True)
    (tmp_path / 'evidence' / 'runtime' / KEPT / 'frame-0001.json').write_text('{}', encoding='utf-8')
    module(tests, '''
        import pathlib
        ROOT = pathlib.Path(__file__).resolve().parents[1]
        GONE = ROOT / 'evidence/runtime/RETIRED/frame-0001.json'
        HERE = ROOT / 'evidence/runtime/KEPT/frame-0001.json'

        def test_needs_the_retired_frame():
            assert GONE.read_text(encoding='utf-8')

        def test_needs_the_kept_frame():
            assert HERE.read_text(encoding='utf-8') == '{}'

        def test_needs_no_frame():
            assert ROOT.is_dir()
        ''')
    done = subprocess.run([sys.executable, '-m', 'pytest', str(tests), '-q', '-rs',
                           '-p', 'no:cacheprovider'], cwd=tmp_path, capture_output=True,
                          text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    assert done.returncode == 0, done.stdout + done.stderr
    assert '2 passed, 1 skipped' in done.stdout
    # A skip that names the run, not a FileNotFoundError.
    reason = [line for line in done.stdout.splitlines() if line.startswith('SKIPPED')]
    assert len(reason) == 1 and 'the retained run %s was retired' % RETIRED in reason[0]
    assert 'FileNotFoundError' not in done.stdout
