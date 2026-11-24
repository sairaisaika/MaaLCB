"""Read the shop's three fusion pages and say which one input is next.

Measured on the live client on 2026-11-24 (MuMu, 1280x720 scaled to 1920x1080; the
frames are kept in the run's own evidence, the anchor boxes below are their OCR):

* **FUSION** - the panel behind the shop's "Fuse Gifts". Until a keyword is chosen
  the owned gifts are dimmed under "Select a Keyword." and only the centre slot
  answers. With a keyword, the game itself lists what a recipe can make right now
  under "Fusion Available"; one tap on an entry fills the slots with the owned
  ingredients and the forecast reads "Guaranteed ... 100%". Reopening the panel
  forgets the keyword. Tapping the centre slot again reopens the keyword choice.
* **FUSION_KEYWORD** - ten tiles (BURN ... BLUNT) with Cancel and Confirm. The chosen
  tile gets an orange frame; nothing else on the page says which one is chosen.
* **FUSION_CONFIRM** - "Fuse the selected E.G.O Gifts?" with Cancel and Confirm. It
  shows the gifts and a prediction as pictures only: no name, no percentage.

After Confirm the game shows its ordinary "E.G.O Gift GET!" notice with the result's
name, and its Confirm returns to the panel.

What this module allows is narrow on purpose. Fuse is pressed only for a recipe: the
forecast must read exactly 100%, which no random fusion reaches (the best is 99.99%),
and the Wishmaking box, which would spend Starlight, must be seen empty. A random
fusion, which gives gifts away for a chance, is not planned here at all.
"""
import re

from .vision import find

TITLE = r'^Fuse E\.?G\.?O\s*Gift$'
KEYWORD_TITLE = r'^Fusion\s*-?\s*Keyword Selection$'
QUESTION = r'^Fuse the selected E\.?G\.?O\s*Gifts\?$'
#: Both buttons carry a check mark that OCR sometimes reads into the word: `Confirm` on
#: pi-20261123-225704 and `✓Confirm` on pi-20261124-000448/frame-0258, the same button.
#: Read strictly, the second frame was no fusion page at all and the run stopped on it.
CONFIRM = r'^[^A-Za-z]{0,2}\s*Confirm$'
FUSE = r'^[^A-Za-z]{0,2}\s*Fuse$'
#: The tile captions, as the page prints them.
KEYWORDS = ('BURN', 'BLEED', 'TREMOR', 'RUPTURE', 'SINKING', 'POISE', 'CHARGE', 'SLASH', 'PIERCE', 'BLUNT')

#: The centre slot of the machine: the only control that opens the keyword choice.
CENTRE = (510, 477, 80, 80)
#: The first entry under the "Fusion Available" heading, relative to the heading's box.
ENTRY_FROM_HEADING = (14, 66, 90, 90)
#: The inside of the Wishmaking checkbox. Empty it is one flat dark colour
#: (mean 23, deviation 0.1 on five frames).
WISH_BOX = (397, 744, 28, 28)
WISH_EMPTY_DEVIATION = 6.0
WISH_EMPTY_MEAN = 60.0
#: Orange pixels on a tile's frame: 0 on every unchosen tile, about 3,000 on the chosen one.
CHOSEN_PIXELS = 800


def _box(record):
    return [int(value) for value in record.box]


def _scale(box, size):
    sx, sy = size[0] / 1920, size[1] / 1080
    return [round(box[0] * sx), round(box[1] * sy), round(box[2] * sx), round(box[3] * sy)]


def page(records, size):
    """Which fusion page this is, or ``None``."""
    if (find(records, KEYWORD_TITLE, (.30, .08, .70, .18), size, .85)
            and len(find(records, CONFIRM, (.56, .74, .68, .82), size, .85)) == 1
            and sum(1 for word in KEYWORDS if find(records, '^%s$' % word, (.20, .40, .80, .70), size, .85)) >= 8):
        return 'FUSION_KEYWORD'
    if (find(records, QUESTION, (.30, .65, .70, .75), size, .85)
            and len(find(records, CONFIRM, (.57, .76, .69, .86), size, .85)) == 1
            and find(records, r'Cancel$', (.33, .76, .45, .86), size, .8)):
        return 'FUSION_CONFIRM'
    if (find(records, TITLE, (.38, .09, .62, .19), size, .85)
            and find(records, r'^Wishmaking$', (.22, .66, .35, .74), size, .85)
            and len(find(records, FUSE, (.58, .76, .68, .86), size, .85)) == 1
            and find(records, r'Close$', (.33, .76, .45, .86), size, .8)):
        return 'FUSION'
    return None


