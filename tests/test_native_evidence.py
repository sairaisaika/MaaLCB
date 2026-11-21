"""The host must acknowledge image suppression before controller work starts."""
from types import SimpleNamespace

import pytest

from maalimbus.native_evidence import configure_host


def api(*, server=False, refused=None):
    calls=[]
    def call(name):
        def method(value):
            calls.append((name,value))
            return name!=refused
        return method
    return calls,dict(library_api=SimpleNamespace(is_agent_server=lambda:server),
        toolkit_api=SimpleNamespace(init_option=call('init_option')),
        tasker_api=SimpleNamespace(**{name:call(name) for name in
            ('set_save_draw','set_save_on_error','set_debug_mode')}))


def test_host_reapplies_options_after_toolkit_defaults_without_disabling_journal(tmp_path):
    calls,options=api()
    result=configure_host(tmp_path,**options)
    assert calls==[('init_option',tmp_path),('set_save_draw',False),
                   ('set_save_on_error',False),('set_debug_mode',False)]
    assert result['canonical_journal_enabled'] and result['native_text_logs']
    assert not result['native_debug_images']


def test_agent_cannot_pretend_to_configure_the_controlling_host(tmp_path):
    calls,options=api(server=True)
    with pytest.raises(ValueError,match='controlling host'):
        configure_host(tmp_path,**options)
    assert not calls


@pytest.mark.parametrize('refused',['init_option','set_save_draw','set_save_on_error','set_debug_mode'])
def test_unacknowledged_policy_cannot_fall_through_to_unbounded_output(tmp_path,refused):
    calls,options=api(refused=refused)
    with pytest.raises(RuntimeError):configure_host(tmp_path,**options)
    assert calls[-1][0]==refused
