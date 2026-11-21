"""Answered map-view read obligations, never navigation success or input grants."""
from datetime import datetime
import json
from pathlib import Path
import re

from .native_evidence import bound_frame,journal_scope
from .map_vision import map_header
from .vision import Text
from . import workspace


def diagnostic_index(runtimes):
    """Keep two latest answered viewport pairs per scope and every unanswered one.

    A fresh same-floor/pack MAP answers the diagnostic read after an allowlisted
    zoom/drag intent. It does not prove that input was sent or moved the view.
    Unknown inputs/pages break the chain. Original records and external business,
    model and review references retain their stronger storage ownership.
    """
    result={};groups={};cache={};unanswered={};reads={}
    def stamp(row):
        try:
            value=datetime.fromisoformat(row['utc'])
            return value if value.tzinfo else None
        except (ValueError,KeyError,TypeError):return None
    def native(run,row):
        name=Path(str(row.get('frame') or '')).stem
        if not re.fullmatch(r'frame-\d+',name):return None
        path=run/(name+'.json')
        if path not in cache:
            try:
                _,data=bound_frame(path)
                header=map_header([Text(t['text'],tuple(t['box']),t['score']) for t in data['ocr']],data['size'])
                cache[path]=(name,data,header) if (data.get('scene')=='MAP' and data.get('frame')==name
                    and header and header.floor in range(1,6) and header.pack and stamp(data)) else None
            except (OSError,ValueError,KeyError,TypeError):cache[path]=None
        hit=cache[path]
        return hit if hit and row.get('image_sha256',hit[1]['image_sha256'])==hit[1]['image_sha256'] else None
    for base in runtimes:
        if not base.is_dir() or workspace._linked(base):continue
        for log in base.glob('*/events.jsonl'):
            if workspace._linked(log) or workspace._linked(log.parent):continue
            try:rows=[json.loads(s) for s in log.read_text(encoding='utf8').splitlines()]
            except (OSError,ValueError):continue
            if any(not isinstance(r,dict) for r in rows):continue
            scope=journal_scope(rows)
            if scope is None:continue
            pending=None;run=log.parent
            for row in rows:
                event=str(row.get('event') or '')
                if event in ('map_observed','battle_observed') and row.get('scene')=='MAP':
                    actual=native(run,row);observed=stamp(row)
                    if actual and observed and stamp(actual[1])<=observed:
                        key=(scope,actual[2].floor,actual[2].pack)
                        reads.setdefault(key,{})[(run,actual[0])]=stamp(actual[1])
                if event=='map_view_intent':
                    before=native(run,row);at=stamp(row)
                    pending=(before,at) if (row.get('kind') in ('zoom','drag') and before and at
                        and stamp(before[1])<=at) else None
                    if pending:unanswered.setdefault(run,set()).add(before[0])
                elif event.endswith('_intent') or row.get('input_sent') is True:
                    pending=None
                elif event in ('map_observed','battle_observed') and pending:
                    before,at=pending;pending=None;after=native(run,row);observed=stamp(row)
                    if (row.get('scene')=='MAP' and after and observed and before[0]!=after[0]
                            and at<stamp(after[1])<=observed
                            and (before[2].floor,before[2].pack)==(after[2].floor,after[2].pack)):
                        groups.setdefault(scope,[]).append((at,run,before[0],after[0],
                            (scope,after[2].floor,after[2].pack),stamp(after[1])))
                        unanswered[run].discard(before[0])
    for pairs in groups.values():
        pairs.sort(key=lambda p:p[0]);required={}
        for _,run,a,b,key,at in pairs[-2:]:
            later=sorted(((time,p,name) for (p,name),time in reads.get(key,{}).items() if time>at),key=lambda v:v[0])
            if len(later)>=2:
                projection=result.setdefault(run,dict(superseded=set(),required=set(),bootstrap=set(),causal_pairs=set()))
                projection['superseded'].update((a,b))
                for _,p,name in later[-2:]:required.setdefault(p,set()).add(name)
            else:required.setdefault(run,set()).update((a,b))
        for _,run,a,b,_,_ in pairs[:-2]:
            projection=result.setdefault(run,dict(superseded=set(),required=set(),bootstrap=set(),causal_pairs=set()))
            projection['superseded'].update({a,b}-required.get(run,set()))
        for run,names in required.items():
            projection=result.setdefault(run,dict(superseded=set(),required=set(),bootstrap=set(),causal_pairs=set()))
            projection['required'].update(names);projection['superseded'].difference_update(names)
    for run,names in unanswered.items():
        projection=result.setdefault(run,dict(superseded=set(),required=set(),bootstrap=set(),causal_pairs=set()))
        projection['required'].update(names);projection['superseded'].difference_update(names)
    return result
