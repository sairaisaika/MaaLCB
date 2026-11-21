"""D105: the row names the picture, and the writer resolves that name safely.

The first live attempt after D105 died with
`callback_failed: 'MapObservation' object has no attribute 'directory'` -- the helper
was right and the receiver was wrong. That is the failure this file exists to prevent.
"""
import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'agent/recognition.py'


def _helper():
    text = SOURCE.read_text(encoding='utf-8')
    start = text.index('def frame_identity(')
    end = text.index('\ndef in_roi(')
    namespace = {'Path': Path, 'json': json}
    exec(text[start:end], namespace)
    return namespace['frame_identity']


def test_the_identity_is_the_hash_the_frame_record_carries(tmp_path):
    # This helper reads a recorder field; it does not re-recognise a historical
    # screenshot. Keep that contract independent of runtime evidence retention.
    want = 'a' * 64
    (tmp_path / 'frame-0001.json').write_text(
        json.dumps({'image_sha256': want}), encoding='utf-8')
    assert _helper()(tmp_path, 'frame-0001') == want


def test_malformed_or_hashless_frame_records_have_no_identity(tmp_path):
    (tmp_path / 'broken.json').write_text('{', encoding='utf-8')
    (tmp_path / 'hashless.json').write_text('{}', encoding='utf-8')
    helper = _helper()
    assert helper(tmp_path, 'broken') is None
    assert helper(tmp_path, 'hashless') is None


def test_a_missing_or_unknown_name_is_not_an_exception():
    helper = _helper()
    directory = REPO / 'evidence/runtime/packaged-mirror-20261024-073605'
    assert helper(directory, None) is None
    assert helper(directory, 'frame-9999') is None
    assert helper(REPO / 'build', 'nope') is None


def test_the_writers_never_read_an_attribute_the_action_does_not_have():
    """`self.directory` lives on the Recorder, not on the action (the live crash)."""
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    # attributes assigned on the action classes themselves
    assigned = set()
    for name in ('MapObservation', 'BattleObservation'):
        for node in ast.walk(classes[name]):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
                        and target.value.id == 'self':
                    assigned.add(target.attr)
    for name in ('MapObservation', 'BattleObservation'):
        text = ast.unparse(classes[name])
        for line in text.splitlines():
            if 'frame_identity(' in line and 'self.directory' in line:
                raise AssertionError(
                    f'{name} reads self.directory, which the action does not own: {line.strip()}')
