"""The shop's fusion pages: what is read from them and the one input each allows.

The text rows are the OCR of the live client on 2026-11-24 (words and boxes only);
the pictures are drawn here, because game artwork does not belong in the repository.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from maalimbus import fusion_vision as fv
from maalimbus.vision import Text, classify

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
LOCALE = json.loads((ROOT / 'assets/resource/en/locale.json').read_text(encoding='utf-8'))

PAGES = {'needs_keyword': [('Fuse E.G.O Gift', (786, 131, 348, 47), 0.995),
                   ('3285', (1506, 133, 104, 45), 1.0),
                   ('Recipes', (956, 222, 92, 32), 1.0),
                   ('By Tier', (1564, 222, 84, 34), 0.994),
                   ('Fusion Guide', (1372, 230, 136, 22), 0.999),
                   ('Fusion Available', (960, 329, 218, 28), 0.992),
                   ('E.G.O Gifts Owned', (958, 530, 234, 27), 0.997),
                   ('Select a Keyword.', (1132, 557, 294, 40), 0.968),
                   ('Forecasts', (328, 686, 82, 28), 0.995),
                   ('111', (962, 726, 28, 14), 0.71),
                   ('111', (1106, 726, 26, 14), 0.662),
                   ('Wishmaking', (464, 740, 150, 32), 1.0),
                   ('5', (686, 744, 18, 24), 1.0),
                   ('X Close', (674, 855, 132, 42), 0.903),
                   ('Fuse', (1164, 857, 82, 40), 0.998)],
 'keyword_page': [('Fusion - Keyword Selection', (620, 113, 674, 65), 0.986),
                  ('Please choose a Keyword you want to Fuse into.', (540, 220, 834, 48), 0.999),
                  ('BURN', (466, 474, 66, 40), 1.0),
                  ('RUPTURE', (1126, 474, 104, 42), 1.0),
                  ('BLEED', (688, 476, 74, 38), 1.0),
                  ('TREMOR', (906, 476, 92, 38), 1.0),
                  ('SINKING', (1360, 476, 90, 38), 1.0),
                  ('POISE', (466, 690, 68, 40), 1.0),
                  ('CHARGE', (680, 692, 90, 38), 1.0),
                  ('SLASH', (916, 692, 72, 40), 1.0),
                  ('PIERCE', (1138, 692, 80, 38), 1.0),
                  ('BLUNT', (1368, 692, 74, 38), 1.0),
                  ('× Cancel', (664, 827, 148, 42), 0.929),
                  ('Confirm', (1112, 827, 156, 42), 1.0)],
 'keyword_set': [('Fuse E.G.O Gift', (784, 131, 352, 53), 0.998),
                 ('3285', (1512, 133, 98, 45), 1.0),
                 ('Recipes', (956, 222, 92, 32), 1.0),
                 ('By Tier', (1564, 222, 84, 34), 0.994),
                 ('Fusion Guide', (1372, 230, 136, 22), 0.999),
                 ('Fusion Available', (958, 329, 220, 28), 0.992),
                 ('E.G.O Gifts Owned', (954, 528, 240, 33), 0.994),
                 ('Forecasts', (332, 690, 74, 22), 0.991),
                 ('111', (962, 726, 28, 14), 0.718),
                 ('Wishmaking', (464, 738, 150, 34), 1.0),
                 ('5', (686, 744, 18, 24), 1.0),
                 ('X Close', (674, 855, 132, 42), 0.903),
                 ('Fuse', (1166, 857, 80, 40), 0.998)],
 'recipe_loaded': [('Fuse E.G.O Gift', (784, 131, 352, 53), 0.999),
                   ('3285', (1510, 131, 102, 51), 1.0),
                   ('By Tier', (1564, 222, 84, 34), 0.994),
                   ('Recipes', (960, 228, 86, 22), 1.0),
                   ('Fusion Guide', (1372, 230, 136, 22), 0.999),
                   ('Fusion Available', (958, 329, 220, 28), 0.993),
                   ('E.G.O Gifts Owned', (956, 528, 236, 27), 0.96),
                   ('100%', (640, 680, 86, 44), 0.999),
                   ('Forecasts', (332, 690, 74, 22), 0.991),
                   ('111', (962, 726, 28, 14), 0.715),
                   ('Wishmaking', (464, 740, 150, 32), 1.0),
                   ('X Close', (674, 855, 132, 42), 0.903),
                   ('Fuse', (1166, 857, 80, 40), 0.998)],
 'question': [('Fuse E.G.OGift', (786, 127, 348, 47), 0.987),
              ('2/3', (866, 250, 86, 67), 1.0),
              ('Prediction', (1374, 256, 224, 47), 1.0),
              ('Selected E.G.O Gifts', (480, 260, 358, 43), 0.994),
              ('1', (1206, 448, 52, 40), 0.801),
              ('Fuse the selected E.G.O Gifts?', (694, 738, 526, 40), 0.974),
              ('× Cancel', (664, 855, 144, 36), 0.881),
              ('Confirm', (1138, 855, 130, 36), 1.0)],
 'notice': [('3285', (1468, 131, 142, 49), 1.0),
            ('Fuse E.G.O Gift', (786, 133, 348, 47), 0.993),
            ('By Tier', (1566, 226, 82, 28), 0.981),
            ('Fusion Guide', (1372, 228, 134, 22), 0.998),
            ('E.G.O Gift GET!', (828, 252, 260, 39), 1.0),
            ('Units)', (802, 522, 82, 35), 1.0),
            ('Insulator', (552, 655, 122, 27), 1.0),
            ('ecasts', (358, 694, 44, 14), 0.922),
            ('Confirm', (926, 776, 130, 41), 0.999)],
 'nothing_available': [('Fuse E.G.O Gift', (784, 131, 352, 53), 0.998),
                       ('3285', (1508, 131, 104, 51), 1.0),
                       ('Recipes', (956, 222, 92, 32), 1.0),
                       ('By Tier', (1566, 226, 82, 28), 0.982),
                       ('Fusion Guide', (1372, 230, 136, 22), 0.999),
                       ('E.G.O Gifts Owned', (956, 325, 238, 34), 0.993),
                       ('X', (1340, 615, 18, 16), 0.612),
                       ('X', (1628, 615, 18, 16), 0.632),
                       ('Forecasts', (330, 690, 78, 22), 0.978),
                       ('Wishmaking', (464, 740, 150, 32), 1.0),
                       ('5', (686, 744, 18, 24), 1.0),
                       ('X Close', (674, 855, 132, 42), 0.903),
                       ('Fuse', (1166, 859, 80, 36), 0.999)],
 'three_random': [('Fuse E.G.O Gift', (784, 131, 352, 53), 0.999),
                  ('3285', (1508, 133, 100, 45), 1.0),
                  ('Recipes', (958, 222, 90, 32), 1.0),
                  ('By Tier', (1566, 226, 82, 28), 0.982),
                  ('Fusion Guide', (1372, 230, 136, 22), 0.999),
                  ('E.G.O Gifts Owned', (956, 325, 238, 34), 0.991),
                  ('90%', (640, 678, 80, 46), 0.988),
                  ('Forecasts', (332, 690, 74, 22), 0.988),
                  ('E.G.O GIFT', (1492, 718, 134, 42), 0.971),
                  ('Wishmaking', (464, 740, 150, 32), 1.0),
                  ('Milepost of Survjval', (1464, 776, 274, 28), 0.956),
                  ('X Close', (674, 855, 132, 42), 0.903),
                  ('Fuse', (1164, 857, 82, 40), 0.998)],
 'shop': [('Shop', (334, 154, 98, 54), 1.0),
          ('PEN', (242, 405, 50, 27), 0.968),
          ('Sell', (596, 561, 48, 30), 1.0),
          ('Enhance', (222, 565, 84, 22), 0.997),
          ('Fuse', (418, 565, 50, 24), 0.999),
          ('Gifts', (590, 579, 58, 34), 0.992),
          ('Gifts', (416, 583, 52, 24), 1.0),
          ('Gifts', (238, 587, 54, 22), 1.0),
          ('Heal', (298, 688, 50, 22), 1.0),
          ('Team', (528, 694, 62, 28), 1.0),
          ('Sinner', (286, 706, 72, 28), 1.0),
          ('100', (264, 742, 62, 32), 1.0),
          ('100', (496, 742, 66, 34), 0.999),
          ('Leave', (1622, 945, 150, 53), 1.0)]}


def records(name):
    return [Text(text, box, score) for text, box, score in PAGES[name]]


def record(name):
    return dict(size=list(SIZE), ocr=[dict(text=text, box=list(box), score=score) for text, box, score in PAGES[name]])


def panel_picture(*, wish_ticked=False):
    """A dark frame; the Wishmaking box holds a bright tick when asked."""
    image = np.full((1080, 1920, 3), 23, np.uint8)
    if wish_ticked:
        x, y, w, h = fv.WISH_BOX
        image[y + 6:y + h - 6, x + 6:x + w - 6] = (60, 200, 255)
    return image


def keyword_picture(chosen=None):
    """Ten dark tiles; the chosen one carries the orange frame the game draws."""
    image = np.full((1080, 1920, 3), 30, np.uint8)
    for text, (x, y, w, h), _ in PAGES['keyword_page']:
        if text == chosen:
            centre = x + w // 2
            left, right, top, bottom = centre - 84, centre + 84, y - 136, y + 60
            image[top:bottom, left:right] = (0, 140, 255)           # BGR orange
            image[top + 8:bottom - 8, left + 8:right - 8] = 30
    return image


def test_each_live_page_is_named_and_the_shop_behind_it_is_not():
    expected = dict(needs_keyword='FUSION', keyword_set='FUSION', recipe_loaded='FUSION', nothing_available='FUSION',
                    three_random='FUSION', keyword_page='FUSION_KEYWORD', question='FUSION_CONFIRM',
                    notice=None, shop=None)
    for name, page in expected.items():
        assert fv.page(records(name), SIZE) == page, name
    # The classifier hands the same names on, the result notice stays the ordinary one,
    # and the shop is still the shop.
    for name, scene in dict(expected, notice='GIFT_GET', shop='SHOP').items():
        assert classify(records(name), LOCALE, SIZE) == scene, name


def test_the_panel_reader_reports_keyword_list_forecast_and_buttons():
    blank = panel_picture()
    needs = fv.read_panel(records('needs_keyword'), SIZE, blank)
    assert needs['keyword_needed'] and needs['forecast'] is None
    # The game lists the recipe before any keyword is chosen: the list does not depend on it.
    assert needs['available'] == [974, 395, 90, 90]
    loaded = fv.read_panel(records('recipe_loaded'), SIZE, blank)
    assert loaded == dict(keyword_needed=False, available=[972, 395, 90, 90], forecast=100.0, wish_empty=True,
                          centre=[510, 477, 80, 80], fuse=[1166, 857, 80, 40], close=[674, 855, 132, 42])
    empty = fv.read_panel(records('nothing_available'), SIZE, blank)
    assert empty['available'] is None and empty['forecast'] is None and not empty['keyword_needed']
    assert fv.read_panel(records('three_random'), SIZE, blank)['forecast'] == 90.0
    # The Wishmaking box: empty only when it is seen empty.
    assert fv.read_panel(records('recipe_loaded'), SIZE, panel_picture(wish_ticked=True))['wish_empty'] is False
    assert fv.read_panel(records('recipe_loaded'), SIZE, None)['wish_empty'] is False


def test_the_keyword_page_says_which_tile_is_chosen_by_its_frame():
    none = fv.read_keywords(records('keyword_page'), SIZE, keyword_picture())
    assert none['chosen'] is None and len(none['tiles']) == 10
    assert none['confirm'] == [1112, 827, 156, 42] and none['cancel'] == [664, 827, 148, 42]
    assert fv.read_keywords(records('keyword_page'), SIZE, keyword_picture('CHARGE'))['chosen'] == 'CHARGE'
    assert fv.read_keywords(records('keyword_page'), SIZE, keyword_picture('BLUNT'))['chosen'] == 'BLUNT'
    assert fv.read_keywords(records('keyword_page'), SIZE, None)['chosen'] is None


def test_the_shop_button_is_two_stacked_words_between_its_neighbours():
    assert fv.opener(records('shop'), SIZE) == [416, 565, 52, 42]
    without = [row for row in records('shop') if row.text != 'Fuse']
    assert fv.opener(without, SIZE) is None
    assert fv.opener(records('needs_keyword'), SIZE) is None


def walk(pages, systems=('CHARGE',)):
    """Feed a sequence of (page, reading) to the decision with one visit's memory."""
    memory, answers = {}, []
    for name, reading in pages:
        answers.append(fv.next_input(name, reading, memory, list(systems)))
    return answers, memory


