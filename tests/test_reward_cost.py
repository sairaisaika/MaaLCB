import copy,json
from pathlib import Path
import pytest
from maalimbus.reward_cost import page_anchors,combine_evidence
from maalimbus.vision import Text

FRAME=Path(__file__).resolve().parents[1]/'evidence/runtime/window-20261008-144554/frame-0458.json'

def readings():
    return [dict(purpose=purpose,results=[dict(score=score,**extra)])
        for purpose,score,extra in [('currency',.99,{}),('deduction',.99,{}),
            ('cost_digit_a',.99,dict(text='6')),('cost_digit_b',.99,dict(text='6')),
            ('weekly_count',.99,dict(text='1/3'))]]

def test_real_page_and_consistent_evidence_only_prove_offer():
    data=json.loads(FRAME.read_text());records=[Text(t['text'],tuple(t['box']),t['score']) for t in data['ocr']]
    assert page_anchors(records,data['size'])
    assert combine_evidence(readings())==dict(currency='enkephalin_modules',cost=6,weekly=1)

@pytest.mark.parametrize('purpose',['currency','deduction','cost_digit_a','cost_digit_b','weekly_count'])
def test_missing_low_confidence_duplicate_results_refuse(purpose):
    rows=readings();index=next(i for i,r in enumerate(rows) if r['purpose']==purpose)
    for change in ('missing','low','duplicate'):
        changed=copy.deepcopy(rows)
        if change=='missing':changed.pop(index)
        if change=='low':changed[index]['results'][0]['score']=.89
        if change=='duplicate':changed[index]['results']*=2
        assert combine_evidence(changed) is None

@pytest.mark.parametrize('text',['18','0','-6','6?'])
def test_disagreement_or_invalid_digit_never_implies_cost(text):
    rows=readings();rows[3]['results'][0]['text']=text
    assert combine_evidence(rows) is None


def test_five_module_zero_weekly_offer_still_requires_matching_digits_and_sign():
    rows=readings()
    rows[2]['results'][0]['text']=rows[3]['results'][0]['text']='5'
    rows[4]['results'][0]['text']='0/3'
    assert combine_evidence(rows)==dict(currency='enkephalin_modules',cost=5,weekly=0)
    assert combine_evidence([r for r in rows if r['purpose']!='deduction']) is None
    rows[2]['results'][0]['text']='6'
    assert combine_evidence(rows) is None

def two_digit_readings():
    # pi-20261120-193352/frame-0269: a hard clear with all three weekly bonuses on.
    rows=readings()
    for row in rows[:2]:row['layout']='two_digit'
    rows[2]['results'][0]['text']=rows[3]['results'][0]['text']='18'
    rows[4]['results'][0]['text']='3/3'
    return rows


def test_two_digit_cost_is_an_offer_only_in_the_two_digit_layout():
    assert combine_evidence(two_digit_readings())==dict(currency='enkephalin_modules',cost=18,weekly=3)
    # The same digits beside marks found where a one-digit cost puts them disagree
    # about where the row is.
    rows=two_digit_readings()
    for row in rows[:2]:row['layout']='one_digit'
    assert combine_evidence(rows) is None
    rows=two_digit_readings();rows[1]['layout']='one_digit'
    assert combine_evidence(rows) is None
    rows=readings()
    for row in rows[:2]:row['layout']='two_digit'
    assert combine_evidence(rows) is None
    rows=two_digit_readings();rows[0]['layout']='three_digit'
    assert combine_evidence(rows) is None


@pytest.mark.needs_local('assets/resource/base/image/reward/module-currency.png',
                         'assets/resource/base/image/reward/deduction-sign.png',
                         'assets/resource/base/image/reward/module-currency-two-digit.png',
                         'assets/resource/base/image/reward/deduction-sign-two-digit.png')
def test_the_retained_two_digit_frame_passes_the_page_gate_and_carries_its_templates():
    import hashlib
    root=Path(__file__).resolve().parents[1]
    proof=json.loads((root/'assets/resource/base/image/reward/provenance.json').read_text())
    for entry in proof['templates']+proof['two_digit_cost']['templates']:
        template=root/entry['template'].replace('\\','/')
        assert hashlib.sha256(template.read_bytes()).hexdigest()==entry['sha256']
    from maalimbus.reward_cost import LAYOUTS
    assert {name for row in LAYOUTS for name in (row[1],row[3])}=={
        'reward/'+Path(entry['template'].replace('\\','/')).name
        for entry in proof['templates']+proof['two_digit_cost']['templates']}
    for _layout,_currency,currency_roi,_sign,sign_roi in LAYOUTS[1:]:
        for (x,y,w,h),entry in zip((currency_roi,sign_roi),proof['two_digit_cost']['templates']):
            tx,ty,tw,th=entry['roi']
            assert x<=tx and y<=ty and tx+tw<=x+w and ty+th<=y+h


@pytest.mark.parametrize('title',['Exploration Reward','Floor 5','To Window','Claim','Weekly','Bonuses'])
def test_missing_independent_page_anchor_refuses(title):
    data=json.loads(FRAME.read_text());records=[Text(t['text'],tuple(t['box']),t['score'])
        for t in data['ocr'] if t['text']!=title]
    assert not page_anchors(records,data['size'])
