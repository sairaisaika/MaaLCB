import hashlib
import json

from agent.recognition import Journal


def sample(journal, pixels, *, released=True, owner='mirror_loader'):
    journal.begin_step()
    journal.index += 1
    name = f'frame-{journal.index:04d}'
    path = journal.directory / name
    path.with_suffix('.png').write_bytes(pixels)
    path.with_suffix('.json').write_text(json.dumps({
        'scene': 'LOADING', 'image_sha256': hashlib.sha256(pixels).hexdigest(),
    }))
    if released:
        journal.finish_diagnostic_sample((owner, 'LOADING', name, hashlib.sha256(pixels).hexdigest()))
    return path


def test_declared_wait_releases_middle_png_and_preserves_metadata(tmp_path):
    journal = Journal(tmp_path)
    first = sample(journal, b'first')
    middle = sample(journal, b'middle')
    last = sample(journal, b'last')
    assert first.with_suffix('.png').read_bytes() == b'first'
    assert not middle.with_suffix('.png').exists()
    assert middle.with_suffix('.json').is_file()
    assert last.with_suffix('.png').read_bytes() == b'last'
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == [
        'diagnostic_sample_release_intent', 'diagnostic_sample_released',
    ]
    assert rows[-1]['owner'] == 'mirror_loader'
    assert rows[-1]['record_sha256'] == hashlib.sha256(middle.with_suffix('.json').read_bytes()).hexdigest()
    assert rows[-1]['bytes'] == len(b'middle')


def test_wait_retains_bracketed_visual_change(tmp_path):
    journal = Journal(tmp_path)
    sample(journal, b'first')
    middle = sample(journal, b'middle')
    sample(journal, b'first')
    assert middle.with_suffix('.png').read_bytes() == b'middle'


def test_action_or_incomplete_step_breaks_diagnostic_series(tmp_path):
    journal = Journal(tmp_path)
    first = sample(journal, b'first')
    other = sample(journal, b'uncertainty', released=False)
    sample(journal, b'restart')
    sample(journal, b'latest')
    assert first.with_suffix('.png').is_file()
    assert other.with_suffix('.png').read_bytes() == b'uncertainty'


def test_new_wait_owner_does_not_release_previous_owner_frame(tmp_path):
    journal = Journal(tmp_path)
    sample(journal, b'first')
    middle = sample(journal, b'middle')
    sample(journal, b'new-diagnostic-series', owner='cold_start_loader')
    assert middle.with_suffix('.png').read_bytes() == b'middle'


def test_current_transaction_pin_wins_over_a_diagnostic_release(tmp_path, monkeypatch):
    from agent import recognition
    monkeypatch.setattr(recognition, 'ROOT', tmp_path)
    journal = Journal(tmp_path / 'evidence/runtime/current')
    sample(journal, b'first')
    middle = sample(journal, b'middle')
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'user-transaction.json').write_text(json.dumps({
        'pending': {'before': str(middle.with_suffix('.json'))},
    }))
    sample(journal, b'last')
    assert middle.with_suffix('.png').read_bytes() == b'middle'
