from maalimbus.decision_log import lines, signature
from maalimbus.event_log import report

def test_rule_components_and_direction_visible_in_console_and_finished_log():
    row=dict(title='Example',score=20,score_components=dict(trial=60,synergy=-40,already_owned=0,visible_benefit=0))
    text=lines('floor_gift_ranking',dict(ranking=[row]))
    assert '越低' in text[0] and '模型未参与' in text[0]
    assert 'trial=+60' in text[1] and 'synergy=-40' in text[1] and '最终分=20' in text[1]
    assert text[1] in report(dict(decisions=[dict(lines=text)]))

def test_shadow_prediction_does_not_claim_to_choose_purchase():
    text=lines('shop_decision_ranking',dict(currency=2000,reserve=300,refresh_limit=2,reason='gift_plan',
        ranking=[dict(name='Black Card',price=150,manual_weight=95,score=7,status='可购买',chosen=True)],
        learning=dict(neural_value_shadow_applied=True)))
    assert '手动权重=95' in text[1] and '队列分=7' in text[1] and '选择购买' in text[1]
    assert '不改变购买顺序' in text[-1]

def test_theme_weight_is_the_actual_score_not_neural():
    row=dict(name='Pack',weight=40,reason='team_weight')
    text=lines('theme_pack_recommendation',dict(chosen=row,ranking=[row]))
    assert '最终分=40' in text[1] and '选择' in text[1]


def test_neural_scores_are_bound_to_each_visible_offer_and_labelled_shadow():
    row=dict(name='Gift',price=150,manual_weight=95,score=7,status='可购买')
    learning=dict(neural_value_shadow_applied=True,scores=[dict(name='Gift',price=150,
        predicted_review_value=.75),dict(name='Gift',price=200,predicted_review_value=.1)])
    text=lines('shop_decision_ranking',dict(ranking=[row],learning=learning))
    assert '影子预测值=0.7500' in text[1] and '神经排序值' not in text[1]
    learning['neural_value_ranked']=True
    text=lines('shop_decision_ranking',dict(ranking=[row],learning=learning))
    assert '神经排序值=0.7500' in text[1]


def test_skill_preview_is_visible_without_claiming_payment_or_unknown_price():
    event='shop_skill_choices_observed'
    observed=dict(sinner='Don Quixote',counts=(3,2,1),coins=2283,reserve_coins=500,active_mode='off',
        frame='frame-0230',quotes=[dict(from_tier=1,to_tier=2,price=None,tiers_verified=False),
                                   dict(from_tier=2,to_tier=3,price=75,tiers_verified=True)],
        previews=dict(keep_one_each=dict(from_tier=2,price=75,counts_after=(3,1,2),coins_after=2208)))
    rendered=lines(event,observed)
    assert '当前 关闭' in rendered[0] and '人格或前排证据不足' in rendered[0]
    assert '报价=未读到' in rendered[1] and '等级未核' in rendered[1]
    assert '预演' in rendered[-1] and '预测张数=3/1/2' in rendered[-1] and '预测余额=2208' in rendered[-1]
    assert rendered[-1] in report(dict(decisions=[dict(lines=rendered)]))
    assert signature(event,observed)==signature(event,dict(observed,frame='frame-0231'))
    assert signature(event,observed)!=signature(event,dict(observed,coins=2208))


def test_skill_selection_wait_and_receipt_have_distinct_log_messages():
    intent=lines('shop_skill_selection_intent',dict(selection=dict(from_tier=2,price=75)))
    waiting=lines('shop_skill_receipt_unproven',dict(page='SHOP',frame='frame-0012',error='unknown',attempt=1))
    settled=lines('shop_skill_receipt_verified',dict(receipt=dict(sinner='Don Quixote',
        coins_before=2283,coins_after=2208,counts_before=(3,2,1),counts_after=(3,1,2))))
    assert '预留' in intent[0] and '成交' not in intent[0]
    assert '帧 frame-0012' in waiting[0] and '待核' in waiting[0]
    assert '成交已核对' in settled[0] and '3/2/1→3/1/2' in settled[0]