def test_a_ready_recipe_is_fused_through_the_steps_measured_live():
    blank = panel_picture()

    def keyword(chosen):
        return fv.read_keywords(records('keyword_page'), SIZE, keyword_picture(chosen))

    def panel(name):
        return fv.read_panel(records(name), SIZE, blank)

    answers, memory = walk([
        ('FUSION', panel('needs_keyword')),            # centre slot
        ('FUSION_KEYWORD', keyword(None)),             # the CHARGE tile
        ('FUSION_KEYWORD', keyword('CHARGE')),         # Confirm, now that its frame shows
        ('FUSION', panel('keyword_set')),              # the entry under Fusion Available
        ('FUSION', panel('recipe_loaded')),            # Fuse, at 100%
        ('FUSION_CONFIRM', fv.read_confirm(records('question'), SIZE)),
        ('FUSION', panel('nothing_available')),        # Close
    ])
    assert [a['action'] for a in answers] == ['click'] * 7
    assert [a['target'] for a in answers] == [
        [510, 477, 80, 80], [680, 692, 90, 38], [1112, 827, 156, 42], [972, 395, 90, 90],
        [1166, 857, 80, 40], [1138, 855, 130, 36], [674, 855, 132, 42]]
    assert answers[4]['reason'] == 'the_recipe_is_loaded_and_its_forecast_reads_100_percent'
    assert answers[5]['reason'] == 'confirming_the_recipe_fusion_whose_forecast_read_100_percent'
    assert answers[5]['selected'] == '2/3'
    assert memory['fused'] == 1 and memory['done'] and memory['tried'] == ['CHARGE']


