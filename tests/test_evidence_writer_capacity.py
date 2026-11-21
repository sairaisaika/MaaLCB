"""One serialization and actual byte peaks apply to all evidence/state writers."""
import json

import pytest

from maalimbus import documents, runtime_paths, storage, workspace


def test_document_refuses_before_overwriting_existing_evidence(tmp_path, monkeypatch):
    target = tmp_path / 'old.json'
    target.write_bytes(b'original evidence')
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', workspace.size(tmp_path))
    with pytest.raises(ValueError, match='Workspace budget exceeded'):
        documents.write_document(target, {'larger': '确认' * 100}, application_root=tmp_path)
    assert target.read_bytes() == b'original evidence'


def test_document_counts_exact_utf8_bytes_without_windows_newline_expansion(tmp_path, monkeypatch):
    target = tmp_path / 'result.json'
    data = {'message': '确认', 'facts': [1, 2, 3]}
    expected = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', len(expected))
    documents.write_document(target, data, application_root=tmp_path)
    assert target.read_bytes() == expected
    assert workspace.size(tmp_path) == len(expected)


def test_atomic_state_write_budgets_full_temporary_payload_before_touching_old_state(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, 'ROOT', tmp_path)
    target = tmp_path / 'state.json'
    original = b'{"pending":true}'
    target.write_bytes(original)
    replacement = {'pending': None}
    payload = json.dumps(replacement, ensure_ascii=False, indent=2).encode('utf-8')
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', len(original) + len(payload) - 1)
    with pytest.raises(ValueError, match='Workspace budget exceeded'):
        storage.write_json(target, replacement)
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', len(original) + len(payload))
    storage.write_json(target, replacement)
    assert target.read_bytes() == payload


def test_optional_duplicate_copy_cannot_spend_bytes_reserved_for_original_evidence(tmp_path, monkeypatch):
    content = {'steps': [{'reason': 'observed', 'passed': False}]}
    expected = (json.dumps(content, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    monkeypatch.setattr(workspace, 'BUDGET_BYTES', len(expected))
    primary = tmp_path / 'session-result.json'
    duplicate = tmp_path / 'duplicate.json'
    documents.write_document(primary, content, application_root=tmp_path)
    with pytest.raises(ValueError):
        documents.write_document(duplicate, content, application_root=tmp_path)
    assert primary.read_bytes() == expected and not duplicate.exists()
