"""The payout's last step: the loader between the final receipt and the main menu.

Kept apart from `test_reward_task.py`. That module names a retained run, and when these
cases were written the retired-evidence guard in `conftest.py` skipped a whole module
once a run it named was gone: every test there had been skipped since
`window-20261008-172705` was retired. The guard has decided per test since 2026-11-20
(`tests/test_retired_evidence_guard.py`), so the split is history, not a requirement.
These cases need no retained frame and must keep running.
"""
from types import SimpleNamespace

from maalimbus.reward_task import execute
from maalimbus.storage import write_json

def _returning_fixture(tmp_path,monkeypatch,transaction,scenes):
    import maalimbus.reward_task as task
    config=tmp_path/'config';directory=tmp_path/'frames';directory.mkdir()
    write_json(config/'user-run-ledger.json',dict(active=dict(id='run',floors=[1,2,3,4,5],
                                                               victory=True,reward=False)))
    if transaction is not None:write_json(config/'user-reward-claim-transaction.json',transaction)
    frames=iter([dict(scene=scene,size=[1920,1080],ocr=[]) for scene in scenes])
    monkeypatch.setattr(task.runner,'observe',lambda observer,deadline=None,**kwargs:next(frames))
    monkeypatch.setattr(task.runner,'frame_file',lambda path:directory/'frame-0003.json')
    monkeypatch.setattr(task,'LOADER_POLL_SECONDS',0)
    finished=[]
    monkeypatch.setattr(task,'finish',lambda config,scope,home,journal=None:(
        finished.append((scope,home)) or dict(passed=True,reason='mirror_payout_and_home_verified',
                                               reward_received=True)))
    clicks=[]
    result=execute(config,directory,SimpleNamespace(directory=directory),
                   SimpleNamespace(click=lambda *point:clicks.append(point)),
                   SimpleNamespace(record=lambda *a,**k:None))
    return result,clicks,finished,directory


def test_the_loader_after_the_last_receipt_is_waited_through_to_home(tmp_path,monkeypatch):
    # live packaged-mirror-20261120-205012: every paid input proven, then two LOADING
    # frames, and the payout stopped two seconds before HOME.
    acknowledged=dict(scope='run',confirm_sent=True,receipt_ack_sent=True,pass_ack_sent=True,
                      completed=False,pending='pass_ack')
    result,clicks,finished,directory=_returning_fixture(
        tmp_path,monkeypatch,acknowledged,['LOADING']*7+['HOME'])
    assert result['passed'] and result['reward_received'] and not result['input_sent']
    assert not clicks and finished==[('run',directory/'frame-0003.json')]


def test_the_main_menu_still_sliding_in_is_read_again_until_it_is_home(tmp_path,monkeypatch):
    # live pi-20261125-161038 (the fourth run, cleared): the loader ended and the next
    # frame was the main menu mid-slide, read as no page; the payout stopped there.
    acknowledged=dict(scope='run',confirm_sent=True,receipt_ack_sent=True,pass_ack_sent=True,
                      completed=False,pending='pass_ack')
    result,clicks,finished,directory=_returning_fixture(
        tmp_path,monkeypatch,acknowledged,['LOADING','LOADING','UNKNOWN','UNKNOWN','HOME'])
    assert result['passed'] and result['reward_received'] and not result['input_sent']
    assert not clicks and finished==[('run',directory/'frame-0003.json')]


def test_a_page_that_stays_unreadable_still_stops_and_nothing_is_pressed(tmp_path,monkeypatch):
    import maalimbus.reward_task as task
    acknowledged=dict(scope='run',confirm_sent=True,receipt_ack_sent=True,completed=False)
    result,clicks,finished,_=_returning_fixture(
        tmp_path,monkeypatch,acknowledged,['UNKNOWN']*(task.RETURN_UNREADABLE_READS+1))
    assert not result['passed'] and result['reason']=='Reward page or successor not proven'
    assert not clicks and not finished


def test_an_unreadable_page_before_this_runs_receipt_is_not_a_wait(tmp_path,monkeypatch):
    for transaction in (None,dict(scope='run',confirm_sent=True,receipt_ack_sent=False)):
        folder=tmp_path/str(id(transaction));folder.mkdir()
        result,clicks,finished,_=_returning_fixture(folder,monkeypatch,transaction,['UNKNOWN','HOME'])
        assert not result['passed'] and result['reason']=='Reward page or successor not proven'
        assert not clicks and not finished


def test_a_loader_before_this_runs_receipt_is_not_a_wait(tmp_path,monkeypatch):
    for transaction in (None,dict(scope='other',confirm_sent=True,receipt_ack_sent=True),
                        dict(scope='run',confirm_sent=True,receipt_ack_sent=False),
                        dict(scope='run',confirm_sent=True,receipt_ack_sent=True,completed=True)):
        folder=tmp_path/str(id(transaction));folder.mkdir()
        result,clicks,finished,_=_returning_fixture(folder,monkeypatch,transaction,['LOADING','HOME'])
        assert not result['passed'] and result['reason']=='Reward page or successor not proven'
        assert not clicks and not finished


def test_a_loader_that_never_ends_stops_at_the_deadline(tmp_path,monkeypatch):
    import itertools
    import maalimbus.reward_task as task
    acknowledged=dict(scope='run',confirm_sent=True,receipt_ack_sent=True,completed=False)
    clock=itertools.count(0,40)
    monkeypatch.setattr(task.time,'monotonic',lambda:next(clock))
    result,clicks,finished,_=_returning_fixture(tmp_path,monkeypatch,acknowledged,['LOADING']*50)
    assert not result['passed'] and 'before the deadline' in result['reason']
    assert not clicks and not finished
