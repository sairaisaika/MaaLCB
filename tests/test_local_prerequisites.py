"""`needs_local` skips for a missing private path and for nothing else.

The CI runner is a public checkout: it has no `evidence/`, `build/`, `dist/` or
`config/`.  The marker turns exactly that absence into a named skip.  It must not be a
way to skip a test whose tracked fixture was deleted, and it must not skip where the
path is present.
"""
import os
import textwrap

import pytest

import conftest

pytest_plugins = ['pytester']


def test_a_present_path_and_a_matching_glob_are_not_absent(tmp_path):
    (tmp_path / 'evidence' / 'runtime' / 'run-a').mkdir(parents=True)
    (tmp_path / 'evidence' / 'runtime' / 'run-a' / 'events.jsonl').write_text('')
    assert conftest.absent_locally(['evidence/runtime/run-a',
                                    'evidence/runtime/run-*/events.jsonl',
                                    'evidence\\runtime\\run-a'], tmp_path) == []


def test_an_absent_path_and_an_unmatched_glob_are_named(tmp_path):
    (tmp_path / 'evidence').mkdir()
    asked = ['evidence/runtime/run-a', 'build/report.json', 'evidence/runtime/run-*/events.jsonl']
    assert conftest.absent_locally(asked, tmp_path) == asked


@pytest.mark.parametrize('path', ['tests/fixtures/frame.png', 'assets/resource/en/locale.json',
                                  'src/maalimbus/runner.py', 'evidence/../tests/fixtures/x.png',
                                  'evidences/run', ''])
def test_only_the_ignored_local_directories_can_be_declared(path):
    assert conftest.not_local_only([path]) == [path]


@pytest.mark.parametrize('path', ['evidence/runtime/run-a', 'build/report.json',
                                  'dist/MaaLimbus/maafw', 'config/user.json',
                                  'evidence\\runtime\\run-a'])
def test_the_four_local_directories_are_accepted(path):
    assert conftest.not_local_only([path]) == []


def test_every_declared_directory_is_ignored_by_git():
    ignore = open(os.path.join(conftest._CHECKOUT, '.gitignore'), encoding='utf-8').read().splitlines()
    for directory in conftest.LOCAL_ONLY:
        assert directory in ignore or '/' + directory in ignore, directory


def run(pytester, checkout, body):
    """Run ``body`` under the project's guard, with ``checkout`` standing in for the repository.

    pytest drops the outer ``conftest`` from ``sys.modules`` when it loads the inner one,
    so the inner one loads the project's file under a name of its own.
    """
    pytester.makeconftest(textwrap.dedent('''
        import importlib.util
        spec = importlib.util.spec_from_file_location('project_conftest', %r)
        project = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(project)
        project._CHECKOUT = %r
        _local_prerequisites = project._local_prerequisites
        pytest_configure = project.pytest_configure
    ''') % (conftest.__file__, str(checkout)))
    pytester.makepyfile(textwrap.dedent(body))
    return pytester.runpytest_inprocess('-p', 'no:cacheprovider', '-rs')


def test_the_marker_skips_one_test_and_names_the_path(pytester, tmp_path):
    result = run(pytester, tmp_path, '''
        import pytest

        @pytest.mark.needs_local('evidence/runtime/run-a')
        def test_reads_the_run():
            raise AssertionError('ran without its run')

        def test_beside_it_needs_nothing():
            pass
    ''')
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(['*needs local evidence/runtime/run-a, which git ignores*'])


def test_where_the_path_is_present_the_test_runs_and_its_failure_counts(pytester, tmp_path):
    (tmp_path / 'evidence' / 'runtime' / 'run-a').mkdir(parents=True)
    result = run(pytester, tmp_path, '''
        import pytest

        pytestmark = pytest.mark.needs_local('evidence/runtime/run-a')

        def test_regression():
            assert False

        def test_healthy():
            pass
    ''')
    result.assert_outcomes(passed=1, failed=1)


def test_a_tracked_path_fails_instead_of_skipping(pytester, tmp_path):
    result = run(pytester, tmp_path, '''
        import pytest

        @pytest.mark.needs_local('tests/fixtures/no-such-fixture.png')
        def test_reads_a_tracked_fixture():
            pass
    ''')
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(['*needs_local names tests/fixtures/no-such-fixture.png*'])


# ---------------------------------------------------------------------------
# Game bitmaps: the other thing a public checkout never has
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', ['assets/resource/base/image/gifts/abc.png',
                                  'assets/resource/base/image/reward/module-currency.png',
                                  'tests/fixtures/frames/map-20261031-165116/frame-0001.png',
                                  'tests/fixtures/floor-gift-ocr-drift/before.png',
                                  'assets\\resource\\base\\image\\map\\node_badge.png'])
def test_a_game_bitmap_can_be_declared(path):
    assert conftest.not_local_only([path]) == []


@pytest.mark.parametrize('path', ['assets/resource/base/image/reward/provenance.json',
                                  'tests/fixtures/frames/map-20261031-154323/frame-0001.json',
                                  'assets/resource/base/gift-catalog.json',
                                  'assets/misc/Don-Quixote.png',
                                  'tests/fixtures/synthetic.png',
                                  'assets/resource/base/image/../gift-catalog.png'])
def test_a_tracked_file_beside_the_bitmaps_cannot_be_declared(path):
    assert conftest.not_local_only([path]) == [path]


def test_every_bitmap_directory_has_an_ignore_rule_for_its_png_files():
    ignore = open(os.path.join(conftest._CHECKOUT, '.gitignore'), encoding='utf-8').read().splitlines()
    for directory in conftest.LOCAL_BITMAPS:
        assert any(rule.startswith('/' + directory) and rule.endswith('*.png') for rule in ignore), directory


def test_a_missing_game_bitmap_skips_by_name_and_a_missing_tracked_file_still_fails(pytester):
    """The typed error becomes a named skip; a plain FileNotFoundError does not."""
    pytester.makeconftest(textwrap.dedent('''
        import importlib.util
        spec = importlib.util.spec_from_file_location('project_conftest', %r)
        project = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(project)
        pytest_runtest_setup = project.pytest_runtest_setup
        pytest_runtest_call = project.pytest_runtest_call
    ''') % os.path.join(conftest._CHECKOUT, 'tests', 'conftest.py'))
    pytester.makepyfile(textwrap.dedent('''
        import pytest
        from maalimbus import local_assets

        @pytest.fixture
        def catalog():
            raise local_assets.missing('image/gifts/abc.png')

        def test_bitmap_in_the_body():
            raise local_assets.missing('image/themes/pack_search.png')

        def test_bitmap_in_a_fixture(catalog):
            pass

        def test_tracked_file_gone():
            open('tests/fixtures/that-was-tracked.json')

        def test_untouched():
            assert True
    '''))
    result = pytester.runpytest('-rs', '-p', 'no:cacheprovider')
    result.assert_outcomes(passed=1, skipped=2, failed=1)
    result.stdout.fnmatch_lines(['*needs local game assets*image/themes/pack_search.png*',
                                 '*needs local game assets*image/gifts/abc.png*'])
