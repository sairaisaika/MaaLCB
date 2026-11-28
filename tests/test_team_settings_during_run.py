"""Team settings reach every team that is not in the run in progress.

Live 2026-11-28: every Mirror start since 11-26 resumed a run still in progress, and the
whole settings step was skipped. The rotation then started team 2 inside the same task,
and it deployed the order saved on 11-16, not the one the order reading had written
into its settings on 11-27.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
import recognition  # noqa: E402


def test_a_run_in_progress_keeps_its_own_team_and_the_others_take_their_settings(tmp_path, monkeypatch):
    edits = {'1': dict(keywords='keep', order='10 8 7'), '2': dict(keywords='keep', order='3 4 6 9 5')}
    applied, queues, rows = [], [], []
    monkeypatch.setattr(recognition, 'data_directory', lambda *a: tmp_path)
    monkeypatch.setattr(recognition, 'collect_builds', lambda get_node: dict(edits))
    monkeypatch.setattr(recognition, 'apply_builds', lambda directory, chosen: applied.append(chosen) or sorted(int(k) for k in chosen))
    monkeypatch.setattr(recognition, 'collect_mirror_queue', lambda get_node: queues.append(1) or ('single', [2]))
    journal = SimpleNamespace(record=lambda event, **fields: rows.append(dict(fields, event=event)))
    action = recognition.GlobalSettingsAction(SimpleNamespace(journal=journal))
    context = SimpleNamespace(get_node_data=lambda name: {})
    assert action.apply(context, running_team=1)
    # The running team keeps its systems and starlight; its order is applied with the rest.
    assert applied == [{'1': dict(keywords='keep', order='10 8 7'), '2': edits['2']}] and queues == []
    assert rows[-1]['slots'] == [1, 2] and rows[-1]['kept_for_the_run'] == 1
    # With no run in progress every team and the queue are applied, as before.
    applied.clear()
    monkeypatch.setattr(recognition, 'TaskPreferences', lambda directory: SimpleNamespace(set_mirror_queue=lambda *a: None))
    assert action.apply(context)
    assert applied == [edits] and queues == [1]


def test_the_start_of_a_task_applies_the_other_teams_when_a_run_is_in_progress():
    source = (Path(__file__).resolve().parents[1] / 'agent/recognition.py').read_text(encoding='utf-8')
    assert "GlobalSettingsAction(self.recognition).apply(context,running_team=active.get('team'))" in source
    assert '跳过开新局的设置应用' not in source


def test_the_running_teams_order_changes_but_its_systems_do_not(tmp_path):
    from maalimbus.global_settings import apply_builds
    from maalimbus.storage import ProfileStore, write_json
    apply_builds(tmp_path, {'2': dict(keywords=['Charge'], order='3 4 9 1 7 2 12 5 8 10 11 6')})
    write_json(tmp_path / 'user-run-ledger.json', dict(active=dict(id='run', team=2)))
    # The order the user recorded for team 2 (pi-20261128 screenshot): 3 2 12 4 9 6 10 5 11 1 7 8.
    assert apply_builds(tmp_path, {'2': dict(keywords='keep', order='3 2 12 4 9 6 10 5 11 1 7 8')}) == [2]
    team = next(t for t in ProfileStore(tmp_path / 'user-team-profiles.json').load() if t.slot == 2)
    assert team.deployment[:4] == ('Don Quixote', 'Faust', 'Gregor', 'Ryoshu')
    import pytest
    with pytest.raises(ValueError, match='Finish the active run'):
        apply_builds(tmp_path, {'2': dict(keywords=['Tremor'], order='keep')})
