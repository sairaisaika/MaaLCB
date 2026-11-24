"""Durable shop intents. No Maa controller, input, or guessed purchase receipt.

Reserve before attempting input. A reservation means the action may have been
sent, so a restart never repeats it. Only a new, hash-bound independent successor
can reconcile it. Shop coins are separate from module/lunacy budgets.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import re
from pathlib import Path

from .storage import read_json, write_json
from .shop_vision import (currency, offers, refreshes, matching_purchase_question,
                          PRICE_PATTERN, SHELF_PRICE_FLOOR, shelf_tokens, CURRENCY_X,
                          CURRENCY_Y, _inside, _scales)
from .vision import Text


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid shop ' + label)
    return value


def _key(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Shop offer needs its complete title')
    return ' '.join(name.split()).casefold()


# The shop's own typeface draws ``i``, ``l`` and ``1`` with one stem, and ``o`` with
# the ``0`` it prints for prices, so the reader that named a card at reservation can
# name that same card at reconciliation with the other letter.  Live
# ``window-20261012-221212`` reserved "Today's Expression" and its successor printed
# the very same slot, price and Purchased badge as "Today's Expresslon": the receipt
# then found no bought card, fell back to the whole-shelf comparison and refused a
# purchase the counter had already charged (2993 -> 2804 for 189).  A card is matched
# by the shelf's own history plus its badge and price, never by one glyph of its
# title.  This fold is *not* a fuzzy title match: ``matching_purchase_question``
# still demands the complete name, and two titles must be the same string after the
# confusable class and the typeface's own spacing are folded.
#
# The condensed face also closes ``rn`` into the one stem pair a reader can take for
# ``m``: live ``pi-20261014-080122`` reserved a purchase on a six-slot shelf whose own
# frames read its 160-coin slot as "Thomy Path", and the returning shelf printed that
# same slot, price and card as "Thorny Path" (its catalogue name).  The badge path then
# called a card the shelf had held all along an offer it "never held" and stopped the
# run at floor 3.  Folding the ligature compares the card, not the reader's opinion of
# its fourth glyph.
#
# The same reader also loses the space the typeface draws between two words: live
# ``pi-20261014-082326`` reserved a card from a shelf whose own frame-0002 read the
# 144-coin slot as "Crownof Roses", and the returning shelf (frame-0008) printed the
# catalogue spacing "Crown of Roses".  Two keys then differed by one blank and the run
# stopped after 3 inputs on the very refusal above.  Folding the whitespace compares the
# card, not the reader's spacing; it cannot shorten a title, because the letters and
# digits still have to agree one for one.
_CONFUSABLE = str.maketrans({'i': '1', 'l': '1', '!': '1', '|': '1', 'o': '0',
                             '\u2019': "'", '\u02bc': "'", '\u00b4': "'", '`': "'"})


def _fold(name):
    return _key(name).translate(_CONFUSABLE).replace('rn', 'm').replace(' ', '')


def _same_title(one, other):
    """Whether a re-read shelf row is still the card an intent was written for."""
    return _key(one) == _key(other) or _fold(one) == _fold(other)


#: How alike the notice's title and the bought card's title must read, and by how much
#: the bought card must beat every other card of the same shelf.
NOTICE_SIMILARITY = .8
NOTICE_MARGIN = .15


def _notice_names(read, pending):
    """Does the gift notice name the card this purchase was written for?

    The notice prints the gift's name in a display typeface whose ``v`` reads as ``u``:
    live ``pi-20261123-194800/frame-0078`` printed "milepost of Suruiual" for the
    "Milepost of Survival" bought a few seconds earlier, two glyphs off, and the run
    stopped on a purchase that had gone through. A notice can only be for a card of the
    shelf the purchase was made from, and the transaction holds that shelf. So the
    question is which card of the shelf the notice reads closest to: it names the
    bought card when it reads like it and clearly less like every other card.
    """
    if _same_title(read, pending['name']):
        return True
    from difflib import SequenceMatcher

    def alike(name):
        return SequenceMatcher(None, _fold(read), _fold(name)).ratio()
    bought = alike(pending['name'])
    others = [alike(row['name']) for row in pending.get('shelf') or ()
              if isinstance(row, dict) and isinstance(row.get('name'), str) and row['name'].strip()
              and not _same_title(row['name'], pending['name'])]
    return bought >= NOTICE_SIMILARITY and all(bought - other >= NOTICE_MARGIN for other in others)


def _one_glyph_apart(one, other):
    """Equal-length titles whose folded keys differ in exactly one position.

    This is the page-identity comparison's tolerance, not a title match: it is only ever
    asked between two rows a single shelf read on one page, never to name a purchase.  The
    typeface draws ``a`` and ``o`` with the same bowl at this size, so live
    ``pi-20261016-011659`` re-read the very slot its own reservation had read as "Voodoo
    Doll" as "Vaodoo Doll" -- same slot, same 149, same visit -- and the successor check
    called it an offer the shelf never held and stopped the run before its first input.
    Enumerating glyph pairs one at a time is what let that class of stop recur, so this
    side counts differing positions instead.  The title still cannot shorten and the price
    still has to agree, because both are checked beside this.
    """
    first, second = _fold(one), _fold(other)
    return len(first) == len(second) and sum(a != b for a, b in zip(first, second)) == 1


def _context(context):
    """Copy a decision context, keeping the bought *names* and never the records.

    A record carries its own decision context, so storing the records made every purchase
    embed the previous one: live ``pi-20261014-082856`` could not start at all because
    ``config/user-shop-<scope>.json`` had reached 2,464,332 bytes and the reader refused
    its own state (``Configuration/state exceeds 2 MiB``).  The store keeps what the value
    model reads -- names, which is also what ``shop_value_training._text_list`` accepts.
    """
    out = copy.deepcopy(context)
    owned = out.get('owned_bought')
    if owned is None:
        return out
    if not isinstance(owned, list):
        raise ValueError('Invalid shop decision context')
    names = []
    for row in owned:
        if isinstance(row, str) and row:
            names.append(row)
        elif isinstance(row, dict) and isinstance(row.get('name'), str) and row['name']:
            names.append(row['name'])
        else:
            raise ValueError('Invalid shop decision context')
    out['owned_bought'] = names
    return out


def _frame(path):
    path = Path(path).resolve()
    record = read_json(path)
    if not isinstance(record, dict) or not isinstance(record.get('ocr'), list):
        raise ValueError('Invalid shop observation')
    size = record.get('size')
    if (not isinstance(size, list) or len(size) != 2
            or any(type(n) is not int or n <= 0 for n in size)):
        raise ValueError('Invalid shop frame size')
    png = path.with_suffix('.png')
    png_hash = hashlib.sha256(png.read_bytes()).hexdigest()
    if png_hash != record.get('image_sha256'):
        raise ValueError('Shop frame PNG hash differs')
    texts = []
    for row in record['ocr']:
        if (not isinstance(row, dict) or not isinstance(row.get('text'), str)
                or type(row.get('score')) not in (int, float)
                or not 0 <= row['score'] <= 1 or not isinstance(row.get('box'), list)
                or len(row['box']) != 4
                or any(type(n) is not int for n in row['box'])):
            raise ValueError('Invalid shop OCR record')
        x, y, width, height = row['box']
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > size[0] or y + height > size[1]:
            raise ValueError('Shop OCR box outside image')
        texts.append(Text(row['text'], tuple(row['box']), row['score']))
    proof = dict(path=str(path), json_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 png_sha256=png_hash)
    return record, texts, size, proof


def _verify(proof):
    if (not isinstance(proof, dict) or not isinstance(proof.get('path'), str)
            or any(not isinstance(proof.get(key), str)
                   or not re.fullmatch(r'[0-9a-f]{64}', proof[key])
                   for key in ('json_sha256', 'png_sha256'))):
        raise ValueError('Invalid retained shop proof; preserve pending')
    record, texts, size, current = _frame(proof['path'])
    if current != proof:
        raise ValueError('Retained shop proof changed; preserve pending')
    return record, texts, size


def _later_skill_capture(before, after):
    try:
        start = datetime.fromisoformat(before['utc'])
        end = datetime.fromisoformat(after['utc'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Skill successor needs original capture timestamps') from error
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('Skill successor must follow the reserved capture')


def _unspent_skill_chooser(pending, record, texts, size, proof):
    from .shop_skill_vision import read_replacement_modal

    modal = read_replacement_modal(texts, size) if record.get('scene') == 'UNKNOWN_DIALOG' else None
    if modal is None or modal.sinner != pending['skill']['sinner'] or modal.balance != pending['coins']:
        raise ValueError('Skill chooser owner or unchanged balance not proven')
    selection = pending.get('selection')
    if selection:
        before, before_texts, before_size = _verify(selection.get('frame'))
        if proof['png_sha256'] == selection['frame']['png_sha256']:
            raise ValueError('Wait for an independent skill selection successor')
        _later_skill_capture(before, record)
        previous = read_replacement_modal(before_texts, before_size)
        if (previous is None or previous.sinner != modal.sinner or previous.balance != modal.balance
                or previous.counts != modal.counts):
            raise ValueError('Unchanged skill counts not proven; preserve pending')
    return modal


def _coins(texts, size):
    sx, sy = _scales(size)
    candidates = [t for t in texts if t.score >= .9 and PRICE_PATTERN.fullmatch(t.text)
                  and _inside(t.box, CURRENCY_X, CURRENCY_Y, sx, sy)]
    if len(candidates) != 1:
        raise ValueError('Unique high-confidence shop currency not proven')
    return currency(candidates, size)


def _shelf(texts, size):
    found = offers(shelf_tokens(texts), size)
    return [dict(name=o.name, price=o.price, click=list(o.click),
                 **({'purchased':True} if o.purchased else {})) for o in found]


def purchase_execution_witness(prior, following, name, price, coins_before, coins_after):
    """Shared strong execution teacher; never a label of purchase value.

    Own Purchased badge and exact spend suffice even when unrelated shelf text
    changes. Without that badge, require the complete remaining shelf. The live
    transaction's weaker dialog-bound currency-only recovery is deliberately not
    a training witness.
    """
    if (type(price) is not int or price < 0 or type(coins_before) is not int
            or type(coins_after) is not int or coins_before < price
            or coins_after != coins_before-price):
        raise ValueError('Exact shop purchase currency delta not proven')
    chosen=[o for o in prior if _same_title(o['name'],name)]
    kept=[o for o in following if _same_title(o['name'],name)]
    if len(chosen)!=1 or chosen[0]['price']!=price or chosen[0].get('purchased'):
        raise ValueError('Unique unpurchased baseline offer not proven')
    if kept:
        if len(kept)!=1 or kept[0]['price']!=price or not kept[0].get('purchased'):
            raise ValueError('Own Purchased badge not proven')
        # Existing content-addressed samples used exact title keys plus a fully
        # unchanged other shelf. Keep their identity and human review ownership.
        others=lambda rows:sorted((_key(o['name']),o['price']) for o in rows
                                 if _key(o['name'])!=_key(name))
        if (_key(chosen[0]['name'])==_key(name) and _key(kept[0]['name'])==_key(name)
                and others(prior)==others(following)):
            return 'complete_shelf_purchased_badge'
        return 'own_purchased_badge'
    others=lambda rows:sorted((_key(o['name']),o['price']) for o in rows
                             if not _same_title(o['name'],name))
    if others(prior)!=others(following):
        raise ValueError('Complete remaining shelf not proven')
    return 'removed_offer'


def refreshed_gifts(rows):
    """The shelf rows a refresh restocks: the gifts, without the Super Shop's services.

    The Super Shop's first row also sells services ("ID Skill Search", "Replace <sinner>'s
    Skill"). They are not restocked like gifts (ID Skill Search stays put), and their
    price prints as ``??``, which full-frame OCR sometimes reads as ``77`` and sometimes
    not at all. Counting them made the same shelf read 6 rows before a refresh and 7
    after it (live ``pi-20261121-200305``, frames 0043 and 0045), and a correct refresh
    with an exact 15-coin delta was refused.
    """
    from .shop_skill_vision import looks_like_skill_service
    return [row for row in rows or () if not looks_like_skill_service(row['name'])]


def _baseline(pending):
    """The pre-action shelf as the *current* reader sees the retained frame.

    ``pending['shelf']`` was read by whichever build reserved the intent.  A later
    build may read that very same frame with more recall -- the price is the same
    price, the old reader just dropped it at its score cut -- so comparing a
    successor against the stored list would refuse a shelf that never changed.
    ``_pending`` already verifies ``pending['before']``, so re-reading it keeps both
    sides of the comparison on one reader.  Within a single build this is a no-op.
    """
    _, texts, size = _verify(pending['before'])
    return _shelf(texts, size)


def _notice(texts, record):
    """The native ``E.G.O Gift GET!`` notice a shop purchase raises over the shelf.

    The notice's own identity -- its title band and its single Confirm -- is read by
    the shop reader, never by this transaction, and nothing is clicked from here.  A
    scene that is not the notice is refused: the caller only reaches this method
    because the page was named GIFT_GET, so an unread notice must stop the run rather
    than let a later frame pass as one.
    """
    from .shop_skill_vision import read_overlay
    result = read_overlay(texts, record.get('size'), scene=record.get('scene'),
                          require_scene='GIFT_GET')
    if not result['available']:
        raise ValueError('Native E.G.O Gift GET notice not proven')
    if not result['complete'] or not result['target']:
        raise ValueError('Notice Confirm not proven; never click an unread notice')
    return result


class ShopNoticeNameUnproven(ValueError):
    """A named offer is pending and its notice is visible, but the name needs a fresh read."""


class ShopTransaction:
    """One durable store per run; visit IDs must come from proven shop entry.

    ``begin_visit`` keeps completed purchases for the entire run. A second visit
    requires ``close_visit`` with a fresh MAP successor; UNKNOWN never resets a
    refresh limit. All mutation failures preserve previous persisted bytes.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.data = read_json(self.path) if self.path.exists() else None
        if self.data is not None:
            d = self.data
            if (not isinstance(d, dict) or d.get('version') != 1
                    or not isinstance(d.get('scope'), str) or not d['scope']
                    or not isinstance(d.get('visits'), dict)
                    or not isinstance(d.get('bought'), list)
                    or d.get('pending') is not None and not isinstance(d.get('pending'), dict)):
                raise ValueError('Invalid shop transaction; do not overwrite')
            for visit in d['visits'].values():
                if not isinstance(visit, dict) or type(visit.get('refreshes')) is not int or visit['refreshes'] < 0:
                    raise ValueError('Invalid persisted shop visit')
            if d.get('current_visit') not in d['visits']:
                raise ValueError('Invalid persisted current shop visit')
            for bought in d['bought']:
                if not isinstance(bought, dict):
                    raise ValueError('Invalid persisted shop receipt')
                _key(bought.get('name'))
                _integer(bought.get('price'), 'persisted receipt price', 1)
            pending = d.get('pending')
            if pending == {}:
                raise ValueError('Empty persisted shop intent is not a completed action')
            if pending:
                if (pending.get('scope') != d['scope'] or pending.get('visit') != d['current_visit']
                        or pending.get('kind') not in ('purchase', 'refresh', 'skill_service', 'skill_replacement')
                        or pending.get('stage') not in ('card_intent', 'confirm_intent',
                                                        'overlay_intent', 'refresh_intent', 'skill_open_intent', 'skill_confirm_intent')
                        or not isinstance(pending.get('before'), dict)
                        or not isinstance(pending.get('shelf'), list)):
                    raise ValueError('Invalid persisted shop intent')
                if pending['kind'] != 'skill_service':
                    _integer(pending.get('price'), 'persisted price', 1)
                _integer(pending.get('coins'), 'persisted coins')
                if pending['kind'] == 'purchase':
                    _key(pending.get('name'))
                    if pending['stage'] not in ('card_intent', 'confirm_intent', 'overlay_intent'):
                        raise ValueError('Invalid purchase intent stage')
                    if pending['stage'] == 'confirm_intent' and not isinstance(pending.get('question'), dict):
                        raise ValueError('Purchase Confirm needs its retained question proof')
                    if pending['stage'] == 'overlay_intent':
                        overlay = pending.get('overlay_acknowledgement')
                        if (not isinstance(overlay, dict)
                                or not isinstance(overlay.get('frame'), dict)
                                or not isinstance(overlay.get('before'), dict)
                                or overlay.get('kind') != 'ego_gift_get_notice'
                                or overlay.get('scope') != d['scope']
                                or overlay.get('visit') != d['current_visit']):
                            raise ValueError('Notice acknowledgement needs its retained notice proof')
                elif pending['kind'] == 'skill_service':
                    if pending['stage'] != 'skill_open_intent' or not isinstance(pending.get('skill'), dict):
                        raise ValueError('Invalid pending skill opener')
                elif pending['kind'] == 'skill_replacement':
                    if (pending['stage'] != 'skill_confirm_intent' or not isinstance(pending.get('question'), dict)
                            or not isinstance(pending.get('skill'), dict)):
                        raise ValueError('Skill replacement requires the original chooser and selected skill intent')
                elif pending['stage'] != 'refresh_intent':
                    raise ValueError('Invalid refresh intent stage')

    def _save(self, data):
        write_json(self.path, data)
        self.data = data

    def _bound(self, scope, visit):
        if not self.data or self.data['scope'] != scope or self.data.get('current_visit') != visit:
            raise ValueError('Shop intent belongs to another run/visit')
        if self.data['visits'][visit].get('closed'):
            raise ValueError('Shop visit already closed')

    def _ready(self, scope, visit):
        self._bound(scope, visit)
        if self.data['pending']:
            raise ValueError('Unresolved shop intent; never repeat input')

    @property
    def bought_names(self):
        return [entry['name'] for entry in (self.data or {}).get('bought', [])]

    def refreshes_used(self, scope, visit):
        self._bound(scope, visit)
        return self.data['visits'][visit]['refreshes']

    def begin_visit(self, scope, visit, frame_path, learning_context=None):
        if not isinstance(scope, str) or not scope or not isinstance(visit, str) or not visit:
            raise ValueError('Shop requires explicit run scope and visit')
        if self.data and self.data['scope'] != scope:
            raise ValueError('Archive prior shop scope explicitly before starting another')
        record, texts, size, proof = _frame(frame_path)
        if record.get('scene') != 'SHOP' or not _shelf(texts, size):
            raise ValueError('Independent shop shelf required')
        _coins(texts, size)
        if self.data:
            if self.data['pending']:
                raise ValueError('Unresolved shop intent; never reset visit')
            if visit in self.data['visits']:
                self._bound(scope, visit)
                return False  # Idempotent startup keeps limit and exact bytes.
            previous = self.data['visits'][self.data['current_visit']]
            if not previous.get('closed'):
                raise ValueError('A fresh MAP exit is required before a new shop visit')
            if proof['png_sha256'] == previous['entry']['png_sha256']:
                raise ValueError('Replayed shop entry')
        data = copy.deepcopy(self.data) if self.data else dict(
            version=1, scope=scope, visits={}, bought=[], pending=None)
        data['current_visit'] = visit
        data['visits'][visit] = dict(entry=proof, refreshes=0, closed=False,
                                     overlay_acknowledgements=[])
        if learning_context is not None:
            if (not isinstance(learning_context,dict) or set(learning_context)!=
                    {'keywords','wanted','reserve_coins'} or
                    any(not isinstance(learning_context[k],list) or
                        any(not isinstance(x,str) or not x for x in learning_context[k])
                        for k in ('keywords','wanted'))):
                raise ValueError('Invalid captured shop learning context')
            _integer(learning_context['reserve_coins'],'captured reserve')
            data['visits'][visit]['learning_context']=copy.deepcopy(learning_context)
        self._save(data)
        return True

    def _before(self, frame_path):
        record, texts, size, proof = _frame(frame_path)
        if record.get('scene') != 'SHOP':
            raise ValueError('Shop action needs a fresh shelf')
        return texts, size, proof, _coins(texts, size), _shelf(texts, size)

    def reserve_purchase(self, scope, visit, offer, coins, frame_path, reserve_coins=0, decision_context=None):
        from .shop_skill_vision import is_skill_service

        self._ready(scope, visit)
        name = offer.name if hasattr(offer, 'name') else offer['name']
        if is_skill_service(name):
            raise ValueError('Skill services require a chooser opening, not a gift intent')
        price = offer.price if hasattr(offer, 'price') else offer['price']
        _integer(price, 'price', 1)
        _integer(coins, 'currency')
        _integer(reserve_coins, 'reserve')
        if _key(name) in {_key(n) for n in self.bought_names}:
            raise ValueError('Shop title already receipted in this run')
        texts, size, proof, observed_coins, shelf = self._before(frame_path)
        matching = [o for o in shelf if _key(o['name']) == _key(name) and o['price'] == price]
        if len(matching) != 1 or observed_coins != coins or price > coins-reserve_coins:
            raise ValueError('Fresh exact shop title/price/currency not proven')
        data = copy.deepcopy(self.data)
        data['pending'] = dict(kind='purchase', stage='card_intent', scope=scope, visit=visit,
                               name=name, price=price, coins=coins, before=proof,
                               shelf=shelf, click=matching[0]['click'])
        if decision_context is not None:
            if not isinstance(decision_context,dict):raise ValueError('Invalid shop decision context')
            data['pending']['decision_context']=_context(decision_context)
        self._save(data)
        return matching[0]['click']

    def reserve_skill_service(self, scope, visit, name, frame_path, mode, reserve_coins, deployment):
        """Reserve opening the chooser without treating the shelf's `??` as a quote."""
        from .shop_skill_policy import SKILL_MODES, choose_skill_service
        from .shop_skill_vision import named_skill_services

        self._ready(scope, visit)
        _integer(reserve_coins, 'reserve')
        texts, size, proof, coins, _ = self._before(frame_path)
        matches = [offer for offer in named_skill_services(texts,size) if offer['name'] == name]
        attempts = self.data['visits'][visit].get('skill_service_attempts', [])
        if (mode not in SKILL_MODES[1:] or len(matches) != 1
                or not choose_skill_service(matches,coins,reserve_coins,deployment,scope,attempts,())):
            raise ValueError('Skill service needs an untried exact frontline identity and enabled policy')
        match = matches[0]
        data = copy.deepcopy(self.data)
        data['visits'][visit].setdefault('skill_service_attempts', []).append(match['sinner'])
        data['pending'] = dict(kind='skill_service',stage='skill_open_intent',scope=scope,visit=visit,
                               coins=coins,before=proof,shelf=[],click=match['box'],
                               skill=dict(sinner=match['sinner'],mode=mode,reserve_coins=reserve_coins))
        self._save(data)
        return match['box']

    def reconcile_skill_service(self, scope, visit, frame_path):
        """Verify an opened chooser or return to an independently unchanged balance."""
        pending, record, texts, size, proof = self._pending(scope, visit, 'skill_service', frame_path)
        selection = pending.get('selection')
        if record.get('scene') == 'UNKNOWN_DIALOG' and not pending.get('cancel'):
            _unspent_skill_chooser(pending, record, texts, size, proof)
            return 'chooser'
        elif record.get('scene') == 'SHOP' and _coins(texts,size) == pending['coins']:
            cancel = pending.get('cancel')
            if selection and not cancel:
                raise ValueError('Skill selection needs its own unspent Cancel before shelf settlement')
            if cancel:
                cancelled, cancel_texts, cancel_size = _verify(cancel)
                if proof['png_sha256'] == cancel['png_sha256']:
                    raise ValueError('Independent skill Cancel successor required')
                _later_skill_capture(cancelled, record)
                _unspent_skill_chooser(pending, cancelled, cancel_texts, cancel_size, cancel)
            data = copy.deepcopy(self.data)
            data['visits'][visit].setdefault('unspent_skill_services', []).append(
                dict(before=pending['before'],successor=proof,sinner=pending['skill']['sinner']))
            data['pending'] = None
            self._save(data)
            return 'shelf'
        raise ValueError('Skill service successor or unchanged balance not proven')

    def reserve_skill_selection(self, scope, visit, frame_path, mode, reserve_coins, deployment, expected_target):
        """Select the proposed card once. This intent has no permission to Confirm."""
        from .pre_battle_identity import submitted_identity
        from .shop_skill_policy import propose_replacement
        from .shop_skill_vision import read_replacement_modal

        pending, record, texts, size, proof = self._pending(scope,visit,'skill_service',frame_path)
        skill = pending['skill']
        if (pending.get('cancel') or pending.get('selection') or record.get('scene') != 'UNKNOWN_DIALOG'
                or skill['mode'] != mode or skill['reserve_coins'] != reserve_coins):
            raise ValueError('Skill selection requires the unchanged open intent and can be sent only once')
        modal = read_replacement_modal(texts,size)
        identity = submitted_identity(deployment,scope,skill['sinner'])
        if (not modal or modal.sinner != skill['sinner'] or modal.balance != pending['coins']
                or not identity or identity['role'] != 'frontline'):
            raise ValueError('Exact skill chooser and frontline identity not proven')
        choice = propose_replacement(modal,mode,reserve_coins)
        if not choice or list(choice.quote.select_box) != list(expected_target):
            raise ValueError('Verified skill choice changed before dispatch')
        selection = dict(frame=proof, identity_id=identity['identity_id'], from_tier=choice.quote.from_tier,
                         price=choice.quote.price, counts_after=list(choice.counts_after),coins_after=choice.coins_after,
                         target=list(choice.quote.select_box))
        data = copy.deepcopy(self.data)
        data['pending']['selection'] = selection
        self._save(data)
        return selection

    def reserve_skill_service_cancel(self, scope, visit, frame_path, expected_target):
        """Cancel the matched unspent chooser once, even across restarts."""
        pending, record, texts, size, proof = self._pending(scope, visit, 'skill_service', frame_path)
        if pending.get('cancel'):
            raise ValueError('Skill chooser Cancel already reserved')
        modal = _unspent_skill_chooser(pending, record, texts, size, proof)
        if list(modal.cancel_box) != list(expected_target):
            raise ValueError('Skill chooser Cancel target differs')
        data = copy.deepcopy(self.data)
        data['pending']['cancel'] = proof
        self._save(data)

    def reserve_refresh(self, scope, visit, cost, coins, limit, frame_path, kind='regular', reserve_coins=0):
        self._ready(scope, visit)
        _integer(cost, 'refresh cost', 1)
        _integer(coins, 'currency')
        _integer(limit, 'refresh limit')
        _integer(reserve_coins, 'reserve')
        if kind != 'regular':
            raise ValueError('Keyword refresh policy not verified')
        if self.refreshes_used(scope, visit) >= limit:
            raise ValueError('Shop visit refresh limit reached')
        texts, size, proof, observed_coins, shelf = self._before(frame_path)
        refresh = refreshes([t for t in texts if t.score >= .9], size)['regular']
        if refresh.cost != cost or refresh.box is None or observed_coins != coins or cost > coins-reserve_coins:
            raise ValueError('Fresh shop refresh cost/currency not proven')
        data = copy.deepcopy(self.data)
        # Count attempts, including uncertain ones, before input; restart cannot
        # evade the configured cap by crashing between click and reconciliation.
        data['visits'][visit]['refreshes'] += 1
        data['pending'] = dict(kind='refresh', stage='refresh_intent', scope=scope, visit=visit,
                               price=cost, coins=coins, before=proof, shelf=shelf,
                               click=list(refresh.box))
        self._save(data)
        return list(refresh.box)

    def _pending(self, scope, visit, kind, frame_path):
        self._bound(scope, visit)
        pending = self.data['pending']
        if not pending or pending.get('kind') != kind:
            raise ValueError('Matching pending shop action required')
        before, _, _ = _verify(pending['before'])
        if pending.get('question'):
            _verify(pending['question'])
        record, texts, size, proof = _frame(frame_path)
        previous = pending.get('question') or pending['before']
        if proof['png_sha256'] == previous['png_sha256']:
            raise ValueError('Shop successor is a stale original frame')
        if kind == 'skill_service':
            _later_skill_capture(before, record)
        return pending, record, texts, size, proof

    def reserve_confirm(self, scope, visit, frame_path):
        pending, record, texts, size, proof = self._pending(scope, visit, 'purchase', frame_path)
        if pending['stage'] != 'card_intent':
            raise ValueError('Shop Confirm already reserved; never repeat')
        if record.get('scene') != 'SHOP_PURCHASE':
            raise ValueError('Independent shop purchase question required')
        # The redesigned client prints no question sentence at all: the modal is the
        # gift's own band, the before -> after badge and the two buttons.  The proof is
        # therefore the same one the runner's SHOP_PURCHASE branch computes (gift band
        # matched by its words, badge spending exactly the reserved price, coin counter
        # on the reserved intent), never the retired ``Would you like to purchase ...?``
        # wording the live pi-20261015-214921 run died on.
        from .shop_vision import purchase_dialog_answer
        answer = purchase_dialog_answer(texts, pending['name'], pending['price'], size,
                                        coins=pending['coins'])
        if answer is not None and answer[0] == 'purchase':
            target = list(answer[1])
        else:
            # The older client printed the reservation as its own question sentence
            # ("Would you like to purchase ...?"), and both generations are proofs of
            # the same thing, so either one may carry the reservation.
            target = matching_purchase_question(texts, pending['name'], pending['price'], size,
                                                coins=pending['coins'])
            if target is None:
                raise ValueError('Full matching purchase title/price/question not proven')
        data = copy.deepcopy(self.data)
        data['pending'].update(stage='confirm_intent', question=proof, confirm=target)
        self._save(data)
        return target

    def retire_pending(self, scope, visit, reason=None):
        """Drop a reserved intent the page itself never asked about.

        The live 21:24:38 run resumed a 159-coin reservation onto a dialog whose own
        badge asked 390: the modal on screen is not the question this project
        reserved, so its Cancel is the answer and the reservation is retired with it
        *before* the click.  Without this the stale intent would keep the shelf
        unreadable -- a fresh purchase would be refused as 'already reserved' -- so
        the visit is left able to read itself again.  Nothing is recorded as bought:
        the reason is written into the visit instead.
        """
        self._bound(scope, visit)
        pending = self.data['pending']
        if not pending:
            raise ValueError('No pending shop action to retire')
        if pending['kind'] in ('skill_service', 'skill_replacement'):
            raise ValueError('Skill action may have been sent; preserve pending until a successor is proven')
        data = copy.deepcopy(self.data)
        data['pending'] = None
        row = data['visits'][visit]
        row['retired'] = list(row.get('retired') or []) + [
            dict(name=pending.get('name'), price=pending.get('price'), why=reason)]
        self._save(data)
        return True

    def preview_overlay_acknowledgement(self, scope, visit, frame_path):
        """Prove the notice control without creating a dispatch intent."""
        return list(self._overlay_acknowledgement(scope, visit, frame_path)['target'])

    def reserve_overlay_acknowledgement(self, scope, visit, frame_path, *, expected_target=None):
        """Anchor the one input that clears a purchase's own ``E.G.O Gift GET!`` notice.

        A real purchase raises this notice over the shelf, so the shelf that proves the
        coins is behind it.  The notice is not a receipt and this method never records
        one: it re-proves the notice against the retained frame, binds the acknowledgement
        to that frame's own PNG hash and to the pending intent, and only then returns the
        notice's own Confirm box for the caller's planner to click.

        It is deliberately single-use per visit and per intent.  Once reserved, a restart
        can never send the acknowledgement again, and a second different notice cannot
        claim the same slot.  An unread notice raises instead of clicking, so an unknown
        pending action is preserved rather than cleared.
        """
        acknowledgement = self._overlay_acknowledgement(scope, visit, frame_path)
        target = list(acknowledgement['target'])
        if expected_target is not None and target != list(expected_target):
            raise ValueError('Shop notice target differs from the planned current control')
        data = copy.deepcopy(self.data)
        data['pending'].update(stage='overlay_intent', overlay_acknowledgement=acknowledgement)
        data['visits'][visit].setdefault('overlay_acknowledgements', []).append(acknowledgement)
        self._save(data)
        return target

    def _overlay_acknowledgement(self, scope, visit, frame_path):
        from .initial_gifts import receipt_name

        pending, record, texts, _, proof = self._pending(scope, visit, 'purchase', frame_path)
        if pending['stage'] != 'confirm_intent':
            raise ValueError('The purchase card intent was not confirmed yet')
        if pending.get('overlay_acknowledgement'):
            raise ValueError('Notice acknowledgement already reserved; never repeat')
        notice = _notice(texts, record)
        gift_name = receipt_name(texts, record['size'])
        if not gift_name:
            raise ShopNoticeNameUnproven('Shop notice gift name is unreadable')
        if not _notice_names(gift_name, pending):
            raise ValueError('Shop notice names a different gift; preserve pending')
        # A notice that re-states an already retained frame is not a successor: both the
        # shelf the purchase started from and the question that was answered are refused,
        # because neither can be the different page the notice has to be.
        retained = [pending['before']]
        if pending.get('question'):
            retained.append(pending['question'])
        if any(proof['png_sha256'] == kept['png_sha256'] for kept in retained):
            raise ValueError('Notice successor repeats a retained frame')
        previous = pending.get('question') or pending['before']
        return dict(scope=scope, visit=visit, kind='ego_gift_get_notice',
                               title=notice['title'], title_box=notice['title_box'], gift_name=gift_name,
                               confirm=notice['confirm'], target=notice['target'],
                               scene=record.get('scene'), before=previous, frame=proof,
                               refused=[], note='the notice proves no purchase; the '
                               'returning shelf still has to prove the coin delta')

    def reconcile_purchase(self, scope, visit, frame_path):
        pending, record, texts, size, proof = self._pending(scope, visit, 'purchase', frame_path)
        # GET overlays need a separate native receipt parser. Until that parser is
        # supplied, only an independent shelf with exact coin delta AND removed
        # offer is sufficient; a generic GET/caller-provided title proves nothing.
        if record.get('scene') != 'SHOP':
            raise ValueError('Shop purchase receipt/shelf still unknown; preserve pending')
        coins = _coins(texts, size)
        shelf = _shelf(texts, size)
        if coins == pending['coins'] and shelf:
            # An intent whose click left the shop's own purchase question behind: the
            # shelf still prints the card once, at the price and without the Purchased
            # badge it had when the intent was written, and the visit's currency is
            # exactly what it was.  Nothing was bought, so the intent is dropped unspent
            # (live: window-20261012-210547, whose shelf offer "Replace Don Qubote's Sil"
            # opened the skill-replacement chooser instead of a purchase question).
            still = [o for o in shelf if _same_title(o['name'], pending['name'])]
            if (pending['stage'] == 'card_intent' and len(still) == 1
                    and still[0]['price'] == pending['price']
                    and not still[0].get('purchased')):
                data = copy.deepcopy(self.data)
                data.setdefault('unspent_intents', []).append(dict(
                    name=pending['name'], price=pending['price'], visit=visit,
                    stage=pending['stage'], successor=proof,
                    shelf_evidence='unchanged_shelf_and_untouched_currency'))
                data['pending'] = None
                self._save(data)
                return True
        if coins is None and shelf:
            # The counter this frame does not print cannot prove a deduction, and it
            # cannot deny one either: `-190450` confirmed the question and then died on
            # this very check because the dialog never shows a balance.  Keep the
            # pending intent and answer "not verified yet", so the next frame can try
            # again instead of ending a run over an unreadable counter (D421).
            data = copy.deepcopy(self.data)
            data.setdefault('unverified_attempts', []).append(dict(
                name=pending['name'], price=pending['price'], visit=visit,
                reason='the_currency_counter_is_unreadable_on_this_frame',
                successor=proof))
            self._save(data)
            return False
        if coins != pending['coins'] - pending['price'] or not shelf:
            raise ValueError('Exact shop purchase currency delta not proven')
        if pending['stage'] not in ('confirm_intent','overlay_intent'):
            raise ValueError('Exact currency delta has no reserved shop Confirm; preserve pending')
        baseline = _baseline(pending) or pending['shelf']
        bought=[o for o in shelf if _same_title(o['name'], pending['name'])]
        if bought:
            # Actual native shop retains and reorders the card, with Purchased
            # above its art. The badge must belong to this title and price, where the
            # title may differ only by the typeface's confusable glyphs (see _same_title).
            purchase_execution_witness(baseline,shelf,pending['name'],pending['price'],
                                       pending['coins'],coins)
            # The card's own Purchased badge plus the exact coin delta above is the
            # receipt, so the *other* slots do not have to be re-read: the shelf keeps
            # and reorders its cards, and one faint badge below the reader's floor used
            # to turn a completed purchase into "Independent complete successor shelf
            # not proven" (window-20261012-203743 frame-0149, the Gemstone Oscillator's
            # own badge read at .763 where its neighbour read .823).  What stays refused
            # is a successor showing a card this shelf never held, because that would
            # mean the receipt is a different page.  A title that differs only in the
            # typeface's own confusable glyph counts as the card that was held.
            held = {_key(offer['name']) for offer in baseline}
            held |= {_fold(offer['name']) for offer in baseline}

            def held_offer(offer):
                if _key(offer['name']) in held or _fold(offer['name']) in held:
                    return True
                # One reading of the typeface's own noise still names the card the shelf
                # held; see _one_glyph_apart.  The bought card is not asked here -- it is
                # matched by _same_title above -- so this can never rename a purchase.
                return any(offer['price'] == kept['price']
                           and _one_glyph_apart(offer['name'], kept['name'])
                           for kept in baseline)

            unheld = [offer['name'] for offer in shelf
                      if not _same_title(offer['name'], pending['name'])
                      and not held_offer(offer)]
            # The receipt is the card's own Purchased badge plus the exact currency delta
            # proven above.  An offer this session never saw says the shelf is a
            # different instance than the one the reservation was made on -- a shop that
            # re-rolled between the two sessions of a resumed run -- and that is not
            # evidence about what the account paid.  It is recorded, not raised.
            successor_note = (dict(reason='the_successor_shelf_holds_offers_this_session_'
                                          'never_saw', offers=unheld[:6],
                                   expected=[offer['name'] for offer in baseline][:6])
                              if unheld else None)
        else:
            # Without the card's own badge the *exact currency delta* proven above is the
            # receipt: the account paid exactly the reserved price for exactly the
            # reserved card.  The successor shelf can only corroborate that, and the
            # redesigned client does not always let it: live run pi-20261015-215812
            # resumed a reservation the previous run left behind, paid its 390
            # (1809 -> 1419), and the successor shelf still printed the truncated title
            # ("Clear Mirror, Calm Wate") at the same price with no Purchased badge, so
            # demanding a complete successor shelf ended a run that had just bought
            # correctly.  The difference is now recorded on the receipt instead of raised;
            # the card's *identity* never comes from the shelf, only from the reservation
            # and the dialog the click answered, so a successor cannot rename the purchase.
            remaining = sorted((_fold(o['name']), o['price']) for o in baseline
                               if not _same_title(o['name'], pending['name']))
            actual = sorted((_fold(o['name']), o['price']) for o in shelf
                            if not _same_title(o['name'], pending['name']))
            successor_note = None if actual == remaining else dict(
                expected=[list(row) for row in remaining], observed=[list(row) for row in actual],
                reason='the_successor_shelf_could_not_corroborate_the_exact_currency_delta')
        data = copy.deepcopy(self.data)
        data['bought'].append(dict(name=pending['name'], price=pending['price'],
                                   visit=visit, before=pending['before'],
                                   question=pending.get('question'), successor=proof,
                                   shelf_evidence=('own_purchased_badge' if bought else
                                                   'removed_offer' if successor_note is None else
                                                   'exact_currency_delta'),
                                   successor_note=successor_note,
                                   decision_context=pending.get('decision_context'),
                                   overlay_acknowledgement=pending.get('overlay_acknowledgement')))
        data['pending'] = None
        self._save(data)
        return True

    def reconcile_refresh(self, scope, visit, frame_path):
        pending, record, texts, size, proof = self._pending(scope, visit, 'refresh', frame_path)
        shelf = refreshed_gifts(_shelf(texts, size))
        before = refreshed_gifts(_baseline(pending) or pending['shelf'])
        fingerprint = lambda rows: sorted((_key(o['name']), o['price']) for o in rows)
        coins = _coins(texts, size)
        paid = None if coins is None else pending['coins'] - coins
        # A refresh can also be free: floor 4 of pi-20261122-004911 restocked the Super
        # Shop for 0 coins (2383 before and after) while the button's own price rose
        # 15 -> 30, as a paid refresh does. Zero is accepted only with that rise as proof
        # the press registered; any other delta still stops the run.
        next_price = refreshes(texts, size)['regular'].cost
        free = paid == 0 and next_price is not None and next_price > pending['price']
        if (record.get('scene') != 'SHOP' or not (paid == pending['price'] or free)
                or not shelf or fingerprint(shelf) == fingerprint(before)
                or len(shelf) != len(before)):
            raise ValueError('Fresh refresh currency delta and complete changed shelf not proven')
        data = copy.deepcopy(self.data)
        data['visits'][visit].setdefault('refresh_receipts', []).append(
            dict(before=pending['before'], successor=proof, price=pending['price'], paid=paid,
                 **({'free': True, 'next_price': next_price} if free else {})))
        data['pending'] = None
        self._save(data)
        return True

    def reconcile_skill_replacement(self, scope, visit, frame_path):
        """Settle a possibly dispatched skill Confirm against a new chooser observation."""
        from .shop_skill_policy import propose_replacement
        from .shop_skill_vision import read_replacement_modal

        pending, record, texts, size, proof = self._pending(scope, visit, 'skill_replacement', frame_path)
        if record.get('scene') != 'UNKNOWN_DIALOG' or proof['png_sha256'] == pending['before']['png_sha256']:
            raise ValueError('Independent skill chooser successor required')
        question, before_texts, before_size = _verify(pending['question'])
        _later_skill_capture(question, record)
        before = read_replacement_modal(before_texts, before_size)
        after = read_replacement_modal(texts, size)
        skill = pending['skill']
        if (question.get('scene') != 'UNKNOWN_DIALOG' or before is None or after is None
                or before.sinner != skill.get('sinner') or after.sinner != before.sinner
                or before.balance != pending['coins']):
            raise ValueError('Matching skill chooser and owner not proven')
        proposal = propose_replacement(before, skill.get('mode'), skill.get('reserve_coins'))
        if (proposal is None or proposal.quote.from_tier != skill.get('from_tier')
                or proposal.quote.price != pending['price']):
            raise ValueError('Retained skill replacement quote differs from the reserved policy')
        if after.counts != proposal.counts_after or after.balance != proposal.coins_after:
            raise ValueError('Exact skill counts and coin delta not proven; preserve pending')

        data = copy.deepcopy(self.data)
        receipt = dict(sinner=before.sinner, from_tier=proposal.quote.from_tier, to_tier=3,
                       price=proposal.quote.price, counts_before=list(before.counts), counts_after=list(after.counts),
                       coins_before=before.balance, coins_after=after.balance,
                       before=pending['question'], successor=proof)
        data['visits'][visit].setdefault('skill_receipts', []).append(receipt)
        data['pending'] = None
        self._save(data)
        return receipt

    def close_visit(self, scope, visit, frame_path):
        self._ready(scope, visit)
        record, texts, size, proof = _frame(frame_path)
        _verify(self.data['visits'][visit]['entry'])
        if record.get('scene') != 'MAP' or proof['png_sha256'] == self.data['visits'][visit]['entry']['png_sha256']:
            raise ValueError('Fresh independent MAP exit required; UNKNOWN never resets shop')
        # Caller must independently classify MAP via Maa. This transaction never
        # promotes UNKNOWN to MAP or grants a Leave input of its own.
        data = copy.deepcopy(self.data)
        data['visits'][visit].update(closed=True, exit=proof)
        self._save(data)
