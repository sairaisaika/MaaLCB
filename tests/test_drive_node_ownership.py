"""Input hit reset belongs to one explicit Runner dispatch, not every input."""
import sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from recognition import AgentTasker
from maalimbus.runner import run_node


class Context:
    def __init__(self):
        self.hits={'MirrorDrive':1,'MirrorEntry':1};self.calls=[];self.reset_ok=True
    def clear_hit_count(self,name):
        self.calls.append(('clear',name))
        if self.reset_ok:self.hits[name]=0
        return self.reset_ok
    def run_task(self,name,override):
        self.calls.append(('run',name,override));ok=not self.hits.get(name,0)
        self.hits[name]=self.hits.get(name,0)+1
        return SimpleNamespace(status=SimpleNamespace(succeeded=ok))


def test_two_owned_runner_dispatches_reenter_without_clearing_other_input_counts():
    context=Context();proxy=AgentTasker(context)
    for _ in range(2):assert run_node(proxy,'MirrorDrive',time.monotonic()+2)['task_succeeded']
    assert [r[:2] for r in context.calls]==[('clear','MirrorDrive'),('run','MirrorDrive')]*2
    assert context.hits['MirrorEntry']==1


@pytest.mark.parametrize('name,override',[
    ('MirrorDrive',None),('MirrorDrive',{'MirrorDrive':{'next':[]}}),
    ('MirrorDrive',{'MirrorDrive':{'next':[],'on_error':[],'max_hit':99}}),
    ('MirrorEntry',{'MirrorEntry':{'next':[],'on_error':[]}})])
def test_unowned_graph_or_other_input_preserves_its_hit(name,override):
    context=Context();assert not AgentTasker(context).post_task(name,override).succeeded
    assert not any(c[0]=='clear' for c in context.calls)


def test_failed_owned_reset_dispatches_nothing():
    context=Context();context.reset_ok=False
    with pytest.raises(RuntimeError,match='owned one-action hit count'):
        run_node(AgentTasker(context),'MirrorDrive',time.monotonic()+2)
    assert context.calls==[('clear','MirrorDrive')]