def test_fuse_is_never_pressed_for_anything_but_a_guaranteed_recipe():
    blank = panel_picture()
    # Three gifts somebody loaded by hand read 90%: a random fusion. Close.
    answers, memory = walk([('FUSION', fv.read_panel(records('three_random'), SIZE, blank))])
    assert answers[0]['target'] == [674, 855, 132, 42] and 'random_fusion' in answers[0]['reason']
    assert not memory.get('armed')
    # 100% with the Wishmaking box ticked, or not seen at all: Close.
    for picture in (panel_picture(wish_ticked=True), None):
        answers, memory = walk([('FUSION', fv.read_panel(records('recipe_loaded'), SIZE, picture))])
        assert answers[0]['target'] == [674, 855, 132, 42] and answers[0]['reason'].startswith('wishmaking_box')
        assert not memory.get('armed')
    # 99.99% is the best a random fusion reaches; it is not 100.
    almost = dict(fv.read_panel(records('recipe_loaded'), SIZE, blank), forecast=99.99)
    assert walk([('FUSION', almost)])[0][0]['target'] == [674, 855, 132, 42]
    # The fusion question without a Fuse this visit pressed at 100% is cancelled.
    answers, _ = walk([('FUSION_CONFIRM', fv.read_confirm(records('question'), SIZE))])
    assert answers[0]['target'] == [664, 855, 144, 36] and 'did_not_arm' in answers[0]['reason']
    # A 100% forecast arms exactly one Confirm.
    memory = {}
    loaded = fv.read_panel(records('recipe_loaded'), SIZE, blank)
    question = fv.read_confirm(records('question'), SIZE)
    assert fv.next_input('FUSION', loaded, memory, ['CHARGE'])['target'] == loaded['fuse']
    assert fv.next_input('FUSION_CONFIRM', question, memory, ['CHARGE'])['target'] == question['confirm']
    assert fv.next_input('FUSION_CONFIRM', question, memory, ['CHARGE'])['target'] == question['cancel']


