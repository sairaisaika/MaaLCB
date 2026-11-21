"""Native scratch lifetime and the one-field MXU compatibility repair."""
import os
from pathlib import Path
import tempfile

import pytest

from maalimbus.native_agent import native_temp,tcp_compatibility


@pytest.fixture
def short_root():
    # pytest's descriptive nested path exceeds Windows AF_UNIX sun_path, and so does
    # the system temp directory under a long account name; see scratch_roots.
    from scratch_roots import short_root as root
    with root('ma-') as path:
        yield path


def test_private_temp_is_writable_unique_and_restores_environment(short_root,monkeypatch):
    monkeypatch.setenv('TEMP','old-temp');monkeypatch.delenv('TMP',raising=False)
    with native_temp(short_root) as first:
        assert first.is_dir() and os.environ['TEMP']==str(first)==os.environ['TMP']
        (first/'socket-placeholder').write_bytes(b'temporary')
    assert not first.exists()
    assert os.environ['TEMP']=='old-temp' and 'TMP' not in os.environ
    with native_temp(short_root) as second:
        assert first!=second


def test_exception_also_restores_environment_and_cleans_owned_directory(short_root):
    before={key:os.environ.get(key) for key in ('TEMP','TMP')}
    with pytest.raises(RuntimeError):
        with native_temp(short_root) as directory:
            raise RuntimeError('injected native startup failure')
    assert not directory.exists()
    assert before=={key:os.environ.get(key) for key in before}


def test_tcp_setting_keeps_all_other_user_values():
    original={'settings':{'tcpCompatMode':False,'autoRunOnLaunch':False},
              'instances':[{'tasks':['saved task']}],'globalOptionValues':{'team2':'saved'}}
    result=tcp_compatibility(original)
    assert result['settings']['tcpCompatMode'] is True
    assert original['settings']['tcpCompatMode'] is False
    result['settings']['tcpCompatMode']=False
    assert result==original


@pytest.mark.parametrize('value',[None,{}, {'settings':[]}])
def test_malformed_config_is_not_replaced_by_defaults(value):
    with pytest.raises(ValueError):tcp_compatibility(value)
