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
#: An earlier version of a gift the wiki keeps for reference. Not obtainable; left out.
LEGACY = ' (Legacy)'
TIERS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'EX': 'EX'}
#: The seven status systems and the three damage types a gift can be filed under.
KEYWORDS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge', 'Slash', 'Pierce', 'Blunt')
SYSTEMS = KEYWORDS[:7]
SINS = ('wrath', 'lust', 'sloth', 'gluttony', 'gloom', 'pride', 'envy')

ENTRY = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*\{(.*)\}\s*,?\s*(?:--.*)?$')
FIELD = re.compile(r'(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|(-?\d+))\s*(?:,|$)')
STATUS = re.compile(r'\{\{StatusEffect\|([^|}]+)')

#: Which kinds of effect a description mentions. The vocabulary is the one the damage
#: formula uses (docs/wiki, chapter 9 "How the damage terms relate"), plus what a gift
#: can do besides. A term says the words are there; it does not say for whom, when, or
#: how much -- conditions are not modelled, so this is material for a later reader and
#: not yet a valuation.
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
    ('revive', r'\breviv'),
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


def terms(description):
    return [term for term, pattern in TERMS if re.search(pattern, description)]


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
        if key.endswith(LEGACY):
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
        mentioned = [system for system in SYSTEMS if system in set(STATUS.findall(description))]
        rows.append(dict(name=name, tier=TIERS[fields['tier']], cost=fields['cost'], keyword=keyword,
                         sin=fields['sin'], enhancements=steps, systems=mentioned, terms=terms(description)))
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
        version=1,
        source=dict(
            url='https://limbuscompany.wiki.gg/wiki/' + urllib.parse.quote(PAGE.replace(' ', '_')),
            page=saved['title'], pageid=saved['pageid'], revid=saved['revid'], retrieved_utc=retrieved,
            text_sha256=hashlib.sha256(saved['text'].encode('utf-8')).hexdigest(),
            license=rights.get('text'), license_url=rights.get('url'),
            scope=('gift name, tier, shop cost, keyword, affinity, number of enhancements, and which kinds of '
                   'effect the description mentions; no description text and no artwork'),
            name_rule='the wiki key suffix %r is dropped: the game prints the name without it' % DISAMBIGUATOR,
            left_out=left_out,
            terms=[term for term, _ in TERMS]),
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
        lines = ['{', ' "version": 1,', ' "source": ' + json.dumps(data['source'], ensure_ascii=False) + ',', ' "gifts": [']
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
