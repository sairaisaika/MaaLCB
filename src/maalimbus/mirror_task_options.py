"""Independent native task nodes avoid MXU's shallow action-param replacement."""
from .shop_skill_policy import SKILL_MODES
from .storage import KEYWORDS


def collect(get_node):
    keyword = get_node('MirrorInitialKeyword')['attach']['keyword']
    search = get_node('MirrorGiftSearch')['attach']['mode']
    # The step bound is not offered any more (2026-11-27: the player counts runs, and a
    # number of loop steps means nothing to them). The node is still read so that a
    # pipeline or a saved choice that carries a number behaves as it did.
    try:
        bounds = get_node('MirrorRunBounds').get('attach', {}).get('steps', 'saved')
    except KeyError:
        bounds = 'saved'
    # The run count is a later node than the rest: a pipeline built before it existed
    # simply carries no value, and that reads as "no number named" rather than as a
    # failure to start the window.
    runs = get_node('MirrorRunCount').get('attach', {}).get('run_count', 'saved')
    battle = get_node('MirrorBattleAssignment')['attach']['mode']
    result = {}
    try:
        skill = get_node('MirrorShopSkillMode').get('attach', {}).get('mode')
    except KeyError:
        skill = None  # Older packaged pipelines have no skill option carrier.
    if skill is not None:
        if skill not in SKILL_MODES:
            raise ValueError('Unknown shop skill policy')
        result['shop_skill_mode'] = skill
    try:
        fusion = get_node('MirrorShopFusion').get('attach', {}).get('mode')
    except KeyError:
        fusion = None  # A pipeline packaged before the fusion switch carries no node.
    if fusion is not None:
        if fusion not in ('recipes', 'off'):
            raise ValueError('Unknown shop fusion mode')
        result['shop_fusion'] = fusion
    try:
        wipe = get_node('MirrorDefeatAccept').get('attach', {}).get('mode')
    except KeyError:
        wipe = None  # A pipeline packaged before the choice existed carries no node.
    if wipe is not None:
        if wipe not in ('accept', 'wait'):
            raise ValueError('Unknown wiped-stage choice')
        # What happens once a wiped stage has used up its retries: accept the result, which
        # ends the run, or stop on the page and leave it to the player.
        result['defeat_accept'] = wipe == 'accept'
    if battle not in ('saved','win_rate','damage','observe'):
        raise ValueError('Unknown battle assignment mode')
    if battle!='saved':result['battle_assignment']=battle
    if keyword != 'saved':
        if keyword not in {k.lower() for k in KEYWORDS}:
            raise ValueError('Unknown initial gift system')
        result['gift_keyword'] = keyword
    # A task preference never grants permission to pay for gift search.
    if search not in ('saved', 'refuse'):
        raise ValueError('Gift search payment is not supported by task settings')
    if search != 'saved':
        result['gift_search'] = search
    if bounds != 'saved':
        if type(bounds) is not int or not 1 <= bounds <= 2000:
            raise ValueError('Mirror window steps must be 1..2000')
        result['steps'] = bounds
    # The number of complete runs the player asks for, which is not the step bound: zero
    # is "no number named" and the window keeps walking until another bound stops it.
    if runs != 'saved':
        if type(runs) is not int or not 0 <= runs <= 50:
            raise ValueError('Mirror run count must be 0..50')
        result['run_count'] = runs
    return result


# The installed pipeline names these fields; both were read from
# `assets/resource/base/pipeline/mirror.json` (`MirrorTaskSingleTeam.attach.slot`,
# `MirrorInitialKeyword.attach.keyword`) rather than guessed.  A preference that names
# a team therefore produces a pipeline override with exactly that field.
def gui_override(prefs):
    """Turn the player's GUI choices into a pipeline override, or `{}` if none apply."""
    if not prefs:
        return {}
    patch = {}
    team = prefs.get('mirror_single_team')
    if prefs.get('mirror_team_mode') == 'single' and isinstance(team, int) and team > 0:
        patch['MirrorTaskSingleTeam'] = {'attach': {'slot': team}}
    keyword = prefs.get('mirror_initial_keyword')
    if keyword and keyword != 'saved':
        patch['MirrorInitialKeyword'] = {'attach': {'keyword': keyword}}
    return patch
