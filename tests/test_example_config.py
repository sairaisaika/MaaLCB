"""The example configuration under docs/examples/config loads through the real loaders.

The examples are synthetic.  A stranger copies them into the private ``config/``
directory, so they must stay valid for the code that reads that directory.
"""
import shutil
from pathlib import Path

from maalimbus.storage import SINNERS, ProfileStore
from maalimbus.task_preferences import TaskPreferences

EXAMPLES = Path(__file__).resolve().parents[1] / 'docs/examples/config'


def copied(tmp_path):
    for name in ('user-team-profiles.json', 'user-task-settings.json'):
        shutil.copyfile(EXAMPLES / name, tmp_path / name)
    return tmp_path


def test_the_example_teams_load_as_saved_teams():
    teams = ProfileStore(EXAMPLES / 'user-team-profiles.json').load()
    assert [team.slot for team in teams] == [1, 2]
    for team in teams:
        assert sorted(team.deployment) == sorted(SINNERS)
        assert team.keywords and team.grace_budget == 0


def test_the_example_task_settings_reference_the_example_teams(tmp_path):
    preferences = TaskPreferences(copied(tmp_path))
    value = preferences.load()
    assert value['mirror'] == dict(difficulty='hard', team_mode='rotation', teams=[1, 2])
    assert preferences.build_for('mirror', rotation=1).slot == 2
    assert preferences.build_for('experience').slot == 1


def test_a_task_setting_that_names_an_unsaved_team_is_refused(tmp_path):
    import json

    import pytest

    directory = copied(tmp_path)
    path = directory / 'user-task-settings.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['mirror']['teams'] = [1, 7]
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='saved teams'):
        TaskPreferences(directory).load()
