from types import SimpleNamespace

from maalimbus.jobs import wait_task


def test_dead_agent_cancels_existing_task_without_waiting_for_run_deadline():
    job=SimpleNamespace(done=False,succeeded=False);stops=[]
    def stop():
        stops.append('stop');job.done=True
        return SimpleNamespace(done=True,succeeded=True)
    result=wait_task(SimpleNamespace(post_stop=stop),job,deadline=5400,
                     producer_alive=lambda:False,clock=lambda:0,
                     sleep=lambda _: (_ for _ in ()).throw(AssertionError('unnecessary wait')))
    assert stops==['stop'] and result['stop_confirmed']
    assert result['producer_exited'] and not result['task_succeeded']
    assert not result['timed_out'] and not result['interrupted']
    assert result['error']=='producer_exited_before_task_completion'


def test_completed_task_does_not_treat_normal_producer_exit_as_failure():
    job=SimpleNamespace(done=True,succeeded=True)
    result=wait_task(None,job,deadline=5400,producer_alive=lambda:False)
    assert result['task_succeeded'] and 'producer_exited' not in result


def test_dead_producer_is_not_proof_that_native_stop_completed():
    job=SimpleNamespace(done=False,succeeded=False)
    result=wait_task(SimpleNamespace(post_stop=lambda:SimpleNamespace(done=True,succeeded=True)),
                     job,deadline=5400,producer_alive=lambda:False)
    assert not result['stop_confirmed']
    assert result['verdict']=='the_controller_did_not_confirm_the_stop'
    assert not result['task_succeeded']
