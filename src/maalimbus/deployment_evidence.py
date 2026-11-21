"""Verified selection commits for bounded diagnostics; no controller/state writes."""
import hashlib
import json
from pathlib import Path
import re
from .native_evidence import bound_frame as _native  # compatibility for retained audit callers
from .native_evidence import journal_scope


def _proof(path):
    from .team_vision import participants
    from .vision import Text
    proof,record=_native(path)
    if record.get('scene')!='PRE_BATTLE_TEAM':raise ValueError('Selection page differs')
    count=participants([Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']],record['size'])
    if count is None:raise ValueError('Selection counter not independently read')
    return proof,tuple(count)


def _completed_selection(run,rows,scope):
    """A complete count prefix, explicit submit and independent HUD close diagnostics.

    This projects retention only. It never writes a transaction or proves identity,
    survival or victory. The submit before-image and HUD remain input boundaries.
    """
    from .battle_vision import battle_hud
    from .vision import Text
    last=None;commit=None;pending=None;completed=set()
    for row in rows:
        event=row.get('event')
        if event in ('map_observed','battle_observed'):
            name=Path(str(row.get('frame') or '')).stem
            if not re.fullmatch(r'frame-\d+',name):pending=None;continue
            if pending and row.get('scene')=='BATTLE_HUD':
                try:
                    _,record=_native(run/(name+'.json'))
                    if record.get('scene')=='BATTLE_HUD' and battle_hud(
                            [Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']],record['size']) is not None:
                        completed.add((pending['scope'],tuple(pending['order']),pending['after']['json_sha256']))
                except (OSError,ValueError,KeyError,TypeError):pass
                pending=None
            elif row.get('scene') not in ('PRE_BATTLE_TEAM','UNKNOWN','LOADING','BATTLE_WAIT','CONNECTING'):
                pending=None;commit=None
            last=name
        elif event=='deployment_selection_committed':
            try:commit=validate_commit(row['commit'],run)
            except (OSError,ValueError,KeyError,TypeError):commit=None
        elif str(event or '').endswith('_intent') or row.get('input_sent'):
            pending=None
            if (event=='window_intent' and row.get('reason')=='battle_button_submits_the_team'
                    and row.get('page')=='PRE_BATTLE_TEAM' and commit and commit['scope']==scope
                    and commit['count_after'][0]==commit['count_after'][1] and last):
                try:
                    _,count=_proof(run/(last+'.json'))
                    if list(count)==commit['count_after']:pending=commit
                except (OSError,ValueError,KeyError,TypeError):pass
    return completed


def selection_commit(before,after,scope,order,sequence):
    order=list(order);sequence=list(sequence)
    if (not isinstance(scope,str) or not scope or not sequence or not order or len(order)>12
            or any(type(v) is not int or not 1<=v<=12 for v in order)
            or any(type(v) is not int for v in sequence)
            or len(set(order))!=len(order) or sequence!=order[:len(sequence)]):
        raise ValueError('Selection commit scope/order prefix differs')
    before,after=Path(before),Path(after)
    if before.parent.resolve()!=after.parent.resolve() or before==after:
        raise ValueError('Selection commit needs distinct same-recorder frames')
    a,ac=_proof(before);b,bc=_proof(after)
    if (ac[1]!=bc[1] or not 0<=ac[0]<bc[0]<=bc[1]<=12
            or ac[0]+1!=bc[0] or bc[0]!=len(sequence)):
        raise ValueError('Selection counter increment differs')
    return dict(version=1,kind='deployment_selection_commit',scope=scope,order=order,
                sequence=sequence,before=a,after=b,count_before=list(ac),count_after=list(bc),
                identity_order_verified=False,completion='count_increment_only')


def validate_commit(value,directory):
    for role in ('before','after'):
        name=value[role]['record']
        if not isinstance(name,str) or not re.fullmatch(r'frame-\d+\.json',name):
            raise ValueError('Selection record outside recorder')
    actual=selection_commit(Path(directory)/value['before']['record'],
        Path(directory)/value['after']['record'],value['scope'],value['order'],value['sequence'])
    if actual!=value:raise ValueError('Selection commit original proof differs')
    return actual


def startup_order_preview(run,rows):
    """Earlier preflight pixels are diagnostic after a fresh full-order read.

    Same recorder, no intervening input, complete own controls and all twelve
    high-confidence ordinals. This neither proves identity nor submits a team.
    The actor's fresh before-image, all JSON and external references remain.
    """
    from .startup_evidence import preview_records
    from .runner import controls_by_id,REGISTRY
    from .team_vision import participants,assignment_numbers,selected_saved_team
    from .map_vision import pre_battle_team_page
    from .vision import Text
    captures=preview_records(run,rows,'PRE_BATTLE_TEAM')
    if not captures:return None
    try:
        registry=json.loads(REGISTRY.read_text(encoding='utf8'));orders=[]
        for path,record in captures:
            size=record['size']
            records=[Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']]
            if record['scene']!='PRE_BATTLE_TEAM' or pre_battle_team_page(records,size) is None:return None
            if participants(records,size)!=(12,12):return None
            controls=controls_by_id(registry,size)
            numbers=assignment_numbers(records,[controls.get(f'pre_battle.card_{i:02d}') for i in range(1,13)],size,threshold=.9)
            if set(numbers)!=set(range(1,13)):return None
            orders.append((selected_saved_team(records,size),numbers))
        if any(order!=orders[0] for order in orders[1:]):return None
        return dict(preflight=captures[0][0].stem,actor=captures[-1][0].stem)
    except (OSError,ValueError,KeyError,TypeError):return None


def diagnostic_index(runtimes):
    """Project verified count progress across recorder restarts, read-only.

    A recorder is not a game scope. Native page/reset barriers and count rollback
    separate batches. Only intact commits authorize supersession; absent older
    diagnostic images are skipped, never turned into fresh game evidence.
    """
    from datetime import datetime
    from .team_vision import participants
    from .vision import Text
    timeline=[];logs={};first_commits={};input_free=set();completed=set();hud_reads=[];page_boundaries=[]
    for base in runtimes:
        if not base.is_dir():continue
        for path in base.glob('*/events.jsonl'):
            if path.is_symlink() or path.parent.is_symlink():continue
            try:rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
            except (OSError,ValueError):continue
            if any(not isinstance(row,dict) for row in rows):continue
            run=path.parent;logs[run]=rows
            scope=journal_scope(rows)
            completed.update(_completed_selection(run,rows,scope))
            endings=[row for row in rows if row.get('event')=='mirror_loop_stopped']
            intents=any(str(row.get('event','')).endswith('_intent') or row.get('input_sent')
                        or (row.get('event')=='evidence_capacity_admitted' and row.get('kind')!='plan') for row in rows)
            if (endings and endings[-1].get('clicks_sent')==0
                    and endings[-1].get('reason')=='evidence_capacity_unavailable_before_input'
                    and not intents and not any(row.get('stop_page') for row in rows if row.get('event')=='mirror_loop_start')):
                input_free.add(run)
            prefix=True
            for row in rows:
                if not isinstance(row,dict):continue
                if str(row.get('event','')).endswith('_intent') or row.get('input_sent'):prefix=False
                receipt=row.get('event')=='deployment_selection_committed'
                barrier=(row.get('event') in ('map_observed','battle_observed')
                         and row.get('scene') not in (None,'PRE_BATTLE_TEAM','UNKNOWN','LOADING','BATTLE_WAIT','CONNECTING'))
                preview=bool(prefix and scope and row.get('event')=='map_observed'
                    and row.get('scene')=='PRE_BATTLE_TEAM' and row.get('input_sent') is False)
                hud_preview=bool(prefix and scope and row.get('event') in ('map_observed','battle_observed')
                    and row.get('scene')=='BATTLE_HUD' and row.get('input_sent') is not True)
                page_boundary=(row.get('event') in ('map_observed','battle_observed') and row.get('scene') not in (
                        None,'BATTLE_HUD','UNKNOWN','LOADING','BATTLE_WAIT','CONNECTING'))
                if not receipt and not barrier and not preview and not hud_preview and not page_boundary:continue
                try:
                    stamp=datetime.fromisoformat(row['utc'])
                    if stamp.tzinfo is None:continue
                except (KeyError,TypeError,ValueError):continue
                if page_boundary:page_boundaries.append(stamp)
                if hud_preview:
                    from .battle_vision import battle_hud
                    name=Path(str(row.get('frame') or '')).stem
                    if re.fullmatch(r'frame-\d+',name):
                        try:
                            _,record=_native(run/(name+'.json'))
                            hud=(battle_hud([Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']],record['size'])
                                 if record.get('scene')=='BATTLE_HUD' else None)
                            if hud and hud.get('turn') is not None:
                                hud_reads.append((stamp,run,name,scope,str(hud.get('wave')),str(hud['turn'])))
                        except (OSError,ValueError,KeyError,TypeError):pass
                if preview:
                    name=Path(str(row.get('frame') or '')).stem
                    if not re.fullmatch(r'frame-\d+',name):continue
                    try:_,count=_proof(run/(name+'.json'))
                    except (OSError,ValueError,KeyError,TypeError):continue
                    timeline.append((stamp,run,dict(kind='selection_preview',scope=scope,count=list(count),frame=name)))
                elif receipt:
                    first_commits.setdefault(run,row.get('commit'))
                    try:value=validate_commit(row['commit'],run)
                    except (OSError,ValueError,KeyError,TypeError):continue
                    timeline.append((stamp,run,value))
                elif barrier:timeline.append((stamp,run,None))
    groups=[];active={};latest={};previews={}
    for _,run,value in sorted(timeline,key=lambda item:item[0]):
        if value is None:
            groups.extend(active.values());active={};latest={};continue
        if value.get('kind')=='selection_preview':
            checkpoint=latest.get((value['scope'],value['count'][1]))
            if checkpoint and checkpoint['count_after']==value['count']:
                key=(value['scope'],checkpoint['after']['json_sha256'])
                previews.setdefault(key,[]).append((run,value['frame']))
            continue
        key=(value['scope'],tuple(value['order']),value['count_after'][1])
        group=active.setdefault(key,[])
        if group and value['count_after'][0]<=group[-1][1]['count_after'][0]:
            groups.append(group);active[key]=group=[]
        group.append((run,value))
        latest[(value['scope'],value['count_after'][1])]=value
    groups.extend(active.values());result={}
    for group in groups:
        for run,value in group:
            result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set(),previews=set()))['causal_pairs'].add(
                tuple(Path(value[role]['record']).stem for role in ('before','after')))
    for group in groups:
        final=group[-1][1]
        submitted=(final['scope'],tuple(final['order']),final['after']['json_sha256']) in completed
        if not submitted and len({run for run,_ in group})<2:continue
        for run,value in (group if submitted else group[:-2]):
            row=result[run]
            row['superseded'].update(Path(value[role]['record']).stem for role in ('before','after'))
        for run,valid in group:
            raw=first_commits.get(run);rows=logs[run];last=None;first_input=None;safe=True
            for event in rows:
                name=Path(str(event.get('frame') or '')).stem
                if re.fullmatch(r'frame-\d+',name):last=name
                if event.get('event')=='window_intent':
                    first_input=(last,event);break
                if event.get('input_sent') or str(event.get('event','')).endswith('_intent'):
                    safe=False;break
            if (not safe or not first_input or first_input[1].get('reason')!='team_card_joins_the_next_unpicked_identity'
                    or not isinstance(raw,dict) or raw.get('scope')!=valid['scope'] or raw.get('order')!=valid['order']):continue
            try:
                name=raw['before']['record']
                if not re.fullmatch(r'frame-\d+\.json',name) or Path(name).stem!=first_input[0]:continue
                first=min(run.glob('frame-*.json'));bound=run/name
                if first==bound:continue  # first actual input proof is not a bootstrap duplicate
                preview,pc=_proof(first);body=bound.read_bytes();record=json.loads(body)
                bc=participants([Text(t['text'],tuple(t['box']),t['score']) for t in record['ocr']],record['size'])
                if (record.get('scene')!='PRE_BATTLE_TEAM' or bc is None or tuple(bc)!=pc
                        or list(pc)!=raw['count_before']
                        or hashlib.sha256(body).hexdigest()!=raw['before']['json_sha256']
                        or record.get('image_sha256')!=raw['before']['png_sha256']):continue
                result[run]['bootstrap'].add(first.stem)
            except (OSError,ValueError,KeyError,TypeError):continue
    for items in previews.values():
        if len({run for run,_ in items})<2:continue
        for run,name in items[:-2]:
            if run in input_free:
                result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set(),previews=set()))['previews'].add(name)
    hud_groups={}
    boundaries=sorted(page_boundaries)
    from bisect import bisect_right
    for stamp,run,name,scope,wave,turn in sorted(hud_reads):
        # Named-page visits separate even identical turn numbers in different fights.
        phase=bisect_right(boundaries,stamp)
        hud_groups.setdefault((scope,phase,wave,turn),[]).append((run,name))
    for items in hud_groups.values():
        if len({run for run,_ in items})<2:continue
        for run,name in items[:-2]:
            if run in input_free:
                result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set(),previews=set()))['previews'].add(name)
    for run,rows in logs.items():
        preview=startup_order_preview(run,rows)
        if preview:
            projection=result.setdefault(run,dict(superseded=set(),bootstrap=set(),causal_pairs=set(),previews=set()))
            projection['bootstrap'].add(preview['preflight'])
            projection.setdefault('startup_previews',set()).add(preview['preflight'])
            projection.setdefault('required',set()).add(preview['actor'])
    return result
