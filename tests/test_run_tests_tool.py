"""The test runner must hand pytest's own status through, unpiped."""

from pathlib import Path

from tools import run_tests


class _Done:
    def __init__(self, code):
        self.returncode = code


def test_a_failure_is_passed_through_as_a_failure(monkeypatch):
    monkeypatch.setattr(run_tests.subprocess, 'run', lambda *a, **k: _Done(1))
    assert run_tests.main(['-q']) == 1


def test_success_is_zero(monkeypatch):
    monkeypatch.setattr(run_tests.subprocess, 'run', lambda *a, **k: _Done(0))
    assert run_tests.main(['-q']) == 0


def test_regression_children_do_not_regenerate_workspace_bytecode(monkeypatch):
    seen=[]
    monkeypatch.setattr(run_tests.subprocess, 'run',
                        lambda *a,**kw: seen.append(kw) or _Done(0))
    run_tests.main(['-q'])
    assert seen[0]['env']['PYTHONDONTWRITEBYTECODE']=='1'


def test_the_rule_is_written_down_where_agents_read_it():
    text = (Path(__file__).resolve().parent.parent / 'AGENTS.md').read_text(encoding='utf-8')
    assert 'tools/run_tests.py' in text
    assert '退出码' in text
