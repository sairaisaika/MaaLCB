"""Write assets/resource/base/gift-fusion-recipes.json from the wiki's fusion recipe table.

Names and relations only: which E.G.O Gifts fuse into which gift in a Mirror Dungeon
shop. No artwork, no effect text. The source is the page "List of E.G.O Gifts/Fusion"
on limbuscompany.wiki.gg (the page "E.G.O Gift Fusion Recipes" redirects there); the
wiki states its own licence, which is recorded next to the page's revision id.

The table is read strictly. A keyword or theme cell says how many rows it covers
(``rowspan``), and a row that no such cell covers stops the import, as does a row
without exactly one result. Guessing the group "until the next heading" assigned 16
rows to a group of 13 when this was first tried by hand.

    python tools/import_wiki_fusion_recipes.py --fetch           # ask the wiki API
    python tools/import_wiki_fusion_recipes.py --parsed FILE     # replay a saved response
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
PAGE = 'List of E.G.O Gifts/Fusion'
AGENT = 'wiki-data-check/1.0'
TARGET = ROOT / 'assets/resource/base/gift-fusion-recipes.json'
#: The seven status systems a team can be built around; every other group is a theme.
SYSTEMS = ('Burn', 'Bleed', 'Tremor', 'Rupture', 'Sinking', 'Poise', 'Charge')
#: The wiki appends this to a page title that would collide with another page. The
#: game prints the name without it.
DISAMBIGUATOR = ' (MD)'

GIFT = re.compile(r'\{\{GiftTT\|([^|}]+)')
GROUP = re.compile(r"rowspan=\"(\d+)\".*'''([^']+)'''")
PLACEHOLDER = re.compile(r'\{\{ItemHeader\|def\|([^}*]+)\*?\}\}')


def ask(**query):
    request = urllib.request.Request(API + '?' + urllib.parse.urlencode(dict(query, format='json', formatversion='2')),
                                     headers={'User-Agent': AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch():
    parsed = ask(action='parse', page=PAGE, prop='wikitext|revid')['parse']
    rights = ask(action='query', meta='siteinfo', siprop='rightsinfo')['query']['rightsinfo']
    return dict(parsed, rightsinfo=rights)


def name(text):
    text = text.strip()
    return text[:-len(DISAMBIGUATOR)] if text.endswith(DISAMBIGUATOR) else text


def tables(wikitext):
    """Yield ``(heading, rows)`` per table; a row is its list of cell lines."""
    heading = None
    rows = None
    for line in wikitext.split('\n'):
        title = re.fullmatch(r'==+\s*(.*?)\s*==+', line.strip())
        if title:
            heading = title[1]
        elif line.startswith('{|'):
            rows = [[]]
        elif line.startswith('|}') and rows is not None:
            yield heading, [row for row in rows if row]
            rows = None
        elif rows is not None and line.startswith('|-'):
            rows.append([])
        elif rows is not None and line[:1] in '|!':
            rows[-1].append(line)


def wildcard_names(wikitext, label):
    """The gifts a placeholder cell stands for, from the note under its table."""
    note = re.search(r'"%ss?" used in this recipe can be any of[^\n]*' % re.escape(label), wikitext)
    if note is None:
        raise ValueError('The wiki no longer says which gifts %r stands for' % label)
    names = [name(found) for found in GIFT.findall(note[0])]
    if len(names) < 2 or len(set(names)) != len(names):
        raise ValueError('Unreadable list of gifts for %r' % label)
    return names


def recipes(wikitext):
    found = []
    for heading, rows in tables(wikitext):
        section, group, left = 'keyword', None, 0
        for cells in rows:
            if all(cell.startswith('!') for cell in cells):
                # A header row. "Themed Gifts Fusion" starts the theme half of the table.
                if any('Themed' in cell for cell in cells):
                    section = 'theme'
                continue
            head = GROUP.search(cells[0])
            if head:
                if left:
                    raise ValueError('Group %r ended %d rows early' % (group, left))
                left, group = int(head[1]), head[2].strip()
                cells = cells[1:]
            if heading and 'Super Shop' in heading:
                section, group, left = 'super_shop', None, 1
            if left < 1:
                raise ValueError('A recipe row belongs to no group: %r' % cells)
            left -= 1
            results = [cell for cell in cells if 'border-left' in cell]
            if len(results) != 1 or cells[-1] is not results[0] or len(GIFT.findall(results[0])) != 1:
                raise ValueError('A recipe row needs exactly one result, in its last cell: %r' % cells)
            fixed, any_of = [], {}
            for cell in cells[:-1]:
                gifts = GIFT.findall(cell)
                stand_in = PLACEHOLDER.search(cell)
                if len(gifts) == 1:
                    fixed.append(name(gifts[0]))
                elif not gifts and stand_in:
                    any_of[stand_in[1].strip()] = any_of.get(stand_in[1].strip(), 0) + 1
                elif gifts or cell.split('|')[-1].strip():
                    raise ValueError('Unreadable ingredient cell: %r' % cell)
            row = dict(kind=section, group=group, ingredients=fixed, result=name(GIFT.findall(results[0])[0]))
            if section == 'keyword' and group not in SYSTEMS:
                raise ValueError('Unknown keyword group %r' % group)
            if any_of:
                row['any_of'] = [dict(label=label, count=count, names=wildcard_names(wikitext, label))
                                 for label, count in any_of.items()]
            if len(fixed) + sum(any_of.values()) < 2 or len(set(fixed)) != len(fixed) or row['result'] in fixed:
                raise ValueError('Implausible recipe: %r' % row)
            found.append(row)
        if left:
            raise ValueError('Group %r ended %d rows early' % (group, left))
    keys = [(tuple(sorted(row['ingredients'])), json.dumps(row.get('any_of'), sort_keys=True)) for row in found]
    if len(set(keys)) != len(keys):
        raise ValueError('Two recipes use the same gifts')
    return found


def build(parsed, retrieved):
    wikitext = parsed['wikitext']
    rows = recipes(wikitext)
    rights = parsed.get('rightsinfo') or {}
    return dict(
        version=1,
        source=dict(
            url='https://limbuscompany.wiki.gg/wiki/' + urllib.parse.quote(PAGE.replace(' ', '_')),
            page=parsed['title'], pageid=parsed['pageid'], revid=parsed['revid'], retrieved_utc=retrieved,
            wikitext_sha256=hashlib.sha256(wikitext.encode('utf-8')).hexdigest(),
            license=rights.get('text'), license_url=rights.get('url'),
            scope='gift names and which gifts fuse into which; no artwork and no effect text',
            name_rule='the wiki page-title suffix %r is dropped: the game prints the name without it' % DISAMBIGUATOR),
        recipes=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fetch', action='store_true', help='ask the wiki API now')
    source.add_argument('--parsed', type=Path, help='a saved action=parse response (with revid; rightsinfo optional)')
    parser.add_argument('--target', type=Path, default=TARGET)
    parser.add_argument('--retrieved', help='ISO time the saved response was fetched (with --parsed)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.fetch:
        parsed = fetch()
    else:
        saved = json.loads(args.parsed.read_text(encoding='utf-8'))
        parsed = dict(saved['parse'], rightsinfo=saved.get('rightsinfo') or saved['parse'].get('rightsinfo'))
    retrieved = args.retrieved or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    data = build(parsed, retrieved)
    previous = json.loads(args.target.read_text(encoding='utf-8'))['recipes'] if args.target.exists() else []
    key = lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False)
    before, after = {key(row) for row in previous}, {key(row) for row in data['recipes']}
    if not args.dry_run:
        args.target.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    groups = {}
    for row in data['recipes']:
        groups[row['group'] or row['kind']] = groups.get(row['group'] or row['kind'], 0) + 1
    print(json.dumps(dict(revid=data['source']['revid'], recipes=len(data['recipes']), groups=groups,
                          added=len(after - before), removed=len(before - after)), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
