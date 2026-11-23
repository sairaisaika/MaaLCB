"""Starting the Agent does not depend on the project-folder warning line.

On 2026-11-22 the installed app's project folder was 3,003,807,154 bytes, 4 MB over
the 3 GB line. The Agent died in ``native_temp`` with "Workspace budget exceeded",
before any task ran, and the GUI stayed on "Starting". The evidence a run writes was
already checked against free disk space only; the start-up scratch now is too.
"""
import pytest

from maalimbus import native_agent, workspace


def test_the_start_up_scratch_is_reserved_as_a_live_write(monkeypatch):
    from scratch_roots import short_root
    seen = []
    monkeypatch.setattr(workspace, 'size', lambda root: workspace.BUDGET_BYTES + 4_000_000)
    monkeypatch.setattr(native_agent, 'reserve_output',
                        lambda *a, **k: seen.append(workspace._LIVE_WRITES.get()) or workspace.reserve_output(*a, **k))
    with short_root('mn-') as root:
        with native_agent.native_temp(root) as scratch:
            assert scratch.is_dir()
    assert seen == [True]


def test_an_offline_reservation_over_the_line_is_still_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, 'size', lambda root: workspace.BUDGET_BYTES + 4_000_000)
    with pytest.raises(ValueError, match='Workspace budget exceeded'):
        workspace.reserve_output(tmp_path / 'build/x', 1_000_000, application_root=tmp_path)
