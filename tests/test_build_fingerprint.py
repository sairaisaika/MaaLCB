"""A build stamp must distinguish dirty source from the same commit identifier."""
import subprocess

from maalimbus.build_fingerprint import source_snapshot


def test_dirty_source_and_new_modules_invalidate_the_snapshot(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    src=tmp_path/'src';src.mkdir();module=src/'work.py';module.write_text('value=1\n')
    original=source_snapshot(tmp_path)
    assert set(original)=={'src/work.py'}
    module.write_text('value=2\n')
    assert original!=source_snapshot(tmp_path)
    second=source_snapshot(tmp_path)
    (src/'another.py').write_text('new=3\n')
    assert second!=source_snapshot(tmp_path)
    assert 'src/another.py' in source_snapshot(tmp_path)


def test_documents_and_private_configuration_are_not_public_build_inputs(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'src').mkdir();(tmp_path/'src/core.py').write_text('value=1')
    before=source_snapshot(tmp_path)
    (tmp_path/'config').mkdir();(tmp_path/'config/secret.json').write_text('{}')
    (tmp_path/'notes.md').write_text('new documentation')
    assert before==source_snapshot(tmp_path)
