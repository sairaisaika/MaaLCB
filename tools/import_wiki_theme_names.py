"""Add the theme pack names listed on limbuscompany.wiki.gg to theme-catalog.json.

Names only: this tool never downloads card artwork (that is a local asset, see
tools/import_wiki_theme_art.py). It reads the MediaWiki category that holds one page
per floor theme pack, strips the " Theme Pack" suffix, and appends every name the
catalog cannot already identify. A wiki spelling of a pack the catalog already holds
(``Abnormal Seismic Zone`` for ``Abnormal Seismi Zone``) is left out, because
``ThemeCatalog.identity`` reads it as that pack already; existing names, weights and
aliases are never changed. Names that the catalog's own near-duplicate rule would
fold into another new name are reported, not added.

    python tools/import_wiki_theme_names.py --fetch            # query the wiki API
    python tools/import_wiki_theme_names.py --members FILE     # replay a saved response
"""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from maalimbus.theme_vision import _shared_prefix_words, normalized  # noqa: E402

API = 'https://limbuscompany.wiki.gg/api.php'
CATEGORY = 'Category:Floor Theme Pack Pages'
SUFFIX = ' Theme Pack'
AGENT = 'MaaLimbus-theme-catalog/1.0'


def fetch_members():
    titles, token = [], None
    while True:
        query = dict(action='query', list='categorymembers', cmtitle=CATEGORY, cmlimit='500',
                     cmnamespace='0', format='json')
        if token:
            query['cmcontinue'] = token
        request = urllib.request.Request(API + '?' + urllib.parse.urlencode(query), headers={'User-Agent': AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        titles += [row['title'] for row in data['query']['categorymembers']]
        token = (data.get('continue') or {}).get('cmcontinue')
        if not token:
            return titles


def pack_names(titles):
    return sorted({title[:-len(SUFFIX)].strip() for title in titles if title.endswith(SUFFIX)})


def close(a, b):
    """The catalog's own near-duplicate rule (``ThemeCatalog._merge_near_duplicates``)."""
    x, y = normalized(a), normalized(b)
    ratio = difflib.SequenceMatcher(None, x, y).ratio()
    return ratio >= .93 or (ratio >= .85 and _shared_prefix_words(x, y) >= 4)


def merge(catalog, names):
    existing = [entry['name'] for entry in catalog['names']]
    added, covered, folded = [], {}, {}
    for name in names:
        known = next((old for old in existing if close(name, old)), None)
        if known is not None:
            covered[name] = known
            continue
        sibling = next((new for new in added if close(name, new)), None)
        if sibling is not None:
            folded[name] = sibling
            continue
        added.append(name)
    return added, covered, folded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fetch', action='store_true', help='query the wiki API now')
    source.add_argument('--members', type=Path, help='a saved categorymembers JSON response')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'assets/resource/base/theme-catalog.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.fetch:
        titles = fetch_members()
    else:
        data = json.loads(args.members.read_text(encoding='utf-8'))
        titles = [row['title'] for row in data['query']['categorymembers']]
    names = pack_names(titles)
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    previous = {entry['name'] for entry in catalog['names'] if entry.get('source') == 'wiki'}
    catalog['names'] = [entry for entry in catalog['names'] if entry.get('source') != 'wiki']
    added, covered, folded = merge(catalog, names)
    catalog['names'] += [dict(name=name, reference_weight=10, source='wiki') for name in added]
    catalog['wiki_names'] = dict(
        url='https://limbuscompany.wiki.gg/wiki/' + CATEGORY.replace(' ', '_'), category=CATEGORY,
        retrieved_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        titles_sha256=hashlib.sha256('\n'.join(names).encode('utf-8')).hexdigest(),
        listed=len(names), added=len(added), covered_by_existing=len(covered), folded=folded)
    report = dict(listed=len(names), added=added, covered=covered, folded=folded,
                  removed_since_last=sorted(previous - set(added)))
    if not args.dry_run:
        args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
