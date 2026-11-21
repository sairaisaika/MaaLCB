"""Input-free startup capture identity; page owners decide semantic equivalence."""
from datetime import datetime
from pathlib import Path
import json
import re
from .native_evidence import bound_frame, journal_scope, observation_frame


LOGIN_WAIT_PAGES = frozenset(('TITLE', 'UNKNOWN', 'LOADING', 'CONNECTING'))


def answered_login_diagnostics(run, rows):
    """Return only redundant, input-free reads of one verified login response."""
    if journal_scope(rows) is None:
        return set()
    def events(name):
        return [(i, row) for i, row in enumerate(rows) if row['event'] == name]

    starts = events('mirror_loop_start')
    sent = events('login_start_sent')
    success = events('login_successor_observed')
    if len(starts) != 1 or len(sent) != 1 or len(success) != 1:
        return set()
    sent_at, dispatch = sent[0]
    end_at, answer = success[0]
    before, after = answer.get('before'), answer.get('after')
    if (not isinstance(before, str) or not isinstance(after, str) or before == after
            or dispatch.get('frame') != before or dispatch.get('input_sent') is not True
            or not sent_at < end_at or answer.get('page') != 'HOME'
            or answer.get('input_sent') is not False):
        return set()
    intents = [(i, row) for i, row in events('window_intent')
               if i < end_at and row.get('reason') == 'resume_login_with_its_own_start_caption']
    if len(intents) != 1:
        return set()
    intent_at, intent = intents[0]
    if (not starts[0][0] < intent_at < sent_at or intent.get('frame') != before
            or intent.get('page') != 'TITLE'):
        return set()
    other_rows = rows[intent_at + 1:sent_at] + rows[sent_at + 1:end_at]
    if any(row.get('input_sent') is True or row['event'].endswith('_intent')
           or row['event'] == 'battle_observed' for row in other_rows):
        return set()
    observations = events('map_observed')
    source = [row for i, row in observations if i < intent_at and row.get('frame') == before]
    response = [row for i, row in observations if sent_at < i < end_at]
    if not source or len(response) < 2 or response[-1].get('frame') != after:
        return set()
    source = source[-1]
    home = response[-1]
    waits = response[:-1]
    wait_events = [(row.get('frame'), row.get('page')) for i, row in events('login_response_wait')
                   if sent_at < i < end_at and row.get('input_sent') is False]
    if (source.get('scene') != 'TITLE' or home.get('scene') != 'HOME'
            or not source.get('image_sha256') or not home.get('image_sha256')
            or source['image_sha256'] == home['image_sha256']
            or source['image_sha256'] != intent.get('image_sha256')
            or wait_events != [(r.get('frame'), r.get('scene')) for r in waits]):
        return set()
    try:
        # Match the actual event identities. Raw proof callers retain final say
        # over the candidate bytes and all independent module references.
        for row in (source, home):
            _, _, raw = observation_frame(run, row)
            if raw['scene'] != row['scene']:
                return set()
        names = [row.get('frame') for row in response]
        if any(not isinstance(n, str) or not re.fullmatch(r'frame-\d+', n) for n in names):
            return set()
        numbers = [int(n[6:]) for n in [before, *names]]
        if any(a >= b for a, b in zip(numbers, numbers[1:])):
            return set()
        seen = set()
        redundant = set()
        for row in waits:
            name, scene = row['frame'], row.get('scene')
            if scene not in LOGIN_WAIT_PAGES:
                return set()
            raw = json.loads((Path(run) / (name + '.json')).read_bytes())
            if (raw.get('scene') != scene or not row.get('image_sha256')
                    or raw.get('image_sha256') != row['image_sha256']):
                return set()
            if scene in seen:
                redundant.add(name)
            seen.add(scene)
        return redundant - {waits[0]['frame'], waits[-1]['frame']}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return set()


def preview_records(run,rows,scene):
    scopes=[r.get('run_scope') for r in rows if r.get('event')=='mirror_loop_start']
    if len(scopes)!=1 or not isinstance(scopes[0],str) or not scopes[0]:return None
    if any(r.get('episode') not in (None,scopes[0]) for r in rows if r.get('event')=='semantic_frame_proposal'):return None
    actor=None;began=False
    for row in rows:
        if str(row.get('event','')).endswith('_intent') or row.get('input_sent'):
            if actor:break
            return None
        if row.get('event')=='mirror_loop_start':began=True
        if row.get('event') in ('map_observed','battle_observed'):
            if row.get('scene')!=scene:return None
            if began:actor=Path(str(row.get('frame') or '')).stem
    if not actor or not re.fullmatch(r'frame-\d+',actor):return None
    try:
        files=sorted((p for p in Path(run).glob('frame-*.json') if re.fullmatch(r'frame-\d+',p.stem)),key=lambda p:int(p.stem[6:]))
        files=[p for p in files if int(p.stem[6:])<=int(actor[6:])]
        if not 2<=len(files)<=16 or files[-1].stem!=actor:return None
        records=[(p,bound_frame(p)[1]) for p in files]
        times=[datetime.fromisoformat(r['utc']) for _,r in records]
        if (any(r['scene']!=scene for _,r in records) or any(t.tzinfo is None for t in times)
                or any(b<=a for a,b in zip(times,times[1:]))
                or not 0<(times[-1]-times[0]).total_seconds()<=30):return None
        return records
    except (OSError,ValueError,KeyError,TypeError):return None
