import pytest
from maalimbus.public_privacy import findings,require_public,public_file

def test_export_refuses_user_path_without_echoing_identifier(tmp_path):
    p=tmp_path/'sample.md';p.write_text('path '+'C:/Users/'+'private-example/session',encoding='utf-8')
    result=findings([p]);assert result[0]['category']=='local_user_path'
    assert 'private-example' not in str(result)
    with pytest.raises(ValueError) as error:require_public([p])
    assert 'private-example' not in str(error.value)

def test_redacted_path_and_schema_field_are_not_real_identifiers(tmp_path):
    p=tmp_path/'safe.md';p.write_text('C:/Users/<user>/session\nuser_id: string',encoding='utf-8')
    assert findings([p])==[]
    p.write_text('UID: '+'A'+'123456789',encoding='utf-8')
    assert findings([p])[0]['category']=='player_id_literal'
    p.write_text('{"uid": "'+'A'+'123456789'+'"}',encoding='utf-8')
    assert findings([p])[0]['category']=='player_id_literal'

def test_local_learning_policy_and_logs_are_not_public_files(tmp_path):
    for name in ('neural-learning.local.json','events.jsonl','run.log','cert.p12','backup.PPK'):
        p=tmp_path/name;p.touch();assert not public_file(p)


def test_private_rules_cover_public_git_archive_even_for_tracked_files(tmp_path):
    import io
    from pathlib import Path
    import subprocess
    import zipfile

    checkout = Path(__file__).resolve().parents[1]
    for name in ('.gitignore', '.gitattributes'):
        (tmp_path / name).write_bytes((checkout / name).read_bytes())

    def git(*args):
        return subprocess.run(
            ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args],
            cwd=tmp_path, check=True, capture_output=True).stdout

    private = ['.codex/hooks.json', 'tools/local/probe.py', 'tests/local/probe.py',
               'config/runtime.ini', 'evidence/snapshot.png', 'PROJECT.md',
               'assets/model/secret.local.json', 'tools/certs/identity.p12',
               'tools/certs/identity.ppk', 'assets/model/.env']
    public = ['docs/acceptance.md', 'tests/fixtures/public.png', 'tools/probe.py']
    for name in private + public:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'fixture')

    git('init', '-q')
    assert set(git('check-ignore', '--', *private).decode().splitlines()) == set(private)
    git('add', '-f', '--', '.gitignore', '.gitattributes', *private, *public)
    git('commit', '-qm', 'Test archive rule for tracked private files')
    with zipfile.ZipFile(io.BytesIO(git('archive', '--format=zip', 'HEAD'))) as archive:
        assert set(public) <= set(archive.namelist())
        assert not set(private).intersection(archive.namelist())


@pytest.mark.parametrize('prefix', ['ghp_', 'ghs_', 'github_pat_', 'sk-proj-'])
def test_credential_literals_are_refused_without_echo(tmp_path,prefix):
    path=tmp_path/'client.cfg'
    token=prefix+'AbCdeF0123'*5
    path.write_text('value='+token,encoding='utf-8')
    with pytest.raises(ValueError,match='credential_literal') as error:
        require_public([path])
    assert token not in str(error.value)
    path.write_text('value="'+prefix+'<redacted>"',encoding='utf-8')
    assert findings([path])==[]


def test_device_privacy_filters_literal_fingerprints_but_allows_examples(tmp_path):
    p=tmp_path/'device.json'
    p.write_text('{"adb_serial":"127.0.0.1:16416","mumu_ip":"192.0.2.2",'
                 '"device_id":"unit-test-device"}',encoding='utf-8')
    assert findings([p])==[]
    import json
    for field,value in (('mumu_ip','10.'+'23.45.67'),
                        ('mac_address','ab:cd:ef:'+'01:23:45'),
                        ('adb_serial','01234'+'789abc'),
                        ('device_uuid','12345678-1234-'+'abcd-abcd-123456789012')):
        content=json.dumps({field:value})
        p.write_text(content,encoding='utf-8')
        findings_found=findings([p])
        assert [f['category'] for f in findings_found]==['device_identifier']
        assert content not in str(findings_found)

    p = tmp_path/'device.ini'
    p.write_text('adapter='+'ab-cd-ef-'+'01-23-45',encoding='utf-16')
    assert [entry['category'] for entry in findings([p])]==['device_identifier']

def test_source_export_refuses_before_zip_and_excludes_local_policy(tmp_path,monkeypatch):
    import subprocess,sys,zipfile
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    import build_windows_package as package
    monkeypatch.setattr(package,'ROOT',tmp_path)
    for name in ('src','agent','tools','tests','docs','assets','desktop','THIRD_PARTY_NOTICES'):
        (tmp_path/name).mkdir()
    for name in ('README.md','README_en.md','LICENSE','pyproject.toml','PROJECT.md','.gitignore'):
        (tmp_path/name).write_text('public',encoding='utf-8')
    private=tmp_path/'assets'/'neural-learning.local.json';private.write_text('private account policy')
    (tmp_path/'PROJECT.md').write_text('C:/Users/'+'private-example/handoff')
    (tmp_path/'.codex').mkdir()
    (tmp_path/'.codex'/'hooks.json').write_text('C:/Users/'+'private-example/hooks')
    for root in ('tests', 'tools'):
        (tmp_path/root/'local').mkdir()
        (tmp_path/root/'local'/'probe.py').write_text('C:/Users/'+'private-example/probe')
    document=tmp_path/'docs'/'example.md';document.write_text('C:/Users/'+'private-example/proof')
    def git(*args):
        subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args],
                       cwd=tmp_path,check=True,capture_output=True)

    git('init','-q')
    git('add','.')
    git('commit','-qm','Fixture with a private field')
    output=tmp_path/'source.zip'
    with pytest.raises(ValueError):package.copy_public_sources(output)
    assert not output.exists()
    document.write_text('C:/Users/<user>/proof')
    git('add','docs/example.md')
    git('commit','-qm','Redacted fixture')
    document.write_text('uncommitted local text')
    (tmp_path/'docs'/'untracked-note.ini').write_text('C:/Users/'+'private-example/untracked')
    package.copy_public_sources(output)
    with zipfile.ZipFile(output) as archive:
        assert 'assets/neural-learning.local.json' not in archive.namelist()
        assert 'PROJECT.md' not in archive.namelist()
        assert '.codex/hooks.json' not in archive.namelist()
        assert 'tests/local/probe.py' not in archive.namelist()
        assert 'tools/local/probe.py' not in archive.namelist()
        assert 'docs/example.md' in archive.namelist()
        assert archive.read('docs/example.md').strip() == b'C:/Users/<user>/proof'
        assert 'docs/untracked-note.ini' not in archive.namelist()
