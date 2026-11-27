"""Write assets/resource/base/gift-facts.json from the wiki's E.G.O Gift data table.

Facts only: a gift's name, tier, shop cost, keyword, affinity, how many times it can be
enhanced, and *which kinds of effect* its description mentions. The description text
itself is game text and is not written anywhere; neither is artwork. The source is the
Lua data module the wiki builds its "List of E.G.O Gifts" from, ``Module:EgoGift/data``
on limbuscompany.wiki.gg; the wiki states its own licence, which is recorded next to
the page's revision id.

The table is read strictly: every line that is not blank or a comment must be one gift
entry of the shape ``["Key"] = { field = value, ... },``. Anything else stops the import
instead of being skipped, so a change in the module's layout is noticed here and not as
a silently shorter list.

    python tools/import_wiki_gift_facts.py --fetch           # ask the wiki API
    python tools/import_wiki_gift_facts.py --saved FILE      # replay a saved response
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = 'https://limbuscompany.wiki.gg/api.php'
PAGE = 'Module:EgoGift/data'
AGENT = 'wiki-data-check/1.0'
TARGET = ROOT / 'assets/resource/base/gift-facts.json'
#: The wiki appends this to a key that would collide with another page; the game prints
#: the name without it.
DISAMBIGUATOR = ' (MD)'
#: An earlier version of a gift the wiki keeps for reference: "Name (Legacy)", or with the
#: season it left in, "Name (Legacy MD5)". Not obtainable; left out. Until version 2 only
#: the bare form was recognised and 61 retired gifts sat in the table.
LEGACY = re.compile(r' \(Legacy(?: [^)]*)?\)$')
TIERS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'EX': 'EX'}
#: The seven status systems and the three damage types a gift can be filed under.
KEYWORDS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge', 'Slash', 'Pierce', 'Blunt')
SYSTEMS = KEYWORDS[:7]
SINS = ('wrath', 'lust', 'sloth', 'gluttony', 'gloom', 'pride', 'envy')

ENTRY = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*\{(.*)\}\s*,?\s*(?:--.*)?$')
FIELD = re.compile(r'(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|(-?\d+))\s*(?:,|$)')
STATUS = re.compile(r'\{\{StatusEffect\|([^|}]+)')

#: Every status the descriptions name, and what kind of thing it is. This table is closed:
#: a status the wiki names and this table does not stops the import, so a new term of the
#: game is classified by a person before any gift carrying it is valued. A value is one of
#: the seven systems (the status belongs to that system: Tremor Burst is Tremor), a term
#: of ``TERMS`` below, or ``unique`` -- a mechanic that belongs to particular Identities
#: or to the one gift that names it, about which nothing general can be said.
STATUS_KIND = {
    # the systems themselves and what only exists inside one of them
    'Burn': 'Burn', 'Bleed': 'Bleed', 'Tremor': 'Tremor', 'Rupture': 'Rupture', 'Sinking': 'Sinking',
    'Poise': 'Poise', 'Charge': 'Charge',
    'Tremor Burst': 'Tremor', 'Amplitude Conversion': 'Tremor', 'Amplitude Entanglement': 'Tremor',
    'Tremor - Scorch': 'Tremor', 'Tremor - Superposition': 'Tremor', 'Tremor - Decay': 'Tremor',
    'Tremor - Chain': 'Tremor', 'Tremor - Hemorrhage': 'Tremor', 'Tremor - Reverb': 'Tremor',
    'Tremor - Distribution': 'Tremor',
    'Charge Barrier': 'Charge', 'Charge Identity': 'Charge',
    'Bloodfeast': 'Bleed', 'Bloodfeast Consumed': 'Bleed', 'Bloodfeast Consumed (shared)': 'Bleed', 'Nails': 'Bleed',
    # what an ally gains
    'Attack Power Up': 'power_up', 'Power Up': 'power_up', 'Slash Power Up': 'power_up',
    'Pierce Power Up': 'power_up', 'Blunt Power Up': 'power_up', 'Lust Power Up': 'power_up',
    'Gloom Power Up': 'power_up', 'Defense Power Up': 'defense_power',
    'Clash Power Up': 'clash_power', 'Base Power Up': 'base_power',
    'Plus Coin Boost': 'coin_power', 'Minus Coin Boost': 'coin_power', 'Unbreakable Coin': 'unbreakable_coin',
    'Offense Level Up': 'offense_level', 'Defense Level Up': 'defense_level',
    'Damage Up': 'damage_up', 'Slash DMG Up': 'damage_up', 'Pierce DMG Up': 'damage_up',
    'Blunt DMG Up': 'damage_up', 'Crit DMG Up': 'critical',
    'Protection': 'damage_taken_down', 'Trauma Shield': 'shield',
    'Haste': 'haste', 'Deathrite -Haste-': 'haste',
    'HP Healing Boost': 'heal', 'HP Healing Down': 'heal',
    'SP Heal Efficiency': 'sp', 'SP Loss Efficiency': 'sp',
    'E.G.O Resource Amp': 'ego_resource', 'Ammo': 'ammo', 'Aggro': 'aggro', 'Discard': 'discard',
    'Assist Defense': 'defense_power',
    # what an enemy is given
    'Defense Level Down': 'enemy_down', 'Offense Level Down': 'enemy_down', 'Power Down': 'enemy_down',
    'Attack Power Down': 'enemy_down', 'Minus Coin Drop': 'enemy_down', 'Paralyze': 'paralyze',
    'Fragile': 'fragile', 'Envy Fragility': 'fragile', 'Slash Resist Down': 'fragile',
    'Blunt Resist Down': 'fragile', 'Bind': 'bind',
}
#: Mechanics of particular Identities, factions or of one gift. Listed by name so that the
#: table above stays closed: a name in neither place is the import's error.
UNIQUE = frozenset((
    'Fanatic', 'Vengeance Mark', 'Curio', 'Art Medium', 'Spark of Inspiration', 'Maggots',
    'Gluttonous Thorn (\u8caa\u98df\u68d8)', 'Backup Candy', 'Hunger (Kkomi)', "The Prescript's Target",
    'Exquisite Aesthetics', 'Emergency Barrier Battery', 'Pink Petals', 'Strider -Mao-',
    'Resident Reg. Microchip', 'Near-light Superbattery', 'Reflux', 'Self Resonance Circuitry',
    'Dhy\u0101na', 'Firepower', 'Delicateness', 'Shimmering -Bloodfiend- (Ally)', 'Karmic Consequence',
    'Torn-out Butterfly', "Dihui Star's Blade", 'Dawnherald', 'Battle Instinct', 'Maturing Textbook',
    'Changing Room (Ishmael)', 'Mark of the King of Needleworks', 'Thundercrack', 'Dullahan', 'Coffin',
    'K Corp. Emergency Ampule (Gift)', 'Blooming Thorn (Ally)', 'Hardblood Armor', 'Hardblood (Ally)',
    'Blood-tinged Scissorblades (Ally)', 'Bloodied Hand (Ally)', 'Glimpse of Precognition', 'Unlock',
    'Grace of the Prescript', 'Unlock - II', 'Requested Target', 'Blessing (E.G.O Gift)', 'Time Moratorium',
    'Borrowed Time', 'Microprecision Time Acceleration', 'Battlefield Retreat', 'Load', 'Dimensional Rift',
    'Hardblood Cast', 'Desperado', 'Hyped-up', 'Pheromone', 'Pheromone Mark', 'High-voltage Exoskeleton',
    'Beauty of the Physique', 'Charm of the Beastly', 'Sword of the Homeland - Striking',
    'Learning by Example', 'Joint Combo', 'A Test of Despair', 'The One Beyond Despair', 'Momentum',
    "Dawn's Camaraderie", 'Embedded Spearhead', 'Nervous Impairment', 'Man in Scabbard',
))
#: A gift whose whole effect is written for named Identities: the description opens with
#: the restriction. A bonus "[... Exclusive Effect]" added to a general effect is not this.
RESTRICTED = re.compile(
    r'^(?:The )?[\w.\' -]+?(?:-faction)? Identities(?::| gain\b)'
    r'|^If there are \d+ or more "[^"]+" Identities')
#: The gift is a liability until it changes: "This E.G.O Gift changes after 6 Encounter wins".
DRAWBACK = re.compile(r'This E\.G\.O Gift changes (?:after|into)')
SIN_WORD = re.compile(r'\b(Wrath|Lust|Sloth|Gluttony|Gloom|Pride|Envy)\b')
TYPE_WORD = re.compile(r'\b(Slash|Pierce|Blunt)\b')

#: Which kinds of effect a description mentions. The vocabulary is the one the damage
#: formula uses (docs/wiki, chapter 9 "How the damage terms relate"), plus what a gift
#: can do besides, in a fight and between fights. A term says the words are there; it
#: does not say when or how much -- conditions and amounts are not modelled. Every gift
#: must show at least one term or system, or the import stops: a description this
#: vocabulary cannot describe at all is a gap in the vocabulary.
TERMS = (
    ('final_power', r'Final Power'),
    ('base_power', r'Base Power'),
    ('clash_power', r'Clash Power'),
    ('coin_power', r'Coin Power'),
    ('power_up', r'\{\{StatusEffect\|(?:Attack Power Up|Power Up|(?:Slash|Pierce|Blunt) Power Up)'),
    ('offense_level', r'Offense Level'),
    ('defense_level', r'Defense Level'),
    ('damage_up', r'[+]\d+% (?:more )?damage|damage by \d+%|\d+% more damage|Damage Up|DMG Up|deals? [+]\d+%'),
    ('damage_taken_down', r'\d+% less damage|less damage|\{\{StatusEffect\|Protection'),
    ('heal', r'\b[Hh]eals?\b|\bHealing\b'),
    ('sp', r'\bSP\b'),
    ('shield', r'\bShield\b'),
    ('haste', r'\bHaste\b'),
    ('stagger', r'\bStagger'),
    ('critical', r'\bCritical\b'),
    ('ego_resource', r'E\.G\.O resource'),
    ('cost', r'\bCost\b'),
    ('revive', r'\breviv|does not drop below 1|not take that damage'),
    ('skill_power', r'Skill Power|\b(?:Slash|Pierce|Blunt) Power by'),
    ('fixed_damage', r'fixed (?:\w+ )*damage|(?:Slash|Pierce|Blunt) Damage equal to'),
    ('resistance', r'[Rr]esistances?\b'),
    ('speed', r'\bSpeed\b'),
    ('max_hp', r'% max HP\b(?! as)|gain [^.]*max HP'),
    ('resonance', r'Resonance|A-Reson'),
    ('extra_action', r'use the Skill one more time'),
    ('levels', r'gain \d+ Levels'),
    ('participants', r'Participant Limit'),
    ('shop', r'\bin a Shop\b|\bShop\b[^.]*Cost|Fusion Probability'),
    ('reward_cards', r'Reward Card'),
    ('material', r'Counts as a Tier \d E\.G\.O Gift'),
    ('drawback', DRAWBACK.pattern),
    # what the closed status table adds; no wording of its own
    ('defense_power', None), ('unbreakable_coin', None), ('ammo', None), ('aggro', None), ('discard', None),
    ('enemy_down', None), ('paralyze', None), ('fragile', None), ('bind', None), ('unique', None),
)


def ask(**query):
    request = urllib.request.Request(API + '?' + urllib.parse.urlencode(dict(query, format='json', formatversion='2')),
                                     headers={'User-Agent': AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch():
    page = ask(action='query', prop='revisions', rvprop='ids|content', rvslots='main', titles=PAGE)['query']['pages'][0]
    rights = ask(action='query', meta='siteinfo', siprop='rightsinfo')['query']['rightsinfo']
    revision = page['revisions'][0]
    return dict(title=page['title'], pageid=page['pageid'], revid=revision['revid'],
                text=revision['slots']['main']['content'], rightsinfo=rights)


def entries(text, repeated=None):
    """``{key: fields}`` for every entry line; any other line of content is an error.

    A field written twice in one entry is not an error: Lua keeps the last one, which is
    what the wiki itself then shows (revision 203751 has ``desc`` twice in "Melted
    Paraffin+"). The same rule is applied and the entry is named in ``repeated``.
    """
    found = {}
    for number, line in enumerate(text.split('\n'), 1):
        bare = line.strip()
        if not bare or bare.startswith('--') or bare in ('return {', '}'):
            continue
        entry = ENTRY.match(line)
        if entry is None:
            raise ValueError('Line %d is not a gift entry: %r' % (number, bare[:80]))
        key, body, fields, at = entry[1], entry[2].strip(), {}, 0
        while at < len(body):
            field = FIELD.match(body, at)
            if field is None:
                raise ValueError('Line %d: unreadable field at %r' % (number, body[at:at + 40]))
            if field[1] in fields and repeated is not None:
                repeated.append('%s.%s' % (key, field[1]))
            fields[field[1]] = int(field[3]) if field[3] is not None else field[2].replace('\\"', '"').replace("\\'", "'")
            at = field.end()
            while at < len(body) and body[at] in ' \t':
                at += 1
        if key in found:
            raise ValueError('Line %d: entry %r twice' % (number, key))
        found[key] = fields
    return found


def statuses(description):
    """The status names a description uses; one this module cannot classify is an error."""
    found = sorted(set(STATUS.findall(description)))
    unknown = [name for name in found if name not in STATUS_KIND and name not in UNIQUE]
    if unknown:
        raise ValueError('Status not classified in STATUS_KIND or UNIQUE: %r' % unknown)
    return found


def terms(description):
    kinds = {STATUS_KIND.get(name, 'unique') for name in statuses(description)}
    return [term for term, pattern in TERMS
            if term in kinds or (pattern is not None and re.search(pattern, description))]


def systems(description):
    """The systems a description touches, through the status itself or one that lives inside it."""
    kinds = {STATUS_KIND.get(name) for name in statuses(description)}
    return [system for system in SYSTEMS if system in kinds]


def facts(text):
    """One row per obtainable Mirror Dungeon gift: the base entries that carry a tier."""
    repeated = []
    table = entries(text, repeated)
    rows, left_out = [], dict(without_tier=0, legacy=0, enhanced=0, story_dungeon_twin=0, repeated_fields=repeated)
    for key, fields in table.items():
        if key.endswith('+'):
            # "Name+" and "Name++" are the same gift enhanced; they are counted on the base row.
            left_out['enhanced'] += 1
            if key.rstrip('+') not in table:
                raise ValueError('Enhanced entry %r has no base entry' % key)
            continue
        if LEGACY.search(key):
            left_out['legacy'] += 1
            continue
        if key + DISAMBIGUATOR in table:
            # The same name in a story dungeon: the Mirror Dungeon gift is the suffixed
            # entry, and the two differ (revision 203751: "Sublimity" is filed under
            # Bleed in the story dungeon and under Slash in the Mirror Dungeon).
            left_out['story_dungeon_twin'] += 1
            continue
        if 'tier' not in fields:
            left_out['without_tier'] += 1    # story-dungeon gifts: no tier, no shop price
            continue
        for needed in ('name', 'desc', 'sin', 'cost'):
            if needed not in fields:
                raise ValueError('Gift %r has no %s' % (key, needed))
        if fields['tier'] not in TIERS or fields['sin'] not in SINS or not isinstance(fields['cost'], int):
            raise ValueError('Gift %r: unknown tier, affinity or cost' % key)
        keyword = fields.get('category')
        if keyword is not None and keyword not in KEYWORDS:
            raise ValueError('Gift %r: unknown keyword %r' % (key, keyword))
        name = key[:-len(DISAMBIGUATOR)] if key.endswith(DISAMBIGUATOR) else key
        steps = sum(1 for plus in ('+', '++') if key + plus in table)
        description = fields['desc']
        row = dict(name=name, tier=TIERS[fields['tier']], cost=fields['cost'], keyword=keyword,
                   sin=fields['sin'], enhancements=steps, systems=systems(description), terms=terms(description),
                   sins=[sin.lower() for sin in dict.fromkeys(SIN_WORD.findall(description))],
                   damage_types=list(dict.fromkeys(TYPE_WORD.findall(description))),
                   restricted=bool(RESTRICTED.search(description)))
        if not row['terms'] and not row['systems']:
            raise ValueError('Gift %r: no term of the vocabulary describes it' % key)
        rows.append(row)
    names = [row['name'] for row in rows]
    if len(set(names)) != len(names):
        raise ValueError('Two gifts print the same name: %r' % sorted({n for n in names if names.count(n) > 1}))
    if len(rows) < 100:
        raise ValueError('Only %d gifts: the table is not the one this reads' % len(rows))
    return sorted(rows, key=lambda row: row['name']), left_out


def build(saved, retrieved):
    rows, left_out = facts(saved['text'])
    rights = saved.get('rightsinfo') or {}
    return dict(
        version=2,
        source=dict(
            url='https://limbuscompany.wiki.gg/wiki/' + urllib.parse.quote(PAGE.replace(' ', '_')),
            page=saved['title'], pageid=saved['pageid'], revid=saved['revid'], retrieved_utc=retrieved,
            text_sha256=hashlib.sha256(saved['text'].encode('utf-8')).hexdigest(),
            license=rights.get('text'), license_url=rights.get('url'),
            scope=('gift name, tier, shop cost, keyword, affinity, number of enhancements, and which kinds of '
                   'effect, systems, affinities and damage types the description mentions and whether it is '
                   'written for named Identities; no description text and no artwork'),
            name_rule='the wiki key suffix %r is dropped: the game prints the name without it' % DISAMBIGUATOR,
            left_out=left_out,
            terms=[term for term, _ in TERMS],
            statuses_classified=len(STATUS_KIND) + len(UNIQUE)),
        gifts=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fetch', action='store_true', help='ask the wiki API now')
    source.add_argument('--saved', type=Path, help='a response saved by --save-response')
    parser.add_argument('--save-response', type=Path, help='with --fetch: keep the raw response here (outside the repository)')
    parser.add_argument('--target', type=Path, default=TARGET)
    parser.add_argument('--retrieved', help='ISO time the saved response was fetched (with --saved)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.fetch:
        saved = fetch()
        if args.save_response:
            args.save_response.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
    else:
        saved = json.loads(args.saved.read_text(encoding='utf-8'))
    retrieved = args.retrieved or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    data = build(saved, retrieved)
    previous = json.loads(args.target.read_text(encoding='utf-8'))['gifts'] if args.target.exists() else []
    key = lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False)
    before, after = {key(row) for row in previous}, {key(row) for row in data['gifts']}
    if not args.dry_run:
        lines = ['{', ' "version": 2,', ' "source": ' + json.dumps(data['source'], ensure_ascii=False) + ',', ' "gifts": [']
        lines += ['  ' + json.dumps(row, ensure_ascii=False) + (',' if index + 1 < len(data['gifts']) else '')
                  for index, row in enumerate(data['gifts'])]
        args.target.write_text('\n'.join(lines + [' ]', '}']) + '\n', encoding='utf-8')
    tiers, described = {}, 0
    for row in data['gifts']:
        tiers[str(row['tier'])] = tiers.get(str(row['tier']), 0) + 1
        described += bool(row['terms'] or row['systems'])
    print(json.dumps(dict(revid=data['source']['revid'], gifts=len(data['gifts']), tiers=tiers,
                          with_a_recognised_term=described, left_out=data['source']['left_out'],
                          changed=len(after - before), removed=len(before - after)), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