def test_the_visit_ends_instead_of_looping():
    blank = panel_picture()
    keyword_set = fv.read_panel(records('keyword_set'), SIZE, blank)
    # The entry is tapped twice at most; a recipe that never loads is left.
    answers, memory = walk([('FUSION', keyword_set)] * 3)
    assert [a['target'] for a in answers] == [[972, 395, 90, 90], [972, 395, 90, 90], [674, 855, 132, 42]]
    assert memory['done']
    # A tile whose frame never shows is not confirmed blind.
    unchosen = fv.read_keywords(records('keyword_page'), SIZE, keyword_picture())
    answers, _ = walk([('FUSION_KEYWORD', unchosen)] * 3)
    assert [a['action'] for a in answers] == ['click', 'click', 'refuse']
    assert answers[2]['reason'] == 'fusion_keyword_tile_never_showed_as_chosen'
    # Nothing available under the one keyword looked at: Close, and stay closed.
    nothing = fv.read_panel(records('nothing_available'), SIZE, blank)
    memory = dict(tried=['CHARGE'])
    answer = fv.next_input('FUSION', nothing, memory, ['CHARGE'])
    assert answer['reason'] == 'no_recipe_is_available_under_any_keyword_looked_at' and memory['done']
    # At most four fusions in one visit.
    memory = dict(tried=['CHARGE'], fused=fv.MAX_FUSIONS)
    assert fv.next_input('FUSION', keyword_set, memory, ['CHARGE'])['target'] == [674, 855, 132, 42]
    # A control the page did not print is a refusal by name, never a guess.
    assert fv.next_input('FUSION', dict(nothing, close=None), dict(tried=['CHARGE']), ['CHARGE'])['action'] == 'refuse'


