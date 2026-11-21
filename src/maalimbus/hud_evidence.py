"""Scope-owned windows of answered, nonfinancial HUD diagnostics; read-only."""
from bisect import bisect_right
from datetime import datetime
import json
from pathlib import Path
import re

from . import workspace
from .native_evidence import bound_frame as _native
from .native_evidence import journal_scope
from .battle_vision import battle_hud
from .vision import Text

ORDINARY_HUD_REASONS=frozenset((
    'win_rate_is_the_proven_auto_assign_control','damage_is_the_proven_auto_assign_control',
    'start_button_submits_the_assigned_turn','the_battles_speed_toggle_is_enabled_once_per_battle'))
OBSERVATIONS=frozenset(('map_observed','battle_observed'))
SAME_VISIT=frozenset(('BATTLE_HUD','BATTLE_PLANNING','UNKNOWN','LOADING','BATTLE_WAIT','CONNECTING'))


def diagnostic_index(runtimes):
    """Recorder restarts do not create a new battle or another permanent tail.

    A new hash-bound native HUD answers a read obligation; an independently
    verified native battle exit closes its diagnostic visit. Neither publishes
    an action effect, assignment, win, resource grant or learning approval.
    Unknown inputs and every independent reference remain stronger protection.
    """
    runs=[];boundaries=[];cache={}
    def stamp(row):
        try:
            t=datetime.fromisoformat(row['utc'])
            return t if t.tzinfo else None
        except (KeyError,ValueError,TypeError):return None
    def bound(run,row):
        name=Path(str(row.get('frame') or '')).stem
        if not re.fullmatch(r'frame-\d+',name):return None
        path=run/(name+'.json')
        if path not in cache:
            try:
                _,data=_native(path)
                cache[path]=(name,data) if Path(str(data.get('frame') or '')).stem==name else None
            except (OSError,ValueError,KeyError,TypeError):cache[path]=None
        hit=cache[path]
        if hit and row.get('image_sha256',hit[1]['image_sha256'])!=hit[1]['image_sha256']:return None
        return hit
    def hud(data):
        try:return battle_hud([Text(t['text'],tuple(t['box']),t['score']) for t in data['ocr']],data['size'])
        except (ValueError,KeyError,TypeError):return None
    def native(run,row):
        hit=bound(run,row)
        return hit if hit and hit[1].get('scene')=='BATTLE_HUD' and hud(hit[1]) else None
    def known_exit(actual):
        from .map_vision import map_header
        from .vision import find
        try:
            if not actual:return None
            if actual[1].get('scene')=='BATTLE_RESULT':
                return len(find([Text(t['text'],tuple(t['box']),t['score']) for t in actual[1]['ocr']],
                                r'^VICTORY$',(.33,.36,.68,.64),actual[1]['size'],.9))==1
            if actual[1].get('scene')!='MAP':return None
            header=map_header([Text(t['text'],tuple(t['box']),t['score']) for t in actual[1]['ocr']],actual[1]['size'])
            return header if header and header.floor in range(1,6) and header.pack else None
        except (KeyError,TypeError,ValueError):return None
    for base in runtimes:
        if not base.is_dir() or workspace._linked(base):continue
        for log in base.glob('*/events.jsonl'):
            if workspace._linked(log) or workspace._linked(log.parent):continue
            try:rows=[json.loads(line) for line in log.read_text(encoding='utf8').splitlines()]
            except (OSError,ValueError):continue
            if any(not isinstance(row,dict) or not isinstance(row.get('event'),str)
                   or (row.get('scene') is not None and not isinstance(row['scene'],str)) for row in rows):continue
            # A foreign/legacy recorder can still prove a different page visit;
            # missing scope never permits us to bridge that boundary.
            boundaries.extend(stamp(r) for r in rows if r.get('event') in OBSERVATIONS
                and r.get('scene') and r['scene'] not in SAME_VISIT and stamp(r) is not None)
            scope=journal_scope(rows)
            if scope is None:continue
            runs.append((log.parent,rows,scope))
    boundaries.sort();groups={};result={};witnesses={};prefix_candidates=[];checkpoints=[];exits=[]
    for run,rows,scope in runs:
        from .startup_evidence import preview_records
        captures=preview_records(run,rows,'BATTLE_HUD')
        if captures:
            readings=[hud(record) for _,record in captures]
            from .battle_vision import auto_assign_buttons
            signature=lambda h:(h.get('wave'),h.get('turn'))
            if (all(h and h.get('turn') is not None for h in readings)
                    and all(signature(h)==signature(readings[0]) for h in readings)
                    and all(auto_assign_buttons([Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']],record['size'],positional=False)
                            for _,record in captures)):
                projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))
                previews={path.stem for path,_ in captures[:-1]}
                projection['bootstrap'].update(previews)
                projection.setdefault('startup_previews',set()).update(previews)
                projection.setdefault('required',set()).add(captures[-1][0].stem)
        last=None;first=None;pending=None;first_intent=True;safe=True;bootstrap=None;prefix=[]
        submission=None;uncertainty_first={};reads=[];input_frames=set()
        for row in rows:
            event=row.get('event')
            if event in OBSERVATIONS:
                last=row
                if first is None:first=row
                if stamp(row) and row.get('scene') in ('UNKNOWN','LOADING','BATTLE_PLANNING'):
                    reads.append((bisect_right(boundaries,stamp(row)),row))
                    if pending:pending['intermediate'].append(row)
                if stamp(row) and row.get('scene') in ('UNKNOWN','LOADING'):
                    phase=bisect_right(boundaries,stamp(row))
                    uncertainty_first.setdefault((phase,row['scene']),Path(str(row.get('frame') or '')).stem)
                    if submission:submission['intermediate'].append(row)
                if row.get('scene')=='BATTLE_HUD' and stamp(row):
                    actual=native(run,row)
                    if actual:
                        key=(scope,bisect_right(boundaries,stamp(row)))
                        witnesses.setdefault(key,[]).append((stamp(row),run,actual[0]))
                        if safe:prefix.append((key,stamp(row),actual[0]))
                        if submission and key==(scope,submission['phase']) and stamp(row)>submission['stamp']:
                            a=native(run,submission['before']);start_hud=hud(a[1]) if a else None;end_hud=hud(actual[1])
                            start_turn=(start_hud or {}).get('turn');end_turn=(end_hud or {}).get('turn')
                            if (start_turn and end_turn and str(start_turn).isdigit() and str(end_turn).isdigit()
                                    and int(end_turn)==int(start_turn)+1
                                    and ((start_hud or {}).get('wave') is None or end_hud.get('wave') is None
                                         or start_hud['wave']==end_hud['wave'])):
                                item=dict(run=run,before=a[0],after=actual[0],stamp=submission['stamp'],key=key)
                                checkpoints.append(item)
                                projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))
                                projection['causal_pairs'].add((a[0],actual[0]))
                                projection.setdefault('turn_answers',{})[a[0]]=actual[0]
                                for middle in submission['intermediate']:
                                    raw=bound(run,middle)
                                    if (raw and raw[1].get('scene')==middle.get('scene')
                                            and raw[0]!=uncertainty_first.get((submission['phase'],middle['scene']))):
                                        projection['superseded'].add(raw[0])
                                submission=None
                if submission and row.get('scene') in ('MAP','BATTLE_RESULT') and stamp(row):
                    actual=bound(run,row);a=native(run,submission['before'])
                    captured=stamp(actual[1]) if actual else None
                    if (a and known_exit(actual) and captured
                            and submission['stamp']<captured<=stamp(row)):
                        key=(scope,submission['phase']);projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))
                        projection['causal_pairs'].add((a[0],actual[0]))
                        projection.setdefault('turn_answers',{})[a[0]]=actual[0]
                        exits.append(dict(run=run,before=a[0],after=actual[0],stamp=stamp(row),key=key,scope=scope))
                        for phase,middle in reads:
                            name=Path(str(middle.get('frame') or '')).stem
                            if phase!=submission['phase'] or name in input_frames:continue
                            raw=bound(run,middle)
                            if (raw and raw[1].get('scene')==middle.get('scene')
                                    and name!=uncertainty_first.get((phase,middle['scene']))):
                                projection['superseded'].add(name)
                if submission and row.get('scene') and row['scene'] not in SAME_VISIT:submission=None
                if pending and row.get('scene')=='BATTLE_HUD' and stamp(row):
                    a=native(run,pending['before']);b=native(run,row)
                    if (a and b and a[0]!=b[0] and stamp(row)>pending['stamp']
                            and bisect_right(boundaries,stamp(row))==pending['phase']):
                        item=dict(run=run,before=a[0],after=b[0],stamp=pending['stamp'])
                        key=(scope,pending['phase']);groups.setdefault(key,[]).append(item)
                        projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))
                        middle=[]
                        for read in pending['intermediate']:
                            hit=bound(run,read)
                            if hit and hit[1].get('scene')==read.get('scene'):middle.append(hit[0])
                        item['middle']=middle
                        projection['causal_pairs'].add(tuple([a[0],b[0]]+middle))
                        if bootstrap:projection['bootstrap'].add(bootstrap)
                    pending=None
                elif pending and row.get('scene') and row['scene'] not in SAME_VISIT:pending=None
            if str(event or '').endswith('_intent'):
                if last:input_frames.add(Path(str(last.get('frame') or '')).stem)
                pending=None;submission=None;t=stamp(row);box=row.get('target');point=row.get('point');delay=row.get('delay_ms')
                known=(event=='window_intent' and row.get('page')=='BATTLE_HUD'
                    and isinstance(row.get('reason'),str) and row['reason'] in ORDINARY_HUD_REASONS
                    and last and t and stamp(last) and stamp(last)<=t
                    and isinstance(box,list) and len(box)==4 and all(type(v) is int for v in box) and min(box[2:])>0
                    and isinstance(point,list) and len(point)==2 and all(type(v) in (int,float) for v in point)
                    and box[0]<=point[0]<box[0]+box[2] and box[1]<=point[1]<box[1]+box[3]
                    and type(delay) in (int,float) and 350<=delay<=750)
                if known and first_intent and safe and last.get('scene')=='BATTLE_HUD':
                    before_name=Path(str(last.get('frame') or '')).stem
                    for key,at,name in prefix:
                        if name!=before_name:prefix_candidates.append((key,at,run,name))
                if known and native(run,last):
                    pending=dict(before=last,stamp=t,phase=bisect_right(boundaries,t),intermediate=[])
                    if row['reason']=='start_button_submits_the_assigned_turn':
                        submission=dict(pending,intermediate=[],point=list(point))
                    if first_intent and safe and first and stamp(first):
                        a=native(run,first);b=native(run,last)
                        if (a and b and a[0]!=b[0]
                                and bisect_right(boundaries,stamp(first))==pending['phase']):bootstrap=a[0]
                first_intent=False;safe=False
            elif row.get('input_sent'):
                if last:input_frames.add(Path(str(last.get('frame') or '')).stem)
                safe=False;pending=None;submission=None
        # A still-pending, independently anchored START may produce many
        # UNKNOWN animation reads. Sample diagnostics without deciding what the
        # page means: keep the original before-image, first of each uncertainty
        # scene, latest two and every externally referenced review image.
        if submission and last and last.get('scene') in ('UNKNOWN','LOADING'):
            a=native(run,submission['before']);start_hud=hud(a[1]) if a else None
            if (a and start_hud and start_hud.get('turn') is not None
                    and stamp(a[1]) and stamp(a[1])<=submission['stamp']):
                import cv2,numpy as np,hashlib
                from .battle_vision import start_button,auto_assign_buttons
                picture=run/(a[0]+'.png');pixels=picture.read_bytes()
                records=[Text(t['text'],tuple(t['box']),t['score']) for t in a[1]['ocr']]
                buttons=auto_assign_buttons(records,a[1]['size'],positional=False)
                box=(start_button(records,a[1]['size'],cv2.imdecode(np.frombuffer(pixels,np.uint8),cv2.IMREAD_COLOR))
                     if buttons and hashlib.sha256(pixels).hexdigest()==a[1]['image_sha256'] else None)
                point=submission['point'];valid_start=bool(box and box[0]<=point[0]<box[0]+box[2] and box[1]<=point[1]<box[1]+box[3])
                reads={};firsts={}
                for row in submission['intermediate']:
                    name=Path(str(row.get('frame') or '')).stem;t=stamp(row)
                    if (row.get('scene') in ('UNKNOWN','LOADING') and re.fullmatch(r'frame-\d+',name)
                            and t and t>submission['stamp'] and bisect_right(boundaries,t)==submission['phase']):
                        reads.setdefault(name,row);firsts.setdefault(row['scene'],name)
                keep=set(firsts.values())|set(list(reads)[-2:])
                def valid_read(row,value):
                    return bool(value and value[1].get('scene')==row['scene'] and stamp(value[1])
                                and submission['stamp']<stamp(value[1])<=stamp(row))
                intact=all(valid_read(reads[name],bound(run,reads[name])) for name in keep)
                if valid_start and intact and len(reads)>len(keep):
                    projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))
                    projection.setdefault('required',set()).update(keep|{a[0]})
                    for name,row in reads.items():
                        if name in keep:continue
                        b=bound(run,row)
                        if valid_read(row,b):
                            projection['superseded'].add(name)
                            projection.setdefault('inflight_reads',set()).add(name)
    for items in groups.values():
        items.sort(key=lambda item:item['stamp'])
        for item in items[:-2]:result[item['run']]['superseded'].update([item['before'],item['after']]+item.get('middle',[]))
    for checkpoint in checkpoints:
        for item in groups.get(checkpoint['key'],[]):
            if item['stamp']<checkpoint['stamp']:
                result[item['run']]['superseded'].update([item['before'],item['after']]+item.get('middle',[]))
        for previous in checkpoints:
            if previous['key']==checkpoint['key'] and previous['stamp']<checkpoint['stamp']:
                result[previous['run']]['superseded'].update((previous['before'],previous['after']))
    latest={}
    for checkpoint in checkpoints:
        if checkpoint['key'] not in latest or checkpoint['stamp']>latest[checkpoint['key']]['stamp']:
            latest[checkpoint['key']]=checkpoint
    for key,checkpoint in latest.items():
        projection=result[checkpoint['run']]
        newer=[item for item in groups.get(key,[]) if item['stamp']>checkpoint['stamp']]
        if len(newer)>=2:
            projection['superseded'].update((checkpoint['before'],checkpoint['after']))
        else:
            projection['superseded'].difference_update((checkpoint['before'],checkpoint['after']))
    for end in exits:
        for item in groups.get(end['key'],[]):
            result[item['run']]['superseded'].update([item['before'],item['after']]+item.get('middle',[]))
    by_scope={}
    for end in exits:by_scope.setdefault(end['scope'],[]).append(end)
    for history in by_scope.values():
        history.sort(key=lambda end:end['stamp'])
        for end in history[:-2]:result[end['run']]['superseded'].update((end['before'],end['after']))
        for end in history[-2:]:
            result[end['run']].setdefault('required',set()).update((end['before'],end['after']))
    for key,at,run,name in prefix_candidates:
        # A redundant *pre-input* identity read is not an input's before-image.
        # Later native witnesses can supersede it even after the actual before
        # pair was lawfully retired. Missing pixels never answer a read or
        # create an outcome: every replacement witness is verified here now.
        later={(r,n) for t,r,n in witnesses.get(key,[]) if t>at and (r,n)!=(run,name)}
        if len(later)>=2:
            result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set()))['bootstrap'].add(name)
    return result
