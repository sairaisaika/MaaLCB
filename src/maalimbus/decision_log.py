"""Human-readable traces of actual decision inputs, never invented model scores."""
import json


_SKILL_MODES = {'off': '关闭', 'keep_one_each': '各留一张 S1、S2', 'keep_one_s2': '只留一张 S2'}


def _skill_counts(counts):
    return '/'.join(map(str,counts)) if counts else '未读到'


def lines(event, fields):
    if event in ('floor_gift_ranking','floor_gift_bounded_exploration_ranking'):
        result=['藏品评分：规则分，越低越优先；同分按名称。学习模型未参与此评分。']
        for n,row in enumerate(fields.get('ranking') or [],1):
            parts=row.get('score_components')
            detail=' '.join(f'{k}={v:+g}' for k,v in parts.items()) if parts else '旧记录未提供分项'
            result.append(f"候选{n} {row['title']}：{detail}；最终分={row['score']}"+('；首选候选' if n==1 else ''))
        return result
    if event=='theme_pack_recommendation':
        chosen=(fields.get('chosen') or {}).get('name')
        result=['主题评分：保存权重，越高越优先；同分按画面从左到右。']
        for row in fields.get('ranking') or []:
            result.append(f"{row['name']}：权重={row['weight']}；最终分={row['weight']}；来源={row['reason']}"+('；选择' if row['name']==chosen else ''))
        return result
    if event=='shop_decision_ranking':
        result=[f"商店选择：{fields.get('reason')}；金币={fields.get('currency')}；最低保留={fields.get('reserve')}；离店结余上限={fields.get('carry_cap_coins', '未记录')}；已刷新={fields.get('refreshes_used', '未记录')}/{fields.get('refresh_limit')}。队列分越高越优先。"]
        trace=fields.get('learning') or {}
        for row in fields.get('ranking') or []:
            scores=[s for s in trace.get('scores') or []
                    if s.get('name')==row['name'] and s.get('price')==row['price']]
            neural=''
            if len(scores)==1 and isinstance(scores[0].get('predicted_review_value'),(int,float)):
                label='神经排序值' if trace.get('neural_value_ranked') else '影子预测值'
                neural='；%s=%.4f'%(label,scores[0]['predicted_review_value'])
            result.append(f"{row['name']}：价格={row['price']}；手动权重={row.get('manual_weight',0)}；队列分={row.get('score')}；{row['status']}"+neural+('；选择购买' if row.get('chosen') else ''))
        if trace.get('neural_value_ranked'):
            state='价值神经模型已参与购买顺序'
        elif trace.get('neural_value_shadow_applied'):
            state='仅影子预测，不改变购买顺序'
        else:
            state='未使用神经价值模型'
        episodes=trace.get('reviewed_episodes')
        held=trace.get('held_out') or {}
        if state!='未使用神经价值模型' and isinstance(episodes,int):
            state+='（%d局已核样本' % episodes
            if isinstance(held.get('pairwise_accuracy'),(int,float)) and held.get('pairs'):
                state+='，留出准确率%.2f/%d对' % (held['pairwise_accuracy'],held['pairs'])
            state+='）'
        result.append('学习参与：'+state+'；'+str(trace.get('refresh_reason') or trace.get('reason') or '规则回退'))
        if trace.get('requested_participation')=='ranked' and not trace.get('neural_value_ranked'):
            promotion=trace.get('promotion') or {}
            why=dict(promotion_receipt_missing='缺少绑定到权重的留出凭据',
                promotion_receipt_invalid='留出凭据或分组不一致',
                promotion_constant_outcome_targets='训练结果标签全部相同',
                promotion_insufficient_heldout_pairs='留出可比较样本不足',
                promotion_accuracy_below_threshold='留出排序准确率未达标').get(
                    promotion.get('reason'),promotion.get('reason','未核实'))
            result.append('神经排序保留规则顺序：'+why)
        return result
    if event=='shop_skill_choices_observed':
        identity=fields.get('deployment_identity') or {}
        role={'frontline':'初始前排','backup':'后备'}.get(identity.get('role'),'人格或前排证据不足')
        mode=_SKILL_MODES.get(fields.get('active_mode'),'未设置')
        result=[f"技能报价 {fields.get('sinner')}，{role}，当前 {mode}，"
                f"S1/S2/S3={_skill_counts(fields.get('counts'))}，金币={fields.get('coins')}，"
                f"保留={fields.get('reserve_coins')}。同样增加一张 S3 时优先最低已核报价。"]
        for quote in fields.get('quotes') or ():
            price=quote.get('price')
            proof='等级已核' if quote.get('tiers_verified') else '等级未核'
            result.append(f"S{quote.get('from_tier')}→S{quote.get('to_tier')}，"
                          f"报价={price if price is not None else '未读到'}，{proof}")
        for key in ('keep_one_each','keep_one_s2'):
            proposal=(fields.get('previews') or {}).get(key)
            if proposal:
                result.append(f"{_SKILL_MODES[key]}预演，S{proposal['from_tier']}→S3，"
                              f"报价={proposal['price']}，预测张数={_skill_counts(proposal['counts_after'])}，"
                              f"预测余额={proposal['coins_after']}")
        return result
    if event=='shop_skill_selection_intent':
        choice=fields['selection']
        return [f"预留技能卡点选 S{choice['from_tier']}→S3，报价={choice['price']}，等待独立后继。"]
    if event=='shop_identity_skill_search_observed':
        badge = '显示星光图标' if fields.get('currency') == 'starlight' else '币种待读'
        return [f"高级店发现 ID Skill Search，{badge}。货架没有可核验报价。"]
    if event=='shop_skill_receipt_verified':
        receipt=fields['receipt']
        return [f"技能成交已核对 {receipt['sinner']}，金币 {receipt['coins_before']}→{receipt['coins_after']}，"
                f"张数 {_skill_counts(receipt['counts_before'])}→{_skill_counts(receipt['counts_after'])}。"]
    if event=='shop_skill_receipt_unproven' and fields.get('attempt')==1:
        return [f"技能后继待核，当前页面 {fields.get('page')}，帧 {fields.get('frame')}，{fields.get('error')}。"]
    return []

def signature(event,fields):
    if event=='shop_skill_choices_observed':
        fields={key:value for key,value in fields.items() if key!='frame'}
    elif event=='shop_identity_skill_search_observed':
        fields={'currency':fields['currency']}
    return json.dumps([event,fields],sort_keys=True,ensure_ascii=False,default=str)