def wish_empty(image, size):
    """Whether the Wishmaking box is seen empty. Unknown counts as not empty."""
    if image is None:
        return False
    x, y, w, h = _scale(WISH_BOX, size)
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return False
    grey = crop.mean(axis=2) if crop.ndim == 3 else crop
    return bool(grey.std() <= WISH_EMPTY_DEVIATION and grey.mean() <= WISH_EMPTY_MEAN)


def read_panel(records, size, image=None):
    """What the fusion panel shows."""
    heading = find(records, r'^Fusion Available$', (.48, .27, .64, .37), size, .85)
    forecast = None
    for record in find(records, r'^\d{1,3}(?:\.\d+)?%$', (.31, .60, .40, .69), size, .85):
        forecast = float(record.text.strip().rstrip('%'))
    entry = None
    if len(heading) == 1:
        x, y = heading[0].box[0], heading[0].box[1]
        dx, dy, w, h = _scale(ENTRY_FROM_HEADING, size)
        entry = [int(x + dx), int(y + dy), w, h]
    fuse = find(records, FUSE, (.58, .76, .68, .86), size, .85)
    close = find(records, r'Close$', (.33, .76, .45, .86), size, .8)
    return dict(
        keyword_needed=bool(find(records, r'^Select a Keyword\.?$', (.55, .48, .80, .59), size, .8)),
        available=entry, forecast=forecast, wish_empty=wish_empty(image, size),
        centre=_scale(CENTRE, size),
        fuse=_box(fuse[0]) if len(fuse) == 1 else None,
        close=_box(close[0]) if len(close) == 1 else None)


def chosen_tile(image, caption_box, size):
    """Whether the tile over this caption carries the orange frame of the chosen keyword."""
    if image is None:
        return False
    import cv2
    import numpy as np
    sx, sy = size[0] / 1920, size[1] / 1080
    x, y, w, _ = caption_box
    centre = x + w / 2
    left, right = int(centre - 88 * sx), int(centre + 88 * sx)
    top, bottom = int(y - 140 * sy), int(y + 64 * sy)
    tile = image[max(0, top):bottom, max(0, left):right]
    if tile.size == 0:
        return False
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    orange = (hsv[..., 0] >= 8) & (hsv[..., 0] <= 22) & (hsv[..., 1] > 180) & (hsv[..., 2] > 200)
    edge = max(1, int(16 * sx))
    ring = np.ones(orange.shape, bool)
    ring[edge:-edge, edge:-edge] = False
    return int((orange & ring).sum()) >= CHOSEN_PIXELS * sx * sy


def read_keywords(records, size, image=None):
    """The keyword tiles, which one is chosen, and the page's two buttons."""
    tiles = {}
    for word in KEYWORDS:
        found = find(records, '^%s$' % word, (.20, .40, .80, .70), size, .85)
        if len(found) == 1:
            tiles[word] = _box(found[0])
    chosen = [word for word, box in tiles.items() if chosen_tile(image, box, size)]
    confirm = find(records, CONFIRM, (.56, .74, .68, .82), size, .85)
    cancel = find(records, r'Cancel$', (.33, .74, .45, .82), size, .8)
    return dict(tiles=tiles, chosen=chosen[0] if len(chosen) == 1 else None,
                confirm=_box(confirm[0]) if len(confirm) == 1 else None,
                cancel=_box(cancel[0]) if len(cancel) == 1 else None)


def read_confirm(records, size):
    confirm = find(records, CONFIRM, (.57, .76, .69, .86), size, .85)
    cancel = find(records, r'Cancel$', (.33, .76, .45, .86), size, .8)
    count = find(records, r'^\d\s*/\s*\d$', (.43, .21, .52, .31), size, .8)
    return dict(confirm=_box(confirm[0]) if len(confirm) == 1 else None,
                cancel=_box(cancel[0]) if len(cancel) == 1 else None,
                selected=count[0].text.replace(' ', '') if len(count) == 1 else None)