def test_binding_opens_the_panel_once_when_the_shop_has_nothing_else_to_do():
    memory = {}
    idle = dict(buy=None, refresh=None, confirm=None, currency=2445)
    box, note = fv.bind('SHOP', record('shop'), idle, memory, visit='5', systems=['Charge', 'Tremor'])
    assert box is None and idle['fuse'] == [416, 565, 52, 42] and note['step'] == 'open'
    # While the shop still buys or refreshes, fusion waits.
    for key in ('buy', 'refresh', 'confirm', 'revive'):
        busy = dict(idle, fuse=None, **{key: dict(box=[1, 2, 3, 4])})
        assert fv.bind('SHOP', record('shop'), busy, {}, visit='5') == (None, None) and not busy['fuse']
    # Switched off: the shop is left alone.
    off = dict(idle, fuse=None)
    assert fv.bind('SHOP', record('shop'), off, {}, visit='5', enabled=False) == (None, None) and not off['fuse']
    # Looked once this visit: not again. A new visit starts over.
    memory['done'] = True
    again = dict(idle, fuse=None)
    assert fv.bind('SHOP', record('shop'), again, memory, visit='5') == (None, None)
    fv.bind('SHOP', record('shop'), again, memory, visit='6')
    assert again['fuse'] == [416, 565, 52, 42] and memory == dict(visit='6', openings=1)
    # A button that opens nothing is pressed twice at most.
    stuck = {}
    for _ in range(2):
        fv.bind('SHOP', record('shop'), dict(idle), stuck, visit='7')
    box, note = fv.bind('SHOP', record('shop'), dict(idle), stuck, visit='7')
    assert note['reason'] == 'the_fuse_gifts_button_did_not_open_the_panel' and stuck['done']


def test_binding_a_fusion_page_returns_the_one_box_and_says_why():
    blank = panel_picture()
    memory = dict(visit='5')
    box, note = fv.bind('FUSION', record('needs_keyword'), None, memory, systems=['Charge', 'Tremor'],
                        load_image=lambda: blank)
    assert box == [510, 477, 80, 80] and note['reason'] == 'the_panel_asks_for_a_keyword_first'
    # The first system of the team is the one keyword looked under.
    box, note = fv.bind('FUSION_KEYWORD', record('keyword_page'), None, memory, systems=['Charge', 'Tremor'],
                        load_image=keyword_picture)
    assert box == [680, 692, 90, 38] and note['keyword'] == 'CHARGE'
    # A team with no system looks under the default keyword.
    box, note = fv.bind('FUSION_KEYWORD', record('keyword_page'), None, {}, systems=[], load_image=keyword_picture)
    assert note['keyword'] == fv.DEFAULT_KEYWORD
    # Switched off and the panel is open anyway: only Close and Cancel are answered.
    box, note = fv.bind('FUSION', record('recipe_loaded'), None, {}, enabled=False, load_image=lambda: blank)
    assert box == [674, 855, 132, 42]
    box, note = fv.bind('FUSION_KEYWORD', record('keyword_page'), None, {}, enabled=False, load_image=keyword_picture)
    assert box == [664, 827, 148, 42]
    box, note = fv.bind('FUSION_CONFIRM', record('question'), None, {}, enabled=False)
    assert box == [664, 855, 144, 36]
    assert fv.bind('MAP', record('shop'), None, {}) == (None, None)


