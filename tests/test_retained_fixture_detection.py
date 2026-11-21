"""Retired fixtures must not silently skip unrelated unit tests."""
from conftest import retained_dependencies


def test_comments_and_docstrings_are_not_fixture_dependencies():
    source='''"""A previous run used evidence/runtime/window-20261001-120000/frame.json."""
# evidence/runtime/window-20261002-120000/frame.json
def f():
    """evidence/runtime/window-20261003-120000/frame.json"""
    return True
'''
    assert retained_dependencies(source)==frozenset()


def test_a_declared_retained_frame_is_a_dependency():
    source="FRAME=ROOT/'evidence/runtime/packaged-mirror-20261031-210833/frame-0067.json'"
    assert retained_dependencies(source)=={'packaged-mirror-20261031-210833'}


def test_a_synthetic_temporary_run_is_not_a_real_fixture():
    source="proof='evidence/runtime/run-a/frame-0001.json'"
    assert retained_dependencies(source)==frozenset()