def opener(records, size):
    """The shop's own "Fuse Gifts" button, or ``None``.

    Two stacked words, ``Fuse`` over ``Gifts``, between ``Enhance Gifts`` and
    ``Sell Gifts`` (pi-20261123-212800/frame-0002: ``Fuse`` [418,565,50,24] over
    ``Gifts`` [416,585,52,22]). Both must be read, one above the other.
    """
    top = find(records, r'^Fuse$', (.19, .50, .27, .56), size, .9)
    under = find(records, r'^Gifts$', (.19, .52, .27, .58), size, .9)
    if len(top) != 1 or len(under) != 1:
        return None
    a, b = top[0].box, under[0].box
    if not 0 < (b[1] + b[3] / 2) - (a[1] + a[3] / 2) < 40 * size[1] / 1080:
        return None
    left, upper = min(a[0], b[0]), a[1]
    right, lower = max(a[0] + a[2], b[0] + b[2]), b[1] + b[3]
    return [int(left), int(upper), int(right - left), int(lower - upper)]


MAX_FUSIONS = 4


def next_input(name, reading, memory, keywords):
    """The one input for a fusion page, as ``dict(action, target, reason, ...)``.

    ``memory`` is this shop visit's own note (a dict this function updates):
    ``tried`` keywords, ``armed`` when Fuse was pressed on a 100% forecast, ``fused``
    count, ``done``. ``keywords`` are the tile captions to look under, in order.

    Every answer is a click on a control the page printed, or a refusal with a reason.
    """
    tried = memory.setdefault('tried', [])
    if name == 'FUSION_KEYWORD':
        want = None if memory.get('done') else (
            memory.get('keyword') or next((word for word in keywords if word not in tried), None))
        if want is None or want not in reading['tiles']:
            # Nothing left to look under: step back out through the page's own Cancel.
            if reading['cancel'] is None:
                return dict(action='refuse', reason='fusion_keyword_cancel_not_read')
            memory['done'] = True
            return dict(action='click', target=reading['cancel'], reason='no_keyword_left_to_look_under',
                        expect=('FUSION',))
        memory['keyword'] = want
        if reading['chosen'] == want:
            if reading['confirm'] is None:
                return dict(action='refuse', reason='fusion_keyword_confirm_not_read')
            tried.append(want)
            memory['keyword'] = None
            return dict(action='click', target=reading['confirm'], reason='confirming_the_keyword_the_tile_frame_shows',
                        expect=('FUSION',), keyword=want)
        if memory.get('tile_clicks', 0) >= 2:
            return dict(action='refuse', reason='fusion_keyword_tile_never_showed_as_chosen')
        memory['tile_clicks'] = memory.get('tile_clicks', 0) + 1
        return dict(action='click', target=reading['tiles'][want], reason='choosing_the_keyword_to_look_under',
                    expect=('FUSION_KEYWORD',), keyword=want)
    if name == 'FUSION_CONFIRM':
        if memory.pop('armed', False):
            if reading['confirm'] is None:
                return dict(action='refuse', reason='fusion_confirm_not_read')
            memory['fused'] = memory.get('fused', 0) + 1
            return dict(action='click', target=reading['confirm'],
                        reason='confirming_the_recipe_fusion_whose_forecast_read_100_percent',
                        expect=('GIFT_GET', 'FUSION', 'UNKNOWN'), selected=reading.get('selected'))
        # A question nobody here armed: answer with its own Cancel.
        if reading['cancel'] is None:
            return dict(action='refuse', reason='fusion_question_not_armed_and_cancel_not_read')
        return dict(action='click', target=reading['cancel'], reason='a_fusion_question_this_visit_did_not_arm_is_cancelled',
                    expect=('FUSION',))
    if name != 'FUSION':
        return dict(action='refuse', reason='not_a_fusion_page')
    memory['tile_clicks'] = 0
    close = dict(action='click', target=reading['close'], reason=None, expect=('SHOP', 'FUSION', 'UNKNOWN'))
    if reading['close'] is None:
        close = dict(action='refuse', reason='fusion_close_not_read')

    def leave(reason):
        memory['done'] = True
        return dict(close, reason=close.get('reason') or reason)

    if memory.get('done') or memory.get('fused', 0) >= MAX_FUSIONS:
        return leave('the_fusion_visit_is_finished')
    if reading['keyword_needed']:
        if not [word for word in keywords if word not in tried]:
            return leave('no_keyword_left_to_look_under')
        return dict(action='click', target=reading['centre'], reason='the_panel_asks_for_a_keyword_first',
                    expect=('FUSION_KEYWORD', 'FUSION'))
    if reading['forecast'] is not None:
        if reading['forecast'] != 100.0:
            # Gifts are loaded that no recipe guarantees. Not ours to spend.
            return leave('a_forecast_below_100_percent_is_a_random_fusion_and_is_left_alone')
        if reading['available'] is None:
            return leave('a_100_percent_forecast_without_the_available_heading_is_not_trusted')
        if not reading['wish_empty']:
            return leave('wishmaking_box_not_seen_empty_so_fuse_is_not_pressed')
        if reading['fuse'] is None:
            return dict(action='refuse', reason='fusion_fuse_button_not_read')
        memory['armed'] = True
        memory['entry_clicks'] = 0
        return dict(action='click', target=reading['fuse'], reason='the_recipe_is_loaded_and_its_forecast_reads_100_percent',
                    expect=('FUSION_CONFIRM', 'FUSION'))
    if reading['available'] is not None:
        if memory.get('entry_clicks', 0) >= 2:
            return leave('the_available_recipe_did_not_load_after_two_taps')
        memory['entry_clicks'] = memory.get('entry_clicks', 0) + 1
        return dict(action='click', target=reading['available'], reason='loading_the_recipe_the_game_lists_as_available',
                    expect=('FUSION',))
    memory['entry_clicks'] = 0
    if [word for word in keywords if word not in tried]:
        return dict(action='click', target=reading['centre'], reason='nothing_available_under_this_keyword_so_the_next_is_tried',
                    expect=('FUSION_KEYWORD', 'FUSION'))
    return leave('no_recipe_is_available_under_any_keyword_looked_at')


