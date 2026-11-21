"""Adapt the project's schema-1 routes to project-wiki's native task protocol.

No game, controller, model, test or maintenance operation is executed. All file
owners are returned; query top-N is never used as a complete impact inventory.
"""
import argparse
import json
from pathlib import Path

from wiki_router import rank,resolve

ROOT=Path(__file__).resolve().parents[1]


def native_context(root,query,files):
    root=Path(root).resolve()
    manifest=json.loads((root/'docs/wiki/routes.json').read_text(encoding='utf8'))
    routes=manifest['routes']
    def page(ref,title):
        name,_,anchor=ref.partition('#')
        return dict(path=name.removeprefix('docs/wiki/'),title=title,anchor=anchor)
    def pages(row):
        return [page(ref,row['id']) for ref in row['docs'] if ref.startswith('docs/wiki/')]
    matched=rank(query,routes)
    chosen=matched[:2];cards=[];details={}
    for row in chosen:
        try:
            current=resolve(root,dict(manifest,routes=[row]))[0]
            details[row['id']]=dict(locations=current['locations'],tests=row.get('tests',[]),
                checks=row.get('checks',[]),boundary=row.get('boundary'))
        except (OSError,ValueError,SyntaxError) as error:
            details[row['id']]=dict(locations=[],warning='Stale route; verify source: '+str(error),
                tests=row.get('tests',[]),checks=row.get('checks',[]),boundary=row.get('boundary'))
        cards.extend(pages(row))
    # Upstream `show --view feature --path` selects one native page key.
    # Two routed sections of one page must remain one expandable feature,
    # with all anchors retained instead of duplicate, ambiguous path keys.
    grouped={}
    for card in cards:
        entry=grouped.setdefault(card['path'],dict(path=card['path'],title=card['title'],sections=[]))
        section=dict(anchor=card['anchor'],route_id=card['title'],**details[card['title']])
        if section not in entry['sections']:entry['sections'].append(section)
    cards=list(grouped.values())
    impact=[]
    for name in files:
        p=Path(name)
        if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or name!=p.as_posix():
            raise ValueError('Project-relative planned files required')
        owners=[]
        for row in routes:
            inputs={r['path'] for r in row.get('sources',[])}
            inputs.update(row.get('tests',[]))
            inputs.update(ref.partition('#')[0] for ref in row['docs'])
            if name in inputs:owners.extend(pages(row))
        # Preserve all distinct section owners, even when they share a page.
        owners=list({(r['path'],r['anchor']):r for r in owners}.values())
        impact.append(dict(file=name,unregistered=not bool(owners),pages=owners))
    return dict(query=query,cards=cards,impact=impact,
        omitted=[dict(path=r['docs'][0].removeprefix('docs/wiki/').partition('#')[0],
                      title=r['id']) for r in matched[2:] if r.get('docs')],
        placementIssues=[],
        workflow=dict(status='project_policy',authority=['AGENTS.md','docs/wiki/zh_cn/8-agent-rules.md'],
            execution='maintenance -> tests -> build -> live, serialized; readonly analysis may continue',
            acceptance='Historical results are feasibility evidence. Frozen login-to-current-Mirror receipt chain is still required.',
            limits='Hook delivery, structural checks and local tests do not certify business completion.'),
        limits='Schema-1 project routes adapted without schema migration. All declared owners returned; indirect undeclared dependencies remain unknown.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query');parser.add_argument('--files',nargs='*',default=[])
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    print(json.dumps(native_context(ROOT,args.query,args.files),ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
