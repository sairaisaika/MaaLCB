"""Ownership of purchase labels; pure data helpers, no game or model input."""
import hashlib
import json

OBJECTIVE_APPROVAL = 'objective_delayed_outcome_evidence'
OBJECTIVE_LABEL_SOURCE = 'observed_run_return_after_the_purchase'
HUMAN_LABEL_SOURCE = 'human_reviewed_episode_benefit'


def _digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()


def objective_review(derived):
    value=dict(status='approved',notes='',corrected_category=None,
        benefit=derived['benefit'],label_source=OBJECTIVE_LABEL_SOURCE,
        outcomes_digest=derived['outcomes_digest'],observations=derived['observations'],
        reviewed_by=OBJECTIVE_APPROVAL)
    value['auto_payload_sha256']=_digest(value)
    return value


def automatic_owned(review,outcome):
    if not isinstance(review,dict) or review.get('reviewed_by')!=OBJECTIVE_APPROVAL:
        return False
    if review.get('label_source')!=OBJECTIVE_LABEL_SOURCE or review.get('status')!='approved':
        return False
    body={key:value for key,value in review.items() if key!='auto_payload_sha256'}
    if review.get('auto_payload_sha256'):
        return review['auto_payload_sha256']==_digest(body)
    # Legacy outputs had no seal. Only the complete old generated shape, matched
    # to its old objective label, can be refreshed. Notes/corrections aren't lost.
    label=outcome.get('label') if isinstance(outcome,dict) else None
    if not isinstance(label,dict) or label.get('source')!=OBJECTIVE_APPROVAL:
        return False
    if not all(k in label for k in ('benefit','outcomes_digest','observations')):
        return False
    expected=objective_review(label);expected.pop('auto_payload_sha256')
    return review==expected and outcome.get('approved_by')==OBJECTIVE_APPROVAL


def review_problem(review,outcome):
    """None only for an untouched pending record or a recognized automatic one."""
    if review is None:
        return None
    if not isinstance(review,dict):
        return 'review_shape_unknown'
    status=review.get('status')
    if status=='rejected':
        return 'human_review_rejected'
    if status=='approved':
        return None if automatic_owned(review,outcome) else 'human_review_preserved'
    if status!='pending':
        return 'review_status_unknown'
    if (review.get('notes') or review.get('corrected_category') is not None or
            review.get('benefit') is not None or review.get('reviewed_by') is not None or
            set(review)-{'status','notes','corrected_category','benefit'}):
        return 'human_review_pending'
    return None


def explicit_human_label(review):
    # Older manual-tool versions inherited the automatic label_source field.
    # The explicit non-teacher reviewer is the takeover marker, not that stale tag.
    return (review.get('status')=='approved'
            and isinstance(review.get('reviewed_by'),str) and bool(review['reviewed_by'])
            and review['reviewed_by']!=OBJECTIVE_APPROVAL)


def merge_outcome(previous,current,*,observations_available=True):
    """Refresh observations without erasing a prior approval or label ownership."""
    if previous is None:
        return current
    if not isinstance(previous,dict) or previous.get('version')!=1:
        raise ValueError('Unknown existing purchase outcome preserved')
    if not observations_available:
        return previous
    facts=('version','category','outcomes','objective')
    if all(previous.get(k)==current.get(k) for k in facts):
        return previous
    value=dict(previous)
    value.update({key:current[key] for key in facts})
    if previous.get('human_approved') is not True:
        # Old automatic eligibility cannot certify an updated observation set.
        # Keep the prior label to recognize unmodified legacy auto reviews.
        value.update(human_approved=False,training_eligible=False,reason=current['reason'])
    return value