PAGES = ('FUSION', 'FUSION_KEYWORD', 'FUSION_CONFIRM')
#: Looked under when the team names no system. The game lists what a recipe can make
#: before any keyword is chosen (the entry is already there, dimmed, under "Select a
#: Keyword."), so which keyword unlocks the list does not decide what is on it.
DEFAULT_KEYWORD = 'BURN'
MAX_OPENINGS = 2


def _records(record):
    from .vision import Text
    return [Text(str(item.get('text', '')), tuple(item.get('box') or (0, 0, 0, 0)), float(item.get('score') or 0.0))
            for item in record.get('ocr') or []]


def bind(name, record, shop, memory, *, visit=None, systems=(), enabled=True, load_image=None):
    """What one frame binds for fusion: ``(box or None, note or None)``.

    On the shop, when the visit has nothing left to buy or refresh and has not looked
    yet, ``shop['fuse']`` is set to the "Fuse Gifts" button so the shop's own plan opens
    the panel before it leaves. On a fusion page the returned box is the one input
    (bound by the caller as ``fusion.next``). ``memory`` is the visit's note and is
    cleared when ``visit`` changes. Switched off, the shop is left alone and a fusion
    page that is open anyway is only closed.
    """
    size = tuple(record.get('size') or (1920, 1080))
    if name == 'SHOP':
        if visit is not None and memory.get('visit') != visit:
            memory.clear()
            memory['visit'] = visit
        busy = any((shop or {}).get(key) for key in ('buy', 'refresh', 'confirm', 'revive'))
        if not enabled or not shop or busy or memory.get('done'):
            return None, None
        if memory.get('openings', 0) >= MAX_OPENINGS:
            memory['done'] = True
            return None, dict(step='not_opened', reason='the_fuse_gifts_button_did_not_open_the_panel')
        box = opener(_records(record), size)
        if box is None:
            memory['done'] = True
            return None, dict(step='not_opened', reason='the_fuse_gifts_button_was_not_read')
        memory['openings'] = memory.get('openings', 0) + 1
        shop['fuse'] = box
        return None, dict(step='open', target=box, systems=list(systems))
    if name not in PAGES:
        return None, None
    if not enabled:
        memory['done'] = True
    look = [str(system).upper() for system in systems if str(system).upper() in KEYWORDS][:1] or [DEFAULT_KEYWORD]
    records = _records(record)
    if name == 'FUSION':
        reading = read_panel(records, size, load_image() if load_image else None)
    elif name == 'FUSION_KEYWORD':
        reading = read_keywords(records, size, load_image() if load_image else None)
    else:
        reading = read_confirm(records, size)
    answer = next_input(name, reading, memory, look)
    note = dict(step=name.lower(), action=answer['action'], reason=answer['reason'], target=answer.get('target'),
                keyword=answer.get('keyword'), forecast=reading.get('forecast'),
                available=reading.get('available') is not None if name == 'FUSION' else None,
                fused=memory.get('fused', 0), tried=list(memory.get('tried', [])))
    return (answer.get('target') if answer['action'] == 'click' else None), note