def test_the_plan_table_turns_the_bound_box_into_the_click_and_refuses_without_it():
    from maalimbus.window import CLICK, plan_step
    for page in fv.PAGES:
        plan = plan_step(page, controls={'fusion.next': [1, 2, 3, 4]})
        assert plan['action'] == CLICK and plan['target'] == [1, 2, 3, 4]
        refused = plan_step(page, controls={})
        assert refused['action'] != CLICK and 'not_decided' in refused['reason']
    # The shop opens the panel before it leaves, and only when told to.
    controls = {'shop.leave_button': [1622, 945, 150, 53]}
    opened = plan_step('SHOP', controls=controls, shop=dict(fuse=[416, 565, 52, 42]))
    assert opened['target'] == [416, 565, 52, 42] and 'FUSION' in opened['expect']
    assert plan_step('SHOP', controls=controls, shop=dict(fuse=None))['target'] == [1622, 945, 150, 53]
    # A purchase still comes first.
    buying = plan_step('SHOP', controls=controls, shop=dict(fuse=[416, 565, 52, 42],
                       buy=dict(box=[870, 357, 120, 90], name='Wobbling Keg', price=147, why='gift_plan')))
    assert buying['target'] == [870, 357, 120, 90]
    # The result notice may hand the run back to the panel.
    assert 'FUSION' in plan_step('GIFT_GET', controls={'gift_get.confirm_button': [926, 776, 130, 41]})['expect']


def test_the_switch_reaches_the_runner_and_defaults_to_recipes():
    from maalimbus import runner
    from maalimbus.mirror_task_options import collect
    assert runner.settings().shop_fusion == 'recipes'
    assert runner.settings(dict(shop_fusion='off')).shop_fusion == 'off'
    with pytest.raises(ValueError):
        runner.settings(dict(shop_fusion='random'))
    pipeline = json.loads((ROOT / 'assets/resource/base/pipeline/mirror.json').read_bytes())
    assert pipeline['MirrorShopFusion']['attach'] == dict(mode='recipes')
    assert collect(pipeline.__getitem__)['shop_fusion'] == 'recipes'
    nodes = dict(pipeline, MirrorShopFusion=dict(attach=dict(mode='off')))
    assert collect(nodes.__getitem__)['shop_fusion'] == 'off'
    older = {name: node for name, node in pipeline.items() if name != 'MirrorShopFusion'}
    assert 'shop_fusion' not in collect(older.__getitem__)
    with pytest.raises(ValueError):
        collect(dict(pipeline, MirrorShopFusion=dict(attach=dict(mode='everything'))).__getitem__)
    interface = json.loads((ROOT / 'assets/interface.json').read_bytes())
    option = interface['option']['mirror_shop_fusion']
    assert option['default_case'] == 'recipes' and [case['name'] for case in option['cases']] == ['recipes', 'off']
    for case in option['cases']:
        assert case['pipeline_override'] == {'MirrorShopFusion': {'attach': {'mode': case['name']}}}
    mirror = next(task for task in interface['task'] if task['name'] == 'mirror_loop')
    assert 'mirror_shop_fusion' in mirror['option']


def test_a_check_mark_read_into_the_button_is_still_the_button():
    # pi-20261124-000448/frame-0258: the keyword page printed `✓Confirm` [1108,827,160,42]
    # at .93 where the day before it printed `Confirm`. The page was not named, the
    # generic dialog rule cancelled it, and the run stopped in the floor-1 shop.
    def marked(name, word):
        return [Text('✓' + text if text == word else text, box, score) for text, box, score in PAGES[name]]
    rows = marked('keyword_page', 'Confirm')
    assert fv.page(rows, SIZE) == 'FUSION_KEYWORD' and classify(rows, LOCALE, SIZE) == 'FUSION_KEYWORD'
    assert fv.read_keywords(rows, SIZE, keyword_picture('CHARGE'))['confirm'] == [1112, 827, 156, 42]
    rows = marked('question', 'Confirm')
    assert fv.page(rows, SIZE) == 'FUSION_CONFIRM' and fv.read_confirm(rows, SIZE)['confirm'] == [1138, 855, 130, 36]
    rows = marked('recipe_loaded', 'Fuse')
    assert fv.page(rows, SIZE) == 'FUSION' and fv.read_panel(rows, SIZE, panel_picture())['fuse'] == [1166, 857, 80, 40]
    # A different word is still a different word.
    other = [Text('Unconfirm' if row.text == 'Confirm' else row.text, row.box, row.score) for row in records('keyword_page')]
    assert fv.page(other, SIZE) is None
