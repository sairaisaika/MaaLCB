"""Pressure-only reclamation of unreferenced intermediate native captures.

JSON, business/review proof, input boundaries and representative page changes
survive. This never deletes a run directory or changes an account transaction.
"""
from pathlib import Path
import ast
import hashlib
import json
import re

from . import workspace
from .hud_evidence import ORDINARY_HUD_REASONS


INTERMEDIATE_SCENES=frozenset(('MAP','UNKNOWN','BATTLE_HUD','LOADING'))
TRANSIENT_SCENES=frozenset(('UNKNOWN','BATTLE_HUD','LOADING'))
READONLY_HOME_RECENT=2
FRAME=re.compile(r'^frame-\d+$')
CLOSED_EVENTS=frozenset(('mirror_loop_stopped','main_task_stopped','window_capture_session_closed'))


def digest(path):
    with Path(path).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def roots(application_root):
    base=Path(application_root).resolve()
    root=base.parent.parent if base.parent.name=='dist' else base
    return root,(root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime')


def _plain(path,root):
    path=Path(path).absolute()
    if not path.resolve().is_relative_to(root):raise ValueError('Capture target outside workspace')
    for parent in (path,*path.parents):
        if workspace._linked(parent):raise ValueError('Linked capture path')
        if parent==root:break
    return path.resolve()


def reference_inventory(value):
    """A complete read-only pin census is a measurement, not a new pin root.

    Accept the exact legacy diagnostic schema, or its explicitly typed form.
    Extra proof/transaction fields or inconsistent counts keep normal protection.
    The report bytes remain intact; actual business/model/review roots win.
    """
    fields={'read_only','device_input','old_protected','new_protected',
            'additional_protected','installed_evidence_previously_candidate',
            'installed_evidence_now_candidate','workspace_bytes','additional_paths'}
    if not isinstance(value,dict):return False
    if set(value) not in (fields,fields|{'kind'}):return False
    if 'kind' in value and value['kind']!='evidence_reference_inventory':return False
    counts=('old_protected','new_protected','additional_protected','workspace_bytes')
    if any(type(value[k]) is not int or value[k]<0 for k in counts):return False
    paths=value['additional_paths']
    return (value['read_only'] is True and value['device_input'] is False
            and value['installed_evidence_previously_candidate'] is True
            and value['installed_evidence_now_candidate'] is False
            and value['new_protected']-value['old_protected']==value['additional_protected']
            and isinstance(paths,list) and len(paths)==value['additional_protected']
            and all(isinstance(p,str) and bool(p) for p in paths)
            and len(set(paths))==len(paths))


def _source_references(body,root,*,python=False):
    """Conservative literal references, including Python aliases/decorators.

    This does not execute source or infer dynamic frame numbers. A module run
    alias used inside a function pairs with that function's literal frame names;
    unrelated functions do not become a file-wide Cartesian product. Unknown
    Python syntax aborts reclamation instead of silently dropping its pins.
    """
    text=body.decode('utf-8-sig' if python else 'utf8').replace('\r\n','\n').replace('\r','\n');found=set()
    pattern=r'(?:evidence[/\\]runtime[/\\])([\w.-]+)'
    bases=(root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime')
    def keep(runs,names):
        for run in runs:
            for name in names:
                for base in bases:
                    p=base/run/name;found.update((p.with_suffix('.png'),p.with_suffix('.json')))
    # Keep the existing prose/split-reference behavior for non-Python sources.
    for match in re.finditer(pattern,text):
        nearby=text[max(0,match.start()-100):match.end()+300]
        keep([match[1]],re.findall(r'frame-\d+',nearby))
    if not python:return found
    tree=ast.parse(text)
    def path_suffix(node):
        # Only static syntax: ROOT / 'evidence' / 'runtime' is a path, not
        # three unrelated literals. An unknown anchor may precede a known
        # suffix; unknown middle pieces never manufacture a run or frame ID.
        if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Div,ast.Add)):
            left,right=path_suffix(node.left),path_suffix(node.right)
            if right is None:return None
            if isinstance(node.op,ast.Add):return left+right if left is not None else None
            return left+'/'+right if left is not None else right
        if isinstance(node,ast.Call) and not node.keywords:
            method=isinstance(node.func,ast.Attribute) and node.func.attr=='joinpath'
            constructor=((isinstance(node.func,ast.Name) and node.func.id=='Path')
                         or (isinstance(node.func,ast.Attribute) and node.func.attr=='Path'))
            if method or constructor:
                parts=[path_suffix(arg) for arg in node.args]
                if not parts or any(part is None for part in parts[1:]):return None
                if method:
                    prefix=path_suffix(node.func.value)
                    if parts[0] is None:return None
                    if prefix is not None:parts.insert(0,prefix)
                elif parts[0] is None:parts=parts[1:]
                return '/'.join(parts) if parts else None
        return None
    def literals(node):
        return [n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    def runs(node,aliases):
        values={name for value in literals(node) for name in re.findall(pattern,value)}
        for n in ast.walk(node):
            suffix=path_suffix(n)
            if suffix is not None:values.update(re.findall(pattern,suffix))
            if isinstance(n,ast.Name):values.update(aliases.get(n.id,()))
        return values
    def assigned(node):
        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
        return [n.id for target in targets for n in ast.walk(target) if isinstance(n,ast.Name)]
    aliases={}
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            for name in assigned(node):aliases[name]=runs(node.value,aliases) if node.value else set()
    functions=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    def fixture(node):
        for decorator in node.decorator_list:
            target=decorator.func if isinstance(decorator,ast.Call) else decorator
            if ((isinstance(target,ast.Attribute) and target.attr=='fixture')
                    or (isinstance(target,ast.Name) and target.id=='fixture')):return True
        return False
    fixture_runs={}
    for node in functions:
        if fixture(node):fixture_runs.setdefault(node.name,set()).update(runs(node,aliases))
    def dependencies(node):
        args=node.args.posonlyargs+node.args.args+node.args.kwonlyargs
        return set().union(*(fixture_runs.get(arg.arg,set()) for arg in args))
    # Indirect parametrization names its frames on the test, while the local
    # fixture owns the run path. Follow that declared dependency, not a module
    # Cartesian product of unrelated runs and frame literals.
    for _ in range(len(fixture_runs)):
        for node in functions:
            if node.name in fixture_runs:fixture_runs[node.name].update(dependencies(node))
    units=[n for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    units.extend(functions)
    for unit in units:
        local=dict(aliases)
        for n in ast.walk(unit):
            if isinstance(n,(ast.Assign,ast.AnnAssign)) and n.value is not None:
                for name in assigned(n):local[name]=runs(n.value,local)
        names={name for value in literals(unit) for name in re.findall(r'frame-\d+',value)}
        owned=runs(unit,local)
        if isinstance(unit,(ast.FunctionDef,ast.AsyncFunctionDef)):owned.update(dependencies(unit))
        keep(owned,names)
    return found


def _reference_keep(root, *, original_byte_documents=()):
    kept=workspace.protected_evidence(root,original_byte_documents=original_byte_documents);lexical=set()
    from .evidence_report_roles import load as report_roles,project as report_projection
    roles,roles_digest=report_roles(root)
    # Build reports are evidence too, even when a transaction no longer names
    # their diagnostic frame. Treat absolute/relative full paths conservatively.
    def visit(value,found):
        if isinstance(value,dict):
            for item in value.values():visit(item,found)
        elif isinstance(value,list):
            for item in value:visit(item,found)
        elif isinstance(value,str):
            value=value.replace('\\','/')
            match=re.search(r'(?:^|/)(evidence/runtime/[^/]+/frame-\d+)(?:\.(?:png|json))?$',value)
            if match:
                for base in (root,root/'dist/MaaLimbus'):
                    p=base/match[1];found.update((p.with_suffix('.png'),p.with_suffix('.json')))
    def report_refs(body):
        value=json.loads(body.decode('utf8'))
        if reference_inventory(value):return set()
        if isinstance(value,dict) and value.get('kind') in (
                'capture_retention_plan','capture_retention_result'):return set()
        value=report_projection(value,body,roles)
        found=set();visit(value,found);return found
    for report in (root/'build').rglob('*.json'):
        if report in original_byte_documents:continue
        if workspace._linked(report) or report.stat().st_size>16_000_000:continue
        try:
            # Administrative deletion plans name their targets for validation;
            # they are not native proof references to those same targets.
            lexical.update(workspace.cached_references(report,root,'report:'+roles_digest,report_refs))
        except (OSError,ValueError):continue
    # Archived closed reports keep the same frame pins as their original bytes.
    # An invalid archive must stop reclamation, never silently unpin its images.
    from .evidence_reports import references as archived_references
    lexical.update(archived_references(root, report_refs,context=roles_digest))
    # Preserve literal and split source/test/document references. A nearby
    # frame name can overprotect, but may never select a frame for deletion.
    for base in (root/'src',root/'agent',root/'tests',root/'docs'):
        for p in base.rglob('*'):
            if p.suffix not in ('.py','.md') or workspace._linked(p):continue
            if p.stat().st_size>8_000_000:continue
            try:lexical.update(workspace.cached_references(p,root,'source-v3',
                lambda body,is_python=p.suffix=='.py':_source_references(body,root,python=is_python)))
            except (OSError,UnicodeError):continue
    project=root/'PROJECT.md'
    if project.is_file():
        lexical.update(workspace.cached_references(project,root,'source-v3',
            lambda body:_source_references(body,root)))
    kept.update(workspace.resolve_references(lexical))
    return kept


def archive_reference_keep(root):
    """Raw needs for lossless storage only; deletion keeps every review pin."""
    from .review_storage import original_byte_documents
    from .native_image_archive import verified_reads
    with verified_reads():
        documents=original_byte_documents(root)
        return (_reference_keep(root,original_byte_documents=documents)
                if documents else _reference_keep(root))


def storage_diagnostic(application_root):
    """Read-only source/frozen parity check, without exposing private frame paths."""
    root, _ = roots(application_root)
    kept = _reference_keep(root)
    from .evidence_reports import load_index
    index = load_index(root)
    names = sorted(path.relative_to(root).as_posix() for path in kept if path.is_relative_to(root))
    return dict(passed=True, protected_references=len(kept),
                references_sha256=hashlib.sha256('\n'.join(names).encode('utf-8')).hexdigest(),
                archived_reports=0 if index is None else len(index['value']['members']),
                archive_index_sha256=None if index is None else index['index_sha256'],
                input_sent=False, game_controller=False)


def input_free_home_history(rows):
    """Only observed HOME reads, with no action or unrecognized producer event."""
    allowed={'map_observed','semantic_frame_proposal','callback_failed','flow_checkpoint_observed',
             'window_capture_session_closed'}
    observed=[row for row in rows if row.get('event')=='map_observed']
    return bool(observed and all(row.get('event') in allowed and not row.get('input_sent')
                                 for row in rows)
                and all(row.get('scene')=='HOME' and row.get('input_sent') is False
                        and isinstance(row.get('image_sha256'),str)
                        and len(row['image_sha256'])==64 for row in observed))


def _completed_battle_inputs(run, rows):
    """Earlier HUD inputs answered by a retained, byte-verified battle result.

    Keep the final input pair of each battle. Missing/changed native proof never
    converts an unfinished fight into permission to compact its input boundary.
    This judges storage eligibility only, not game victory or any ledger event.
    """
    from .native_image_archive import verified_sha
    eligible=set();segment=[];last=None
    for row in rows:
        name=Path(str(row.get('frame') or '')).stem
        if FRAME.fullmatch(name):last=name
        if row.get('event')=='window_intent' and row.get('page') in ('BATTLE_HUD','BATTLE_PLANNING'):
            if last:segment.append(last)
        if (row.get('event') in ('battle_observed','map_observed')
                and row.get('scene')=='BATTLE_RESULT' and FRAME.fullmatch(name)):
            path=run/(name+'.json');png=path.with_suffix('.png')
            try:
                data=json.loads(path.read_text(encoding='utf8'))
                # Witness availability is logical original-byte availability.
                # Actual unlink candidates below still require a raw PNG file.
                identity=verified_sha(png)
                proven=(data.get('scene')=='BATTLE_RESULT' and not workspace._linked(path)
                        and not workspace._linked(png)
                        and identity==data.get('image_sha256')
                        and row.get('image_sha256',data.get('image_sha256'))==data.get('image_sha256'))
            except (OSError,ValueError,TypeError):proven=False
            if not proven:return None
            eligible.update(segment[:-1])
            segment=[]
    return eligible


def _older_hud_diagnostics(run, rows):
    """Bound ordinary nonfinancial HUD diagnostics, not business outcome proof.

    A later independently captured HUD answers the read obligation. Keep the
    last two such inputs and their causal pairs even within an ongoing battle;
    all model/review/transaction references still override this eligibility.
    No success or learning label is inferred from this storage decision.
    """
    from .native_image_archive import verified_sha
    history=[];last=None;pending=None;eligible=set()
    for row in rows:
        name=Path(str(row.get('frame') or '')).stem
        if FRAME.fullmatch(name):
            last=name
            scene=row.get('scene')
            if (scene and scene not in TRANSIENT_SCENES
                    and scene not in ('BATTLE_PLANNING','BATTLE_WAIT','CONNECTING')):
                eligible.update(item['before'] for item in history[:-2] if item['answered'])
                history=[];pending=None
            if (pending and name!=pending['before'] and row.get('scene')=='BATTLE_HUD'
                    and row.get('event') in ('battle_observed','map_observed')):
                record=run/(name+'.json');png=record.with_suffix('.png')
                try:
                    data=json.loads(record.read_text(encoding='utf8'))
                    identity=verified_sha(png)
                    valid=(data.get('scene')=='BATTLE_HUD'
                           and not workspace._linked(record) and not workspace._linked(png)
                           and identity==data.get('image_sha256')
                           and row.get('image_sha256',data.get('image_sha256'))==data.get('image_sha256'))
                except (OSError,ValueError,TypeError):valid=False
                if valid:pending['answered']=True;pending=None
        if row.get('event')=='window_intent':
            pending=None
            if (last and row.get('page')=='BATTLE_HUD'
                    and row.get('reason') in ORDINARY_HUD_REASONS):
                pending=dict(before=last,answered=False);history.append(pending)
    return eligible | {item['before'] for item in history[:-2] if item['answered']}


def _settled_map_inputs(run, rows):
    """Older answered MAP diagnostics; native verdicts own the action outcome.

    Production verdict.frame names the original input, not its successor. Track
    observations separately, keep two accepted-room checks plus the last input
    pair, and never let
    another input or missing/changed native proof discharge an obligation.
    """
    from datetime import datetime
    from .native_evidence import bound_frame,journal_scope
    from .map_vision import map_header
    from .map_dispatch import node_transition
    from .vision import Text
    def stamp(value):
        at=datetime.fromisoformat(value['utc'])
        if at.tzinfo is None:raise ValueError('Unbound diagnostic clock')
        return at
    if journal_scope(rows) is None:return set()
    last=None;pending=None;answered=[]
    for row in rows:
        event=str(row.get('event') or '')
        if event in ('map_observed','battle_observed'):
            name=Path(str(row.get('frame') or '')).stem
            last=name if FRAME.fullmatch(name) else None
        if event=='window_intent':
            pending=(last,row) if last and row.get('page')=='MAP' else None
        elif event.endswith('_intent') or row.get('input_sent') is True:pending=None
        if event!='map_click_result' or pending is None:continue
        before,intent=pending;pending=None;after=Path(str(row.get('after_frame') or last or '')).stem
        # New intents retain the action's original expectation. Legacy journals
        # without it keep only the former MAP/NODE_PANEL contract; a newer
        # planner must never retroactively authorize their preview/room result.
        contract=intent.get('expect',['NODE_PANEL'])
        if (not isinstance(contract,list) or not contract
                or any(not isinstance(value,str) or not value for value in contract)
                or len(set(contract))!=len(contract)):continue
        transition=node_transition(row.get('page'),contract)
        expected=(row.get('page') if transition.outcome==row.get('outcome')
                  and transition.outcome in ('accepted','rejected') else None)
        box=intent.get('target');point=intent.get('point');delay=intent.get('delay_ms')
        declared=Path(str(row.get('frame') or '')).stem
        if (not expected or row.get('page')!=expected or not FRAME.fullmatch(after) or after==before
                or declared not in (before,after) or row.get('target')!=box
                or not isinstance(box,list) or len(box)!=4 or not all(type(v) is int for v in box)
                or min(box[2:])<=0 or not isinstance(point,list) or len(point)!=2
                or not all(type(v) in (int,float) for v in point)
                or not box[0]<=point[0]<box[0]+box[2] or not box[1]<=point[1]<box[1]+box[3]
                or type(delay) not in (int,float) or not 350<=delay<=750):continue
        try:
            _,a=bound_frame(run/(before+'.json'));_,b=bound_frame(run/(after+'.json'))
            if (a.get('scene')!='MAP' or b.get('scene')!=expected
                    or not stamp(a)<=stamp(intent)<stamp(b)<=stamp(row)
                    or row.get('after_image_sha256',b['image_sha256'])!=b['image_sha256']):continue
            header=map_header([Text(t['text'],tuple(t['box']),t['score']) for t in a['ocr']],a['size'])
            if not header or header.floor not in range(1,6) or not header.pack:continue
            if expected=='MAP':
                other=map_header([Text(t['text'],tuple(t['box']),t['score']) for t in b['ocr']],b['size'])
                if not other or (header.floor,header.pack)!=(other.floor,other.pack):continue
            answered.append((before,row['outcome']))
        except (OSError,ValueError,TypeError,KeyError):continue
    accepted=[name for name,outcome in answered if outcome=='accepted']
    # A judged no-op has no game effect or unpaid business result. Its metadata
    # remains, while current last-input/scene and independent learning pins in
    # _run_rows still retain any proof that actually has another owner.
    return {name for name,outcome in answered if outcome=='rejected'}|set(accepted[:-2])


def _older_selection_diagnostics(run,rows):
    """Keep two latest verified selection commits, plus all independent pins.

    A commit is emitted only after the domain transaction settles a single
    count increment. This consumes that contract, never guesses from a page.
    """
    from .deployment_evidence import validate_commit
    groups=[];group=[];previous=None
    for row in rows:
        if row.get('event')!='deployment_selection_committed':continue
        try:value=validate_commit(row['commit'],run)
        except (OSError,ValueError,KeyError,TypeError):continue
        key=(value['scope'],tuple(value['order']))
        if previous is not None and (key!=previous[0] or value['count_before']!=previous[1]):
            groups.append(group);group=[]
        group.append(value);previous=(key,value['count_after'])
    groups.append(group)
    return {Path(value[role]['record']).stem for group in groups for value in group[:-2]
            for role in ('before','after')}


def _discarded_capacity_plans(run,rows):
    """Duplicate read-only proposals explicitly discarded before any intent.

    Keep an earlier same-page native representative from this no-input interval.
    Every actual input endpoint and independent domain/reference owner still wins.
    This is recorder ownership, not an inferred business RunScope or outcome.
    """
    if not all(isinstance(row,dict) for row in rows) or not any(
            row.get('event')=='capacity_plan_discarded' for row in rows):return set()
    from datetime import datetime
    from .native_evidence import frame_reference
    project,_=roots(run.parents[2]);admitted={};representatives={};previous={};endpoints=set()
    last=None;awaiting=False;cache={};discarded=set()
    def native(name):
        if name not in cache:
            try:
                ref,data=frame_reference(run/(name+'.json'));at=datetime.fromisoformat(data['utc'])
                cache[name]=(ref,data,at) if at.tzinfo else None
            except (OSError,ValueError,KeyError,TypeError):cache[name]=None
        return cache[name]
    def key(row):
        if type(row.get('capacity_sequence')) is not int or row['capacity_sequence']<=0:
            raise ValueError('Invalid admission sequence')
        return tuple(row.get(k) for k in ('capacity_sequence','before_frame','before_json_sha256','before_image_sha256'))
    for row in rows:
        event=row.get('event')
        if event in ('map_observed','battle_observed'):
            name=Path(str(row.get('frame') or '')).stem
            if not FRAME.fullmatch(name):continue
            hit=native(name)
            if hit and row.get('scene')==hit[1].get('scene') and row.get('image_sha256')==hit[0].png_sha256:
                scene=hit[1]['scene'];prior=previous.get(scene)
                if prior and prior!=name:
                    older=native(prior)
                    if older and older[2]<hit[2] and older[0].size==hit[0].size:
                        representatives[name]=prior
                previous[scene]=name
            last=name
            if awaiting:endpoints.add(name);awaiting=False
        elif str(event).endswith('_intent') or row.get('input_sent') is True:
            explicit=Path(str(row.get('frame') or '')).stem
            if last:endpoints.add(last)
            if FRAME.fullmatch(explicit):endpoints.add(explicit)
            previous.clear();awaiting=True
        elif (event=='evidence_capacity_admitted' and row.get('kind')=='plan'
                and row.get('input_sent') is False and row.get('storage_maintenance') is True):
            try:admitted[key(row)]=row
            except (TypeError,ValueError):continue
        elif event=='capacity_plan_discarded' and row.get('kind')=='plan' and row.get('input_sent') is False:
            try:
                if key(row) not in admitted:continue
                path=Path(row['before_frame']);path=path if path.is_absolute() else project/path
                if path.parent!=run or path.suffix!='.json' or not FRAME.fullmatch(path.stem):continue
                hit=native(path.stem);older=native(representatives[path.stem])
                at=datetime.fromisoformat(row['utc'])
                if (hit and older and at.tzinfo and hit[2]<=at
                        and hit[1].get('scene') in ('HOME','DRIVE','MIRROR_ENTRY','DUNGEON_PROGRESS','MAP','BATTLE_HUD')
                        and hit[0].json_sha256==row['before_json_sha256']
                        and hit[0].png_sha256==row['before_image_sha256']):discarded.add(path.stem)
            except (OSError,ValueError,KeyError,TypeError):continue
    return discarded-endpoints


def _released_poll_diagnostics(rows):
    """Project the middle of completed reader-declared waits onto frame identities."""
    if not any(row.get('capture_role') == 'diagnostic_poll' for row in rows):
        return {}
    end = next((i for i in range(len(rows)-1, -1, -1)
                if rows[i].get('event') in CLOSED_EVENTS), None)
    if end is None or any(row.get('input_sent') is True or row.get('event') == 'loop_heartbeat'
                          or str(row.get('event')).endswith('_intent') for row in rows[end+1:]):
        return {}

    series = []
    kept = set()
    released = {}
    attempt = None
    observations = set()
    read_only = False

    def finish_series():
        if series:
            kept.update((series[0][0], series[-1][0]))
            for previous, current, following in zip(series, series[1:], series[2:]):
                name, scene, image_hash = current
                if previous[2] == following[2] != image_hash:
                    kept.add(name)
                else:
                    released[name] = (scene, image_hash)
            series.clear()

    for row in rows[:end]:
        event = row.get('event')
        ordinal = row.get('step_attempt')
        if event in CLOSED_EVENTS:
            kept.update(item[0] for item in observations)
            finish_series()
            attempt = None
            observations = set()
            read_only = False
        elif event == 'loop_heartbeat' and row.get('phase') == 'step_start':
            if attempt is not None:
                kept.update(item[0] for item in observations)
                finish_series()
            attempt = ordinal if type(ordinal) is int and ordinal > 0 else None
            observations = set()
            read_only = attempt is not None
            if not read_only:
                finish_series()
        elif row.get('input_sent') is True or str(event).endswith('_intent'):
            read_only = False
            finish_series()
        elif event == 'step_observation':
            name, scene, image_hash = (row.get(key) for key in ('frame', 'scene', 'image_sha256'))
            if (isinstance(name, str) and FRAME.fullmatch(name)
                    and isinstance(scene, str) and scene and isinstance(image_hash, str)
                    and re.fullmatch(r'[0-9a-f]{64}', image_hash)):
                if attempt is not None and ordinal == attempt and row.get('phase') == 'observe':
                    observations.add((name, scene, image_hash))
                else:
                    kept.add(name)
                    read_only = False
                    finish_series()
            else:
                read_only = False
                finish_series()
        elif event == 'step_finished':
            if (attempt is not None and ordinal == attempt and read_only and len(observations) == 1
                    and row.get('capture_role') == 'diagnostic_poll'
                    and row.get('waiting') is True and row.get('dispatched') is False):
                observation = next(iter(observations))
                if observation[1] == row.get('page'):
                    if series and series[-1][1] != observation[1]:
                        finish_series()
                    if not series or series[-1] != observation:
                        series.append(observation)
                else:
                    kept.add(observation[0])
                    finish_series()
            else:
                kept.update(item[0] for item in observations)
                finish_series()
            attempt = None
            observations = set()
    kept.update(item[0] for item in observations)
    finish_series()
    return {name: identity for name, identity in released.items() if name not in kept}


#: Finished runs newer than these, per runtime folder, keep their structural frames.
#: Older finished runs leave for the archive whole, except what a reference pins.
AGED_AFTER_RUNS=5


def _run_rows(run,current,recent,selection_index=None,hud_index=None,viewport_index=None,aged=False):
    records=sorted(run.glob('frame-*.json'))
    if not records:return []
    events=run/'events.jsonl'
    if not events.is_file():return []
    try:
        rows=[json.loads(line) for line in events.read_text(encoding='utf8').splitlines()]
        if any(not isinstance(row,dict) for row in rows):return []
        if aged and not current and any(row.get('event') in CLOSED_EVENTS for row in rows):
            # An older finished run: every frame may leave for the archive (moved with
            # its record, never deleted). Before 2026-11-28 only a few kinds of frame of
            # a run that ended `passed` could move, almost every task ends on some stop,
            # and the live install held 7 GB of frames over a 3 GB warning line.
            # References (state, data folder, reports, sources) and causal components
            # still pin what they pin; the caller removes those.
            return [(p,dict(json.loads(p.read_text(encoding='utf8')),_retention='aged_closed_run'))
                    for p in records]
        readonly=False
        result=run/'result.json'
        if not current and run.name.startswith('map-live-') and result.is_file() and not workspace._linked(result):
            value=json.loads(result.read_text(encoding='utf8'))
            task=value.get('task_result') or {}
            readonly=bool(value.get('controller')=='Maa AdbController'
                and value.get('input_method')=='Null' and value.get('input_sent') is False
                and value.get('stop_confirmed') is True and task.get('stop_confirmed') is True
                and task.get('timed_out') is False and task.get('interrupted') is False
                and not any(row.get('input_sent') or row.get('event') in (
                    'window_intent','unknown_exploration_intent','party_intent') for row in rows))
        if not current and not readonly and not any(row.get('event') in CLOSED_EVENTS for row in rows):return []
        endings=[row for row in rows if row.get('event') in CLOSED_EVENTS]
        # Legacy events do not declare this role and remain on the existing path.
        released_polls = {} if current else _released_poll_diagnostics(rows)
        readonly_home=bool(endings and endings[-1].get('event')=='window_capture_session_closed'
            and endings[-1].get('input_sealed') is True and endings[-1].get('input_free_home') is True
            and input_free_home_history(rows))
        compact_inputs=bool(not current and endings and endings[-1].get('passed') is True)
        # A completed battle's outcome is independent of whether the entire
        # controller session has ended. Only answered earlier inputs compact;
        # the current unfinished battle and its final causal pair stay pinned.
        settled_inputs=_completed_battle_inputs(run,rows)
        if settled_inputs is None:return []
        settled_inputs.update(_older_hud_diagnostics(run,rows))
        selected_inputs=_older_selection_diagnostics(run,rows)
        projection=(selection_index or {}).get(run,{})
        hud=(hud_index or {}).get(run,{})
        viewport=(viewport_index or {}).get(run,{})
        settled_inputs.update(hud.get('superseded',set()))
        settled_inputs.update(hud.get('turn_answers',{}))
        superseded=projection.get('superseded',set())|projection.get('previews',set())
        superseded=superseded|hud.get('superseded',set())
        bootstrap=projection.get('bootstrap',set())|hud.get('bootstrap',set())
        selected_inputs.update(superseded);selected_inputs.update(bootstrap)
        map_diagnostics=_settled_map_inputs(run,rows)
        discarded_plans=_discarded_capacity_plans(run,rows)
        settled_inputs.update(map_diagnostics)
        tail=READONLY_HOME_RECENT if readonly_home else recent
        keep={p.stem for p in records[-tail:]};keep.add(records[0].stem)
        hard_keep={p.stem for p in records[-tail:]} if current else set()
        # First/tail positions of a recorder are diagnostic structural pins.
        # Explicit later domain commits can supersede them across recorders;
        # real non-selection inputs and all external roots remain stronger.
        last=None;awaiting_after=None;last_input=None;last_input_after=None;input_after=None
        for row in rows:
            name=Path(str(row.get('frame') or '')).stem
            # A map verdict names its original input frame. It is not a new
            # capture and must not rewind the observation/input-boundary cursor.
            if FRAME.fullmatch(name) and row.get('event')!='map_click_result':
                if input_after and name!=input_after:
                    last_input_after=name;input_after=None
                if awaiting_after:
                    keep.add(name);hard_keep.add(name)
                    if name!=awaiting_after:awaiting_after=None
                last=name
            if row.get('event') in ('window_intent','flow_intent','unknown_exploration_intent','map_view_probe','map_view_intent'):
                if last is None:return []
                if row.get('event')=='window_intent':
                    last_input=last;last_input_after=None;input_after=last
                compact_this=(row.get('event')=='window_intent'
                              and (compact_inputs or last in settled_inputs
                                   or (last in selected_inputs and row.get('reason')=='team_card_joins_the_next_unpicked_identity')))
                view_diagnostic=(row.get('event')=='map_view_intent' or
                    (row.get('event')=='map_view_probe' and row.get('input_sent') is False))
                if view_diagnostic and last in viewport.get('superseded',set()):
                    compact_this=True
                if not compact_this:
                    keep.add(last);hard_keep.add(last);awaiting_after=last
            if row.get('event')=='view_normalised' and last:keep.add(last)
        # Older successfully closed controller sessions can compact ordinary
        # intermediate inputs. Keep the last causal boundary even if that
        # session ended at a step limit; unknown exploration and referenced
        # business/model/review proof never lose their independent protection.
        if last_input in hud.get('turn_answers',{}):
            last_input_after=hud['turn_answers'][last_input]
        keep.update(name for name in (last_input,last_input_after) if name)
        if current:hard_keep.update(name for name in (last_input,last_input_after) if name)
        previous=None;transient_seen=set()
        data=[]
        for path in records:
            record=json.loads(path.read_text(encoding='utf8'))
            scene=record['scene']
            # Unreadable/loading observations do not themselves establish a
            # new named page. MAP/UNKNOWN animation oscillation used to pin
            # every pair as a fictitious scene boundary. Keep one uncertainty
            # representative within the named-page visit; real named changes,
            # actual input pairs and external proof still win independently.
            if scene not in ('UNKNOWN','LOADING'):
                if scene!=previous:
                    keep.add(path.stem)
                    if data:keep.add(data[-1][0].stem)
                    transient_seen=set()
                previous=scene
            if scene in TRANSIENT_SCENES and scene not in transient_seen:
                keep.add(path.stem);transient_seen.add(scene)
            data.append((path,record))
        # A native-verified input-free preflight replica is not the actor's
        # before-image. Its explicit domain role can supersede structural tail
        # position; actual last input boundaries and all external roots win.
        startup=(projection.get('startup_previews',set())|hud.get('startup_previews',set()))-{last_input,last_input_after}
        hard_keep.difference_update(startup)
        keep.difference_update((bootstrap | (superseded if not current else set()))-hard_keep)
        required=projection.get('required',set())|hud.get('required',set())|viewport.get('required',set())
        discarded_plans.difference_update(required|{last_input,last_input_after})
        hard_keep.difference_update(discarded_plans);keep.difference_update(discarded_plans)
        keep.difference_update(hud.get('superseded',set())-hard_keep-required)
        keep.update(required)
        keep.difference_update(viewport.get('superseded',set())-hard_keep-required)
        # A navigation verdict closes that input's diagnostic obligation even
        # while the exploration continues. Keep the two latest accepted inputs,
        # current tail/last input, and every independent raw requirement.
        keep.difference_update(map_diagnostics-required-(hard_keep if current else set()))
        from .startup_evidence import answered_login_diagnostics
        login_diagnostics = answered_login_diagnostics(run, rows) - required - hard_keep - {last_input,last_input_after}
        keep.difference_update(login_diagnostics)
        return [(p,r) for p,r in data if p.stem not in keep
                and (readonly or r['scene'] in INTERMEDIATE_SCENES or p.stem in selected_inputs
                     or p.stem in discarded_plans or p.stem in login_diagnostics
                     or released_polls.get(p.stem) == (r['scene'], r.get('image_sha256'))
                     or (readonly_home and r['scene']=='HOME'))]
    except (OSError,ValueError,KeyError,TypeError):return []


def _unfinished_retirements(root,runtimes):
    """Finish only previously hash-bound storage intents, never game intents.

    A crash can occur after one member of a verified diagnostic group is gone.
    Remaining members keep their own durable retirement authority; missing
    pixels never become action/outcome/learning evidence. Fresh references win.
    """
    pending={}
    for base in runtimes:
        if not base.is_dir():continue
        for manifest in base.glob('*/capture-retention.jsonl'):
            if workspace._linked(manifest) or manifest.stat().st_size>16_000_000:continue
            try:
                rows=[json.loads(line) for line in manifest.read_text(encoding='utf8').splitlines()]
                local={}
                for row in rows:
                    if row.get('event')=='capture_reclaim_intent':local[row['path']]=row
                    elif row.get('event')=='capture_reclaimed':local.pop(row['path'],None)
                for row in local.values():
                    if row.get('reason')!='unreferenced_intermediate_capture':continue
                    png=_plain(root/row['path'],root);record=_plain(root/row['record'],root)
                    if 'diagnostic_role' in row:
                        if row['diagnostic_role']!='discarded_noninput_plan':continue
                        trace=[json.loads(line) for line in (png.parent/'events.jsonl').read_text(encoding='utf8').splitlines()]
                        if png.stem not in _discarded_capacity_plans(png.parent,trace):continue
                    if (png.parent.parent not in runtimes or not FRAME.fullmatch(png.stem)
                            or record!=png.with_suffix('.json')
                            or not png.is_file() or not record.is_file()
                            or digest(png)!=row['sha256'] or digest(record)!=row['record_sha256']):continue
                    data=json.loads(record.read_text(encoding='utf8'))
                    if data.get('image_sha256')==row['sha256'] and data.get('scene')==row['scene']:
                        pending[png]=(record,data)
            except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    return pending


def diagnostic_groups(application_root,directory=None,*,recent=8,raw_only=True):
    """Shared ordinary-deletion authority for raw and cold representations.

    No lossless proposal exemption. Pending/model/source/report references and
    causal components remain stronger; a cold caller must keep a whole component
    together rather than use one endpoint as permission to discard its witness.
    """
    root,runtimes=roots(application_root)
    if type(recent) is not int or recent<2:raise ValueError('Retain at least two recent frames')
    if directory is not None:
        directory=_plain(directory,root)
        if directory.parent not in runtimes:return []
    from .native_image_archive import completed_retention_check
    kept=_reference_keep(root)
    completed_retention_check()
    from .deployment_evidence import diagnostic_index
    selection_index=diagnostic_index(runtimes)
    completed_retention_check()
    from .hud_evidence import diagnostic_index as hud_diagnostics
    hud_index=hud_diagnostics(runtimes)
    completed_retention_check()
    from .viewport_evidence import diagnostic_index as viewport_diagnostics
    viewport_index=viewport_diagnostics(runtimes)
    completed_retention_check()
    external=set(kept)
    for run,projection in list(selection_index.items())+list(hud_index.items()):
        for pair in projection['causal_pairs']:
            paths={run/(name+suffix) for name in pair for suffix in ('.json','.png')}
            if paths & external:kept.update(paths)
    runs=[]
    for runtime in runtimes:
        if not runtime.is_dir() or workspace._linked(runtime):continue
        closed=sorted(p for p in runtime.iterdir() if p.is_dir() and not workspace._linked(p))
        # A closed session retains its own recent captures and outstanding
        # boundaries; being one of the newest five does not pin its entire
        # otherwise eligible history. Active foreign sessions still refuse.
        # Recency is when the run last wrote its journal, not its name: folders
        # of several prefixes share a runtime and their names do not sort by time.
        def written(p):
            try:return (p/'events.jsonl').stat().st_mtime
            except OSError:return p.stat().st_mtime
        newest=set(sorted((p for p in closed if p!=directory),key=written)[-AGED_AFTER_RUNS:])
        runs.extend((p,False,p not in newest) for p in closed if p!=directory)
    if directory is not None:runs.append((directory,True,False))
    candidates={}
    for run,current,aged in runs:
        for record,data in _run_rows(run,current,recent,selection_index,hud_index,viewport_index,aged=aged):
            png=record.with_suffix('.png')
            if png.resolve() in kept or record.resolve() in kept or (raw_only and not png.is_file()):continue
            candidates[png]=(record,data)
    for png,pair in _unfinished_retirements(root,runtimes).items():
        if png not in kept and pair[0] not in kept:candidates.setdefault(png,pair)
    # Retire each eligible causal component together. Taking only the first
    # endpoint would erase the witness needed to judge its remaining diagnostics.
    parent={p:p for p in candidates}
    def leader(p):
        while parent[p]!=p:
            parent[p]=parent[parent[p]];p=parent[p]
        return p
    for run,projection in list(selection_index.items())+list(hud_index.items()):
        for pair in projection['causal_pairs']:
            members=[run/(name+'.png') for name in pair
                     if not raw_only or run/(name+'.png') in candidates]
            for p in members:parent.setdefault(p,p)
            for p in members[1:]:parent[leader(p)]=leader(members[0])
    components={}
    for png in parent:components.setdefault(leader(png),[]).append(png)
    return [[(png,*candidates[png]) for png in members] for members in components.values()
            if all(png in candidates for png in members)]


def plan(application_root,directory,additional_bytes,*,recent=8,budget=None,prefer_extra=0):
    from .native_image_archive import verified_reads
    with verified_reads():
        return _plan(application_root,directory,additional_bytes,recent=recent,budget=budget,
                     prefer_extra=prefer_extra)


def _plan(application_root,directory,additional_bytes,*,recent=8,budget=None,prefer_extra=0):
    if type(additional_bytes) is not int or additional_bytes<0:raise ValueError('Invalid capture reservation')
    if type(prefer_extra) is not int or prefer_extra<0:raise ValueError('Invalid preferred capture reserve')
    if type(recent) is not int or recent<2:raise ValueError('Retain at least two recent frames')
    root,runtimes=roots(application_root);directory=_plain(directory,root)
    budget=workspace.BUDGET_BYTES if budget is None else budget
    if type(budget) is not int or not 0<budget<=workspace.BUDGET_BYTES:raise ValueError('Invalid workspace cap')
    preferred_bytes=min(budget,additional_bytes+prefer_extra)
    used=workspace.size(root)
    result=dict(kind='capture_retention_plan',root=str(root),directory=str(directory),additional_bytes=additional_bytes,
                recent=recent,budget=budget,used_bytes=used,files=[],sufficient=used+additional_bytes<=budget)
    if result['sufficient']:return result
    # Other diagnostics retain their old reservation semantics, but do not
    # acquire permission to reclaim unrelated project captures.
    if directory.parent not in runtimes:return result
    freed=0;discarded_by_run={};minimum=None
    for members in diagnostic_groups(application_root,directory,recent=recent):
        selected=[]
        for png,record,data in members:
            _plain(png,root);_plain(record,root)
            sha=digest(png)
            if sha!=data.get('image_sha256'):selected=[];break
            row=dict(path=str(png.relative_to(root)),sha256=sha,bytes=png.stat().st_size,
                     record=str(record.relative_to(root)),record_sha256=digest(record),
                     scene=data['scene'],reason='unreferenced_intermediate_capture')
            if png.parent not in discarded_by_run:
                trace=[json.loads(line) for line in (png.parent/'events.jsonl').read_text(encoding='utf8').splitlines()]
                discarded_by_run[png.parent]=_discarded_capacity_plans(png.parent,trace)
            if png.stem in discarded_by_run[png.parent]:
                row['diagnostic_role']='discarded_noninput_plan'
            if data.get('_retention')=='aged_closed_run':
                row['diagnostic_role']='aged_closed_run'
            selected.append(row)
        result['files'].extend(selected);freed+=sum(row['bytes'] for row in selected)
        overhead=8192+4096*len(result['files'])
        if used+additional_bytes+overhead-freed<=budget:
            if not prefer_extra or used+preferred_bytes+overhead-freed<=budget:
                result.update(additional_bytes=max(additional_bytes,preferred_bytes),
                              sufficient=True,reclaimable_bytes=freed,manifest_reservation=overhead)
                return result
            if minimum is None:
                minimum=dict(result,sufficient=True,files=list(result['files']),
                             reclaimable_bytes=freed,manifest_reservation=overhead)
    if minimum is not None:return minimum
    result.update(reclaimable_bytes=freed,manifest_reservation=8192+4096*len(result['files']))
    return result


#: Reclaimed captures leave the project folder for this sibling folder; they are not
#: destroyed. The user's rule (2026-11-22): the folder limit is a warning line, and
#: evidence is moved out with a record of where it went, never deleted.
ARCHIVE_SUFFIX='-evidence-archive'


def retire_capture(png,root,sha256):
    """Move one reclaimed frame to the archive beside the project; return its archive path.

    The path inside the archive repeats the path inside the project, so a frame can be
    put back by hand. A same-volume move is a rename; across volumes the bytes are
    copied, compared with the planned digest and only then removed from the project.
    Where no archive can be written the frame stays where it is and the error is raised:
    reclaiming is refused rather than turned into a deletion.
    """
    import os
    import shutil
    relative=png.relative_to(root)
    target=root.parent/(root.name+ARCHIVE_SUFFIX)/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if digest(target)!=sha256:
            raise ValueError('Archive already holds a different capture at this path; nothing reclaimed')
        png.unlink()
        return relative.as_posix()
    try:
        os.replace(png,target)
    except OSError:
        shutil.copy2(png,target)
        if digest(target)!=sha256:
            target.unlink()
            raise ValueError('Archived capture differs from the planned bytes; nothing reclaimed')
        png.unlink()
    return relative.as_posix()


def apply(application_root,directory,expected):
    """Replan before any unlink; preserve metadata and a durable deletion trail."""
    current=plan(application_root,directory,expected['additional_bytes'],
                 recent=expected['recent'],budget=expected['budget'])
    if current['files']!=expected['files'] or not current['sufficient']:
        raise ValueError('Capture retention plan changed or protected evidence exhausts budget')
    root=Path(current['root'])
    _delete_rows(root,Path(current['directory']),current['files'],
                 current['manifest_reservation'],budget=current['budget'])
    workspace.require_space(root,current['additional_bytes'],budget=current['budget'])
    return current


def _delete_rows(root,directory,files,manifest_reservation,*,budget,guard=None,recheck_seconds=0,deadline=None):
    """Retire `files` through the trail; return how many left the project.

    `recheck_seconds=0` re-reads every reference before each frame, as every caller did
    while retiring meant deleting. `settle` passes an interval instead: one full re-read
    rehashes every source, test, document and state file, about 0.4 s on a real folder,
    so moving 545 frames (0.81 GB) took 217 s after a 31 s plan (measured 2026-11-23). A frame
    that gained a reference inside the interval is moved to the archive, where it stays
    readable under the same path; it is not lost. `deadline` (monotonic seconds) stops
    between frames; what remains keeps its written intent and is finished by a later
    pass, exactly like an interrupted batch.
    """
    if not files:return 0
    import time
    from .native_image_archive import completed_capture_retirement, completed_retention_check

    if guard is not None:guard()
    manifest=_plain(directory/'capture-retention.jsonl',root)
    # The trail is written before the first unlink. A folder already over its target
    # can never fit the trail under it first, so asking for that refused the one job
    # that brings the folder back: measured 2026-11-21 at 3,327,430,918 bytes, where a
    # 333 MB plan stopped on its own 0.9 MB trail. The trail is admitted against what
    # the plan frees, and against the bytes the volume really has for it.
    reclaim=sum(row['bytes'] for row in files)
    used=workspace.size(root)
    if used+manifest_reservation-reclaim>budget:
        raise ValueError('Workspace budget exceeded after reclamation: %d + %d - %d > %d bytes'
                         % (used,manifest_reservation,reclaim,budget))
    workspace.require_disk_space(root,manifest_reservation)
    manifest.parent.mkdir(parents=True,exist_ok=True)
    for row in files:
        png=_plain(root/row['path'],root);record=_plain(root/row['record'],root)
        if digest(png)!=row['sha256'] or digest(record)!=row['record_sha256']:
            raise ValueError('Capture evidence or references changed; preserve remaining frames')
    completed_retention_check()
    # Persist every member before unlinking the first member of a component.
    with manifest.open('a',encoding='utf8') as handle:
        for row in files:
            handle.write(json.dumps(dict(event='capture_reclaim_intent',**row))+'\n')
        handle.flush()
        import os
        os.fsync(handle.fileno())
    kept=None;read_at=0.0;moved=0
    for row in files:
        if deadline is not None and time.monotonic()>=deadline:break
        if guard is not None:guard()
        png=_plain(root/row['path'],root);record=_plain(root/row['record'],root)
        if kept is None or time.monotonic()-read_at>=recheck_seconds:
            kept=_reference_keep(root);read_at=time.monotonic()
        if png in kept or record in kept or digest(png)!=row['sha256'] or digest(record)!=row['record_sha256']:
            raise ValueError('Capture evidence or references changed; preserve remaining frames')
        if guard is not None:guard()
        completed_retention_check()
        archived=retire_capture(png,root,row['sha256'])
        with manifest.open('a',encoding='utf8') as handle:
            handle.write(json.dumps(dict(event='capture_reclaimed',path=row['path'],sha256=row['sha256'],
                                         archived=archived))+'\n')
            handle.flush()
            os.fsync(handle.fileno())
        # Raw reclamation can follow warm archive reads for a long batch. Only
        # this actual completed unit refreshes the existing progress watch.
        completed_capture_retirement()
        moved+=1
    return moved



def prune_discarded_plan(directory,before_frame):
    """Retire only this controller owner's duplicate, never-submitted proposal.

    Storage work finishes before the replacement native read. Ordinary domain
    requirements, actual input endpoints and all independent references win.
    """
    directory=Path(directory).absolute()
    if directory.parent.name!='runtime' or directory.parent.parent.name!='evidence':return 0
    root,_=roots(directory.parents[2]);directory=_plain(directory,root)
    target=Path(before_frame);target=target if target.is_absolute() else root/target
    target=_plain(target,root)
    if target.parent!=directory or target.suffix!='.json' or not FRAME.fullmatch(target.stem):
        raise ValueError('Discarded proposal belongs to another recorder')
    from .native_image_archive import verified_reads,deferred_progress
    with verified_reads(),deferred_progress():
        rows=[json.loads(line) for line in (directory/'events.jsonl').read_text(encoding='utf8').splitlines()]
        if target.stem not in _discarded_capacity_plans(directory,rows):return 0
        candidates=diagnostic_groups(root,directory,recent=2)
        selected=next((group for group in candidates if len(group)==1 and group[0][1]==target),None)
        if selected is None:return 0
        png,record,data=selected[0];sha=digest(png)
        if sha!=data.get('image_sha256'):raise ValueError('Discarded proposal image changed')
        files=[dict(path=str(png.relative_to(root)),sha256=sha,bytes=png.stat().st_size,
                    record=str(record.relative_to(root)),record_sha256=digest(record),
                    scene=data['scene'],reason='unreferenced_intermediate_capture',
                    diagnostic_role='discarded_noninput_plan')]
        def snapshot():
            return {p:digest(_plain(p,root)) for p in directory.iterdir() if p.is_file()
                    and ((FRAME.fullmatch(p.stem) and p.suffix in ('.json','.png')) or p.name=='events.jsonl')}
        before=snapshot()
        def guard():
            if snapshot()!=before:raise ValueError('Discarded proposal witnesses changed')
        _delete_rows(root,directory,files,12288,budget=workspace.BUDGET_BYTES,guard=guard)
        return files[0]['bytes']


def reserve(directory,additional_bytes,*,application_root,prefer_extra=0):
    from .native_image_archive import verified_reads
    with verified_reads():
        return _reserve(directory,additional_bytes,application_root=application_root,prefer_extra=prefer_extra)


def _reserve(directory,additional_bytes,*,application_root,prefer_extra=0):
    root,runtimes=roots(application_root)
    directory=Path(directory).resolve()
    if not directory.is_relative_to(root):return None
    from .native_image_archive import VAULT_POLICY
    vault={}
    if (directory.parent in runtimes and (root/VAULT_POLICY).exists()
            and workspace.size(root)+additional_bytes>workspace.BUDGET_BYTES):
        from .native_cold_vault import VaultUnavailable,offload
        before=workspace.size(root)
        try:
            value=offload(root,target_free=additional_bytes,max_containers=2)
            if value['containers']:
                vault=dict(vault_containers=value['containers'],vault_project_bytes_freed=value['freed_bytes'])
        except VaultUnavailable:
            # The failed operation either never moved its blob or rolled it
            # back. Earlier completed moves in this batch still require a fresh plan.
            vault=dict(vault_unavailable=True,vault_project_bytes_freed=max(0,before-workspace.size(root)))
    options={'prefer_extra':prefer_extra} if prefer_extra else {}
    reservation=plan(application_root,directory,additional_bytes,**options)
    if not reservation['sufficient']:
        # Prefer eight diagnostic tail frames, then the supported two-frame
        # minimum. Input/scene/transaction/review/source pins are unchanged.
        reservation=plan(application_root,directory,additional_bytes,recent=2,**options)
    if reservation['files'] and reservation['sufficient']:
        return dict(apply(application_root,directory,reservation),storage_maintenance=True,**vault)
    if not reservation['sufficient']:
        # The current producer already owns the controller lease. Bounded cold
        # storage keeps old diagnostic bytes, and never touches pending proof.
        # Stop before a third batch; the original run deadline is never extended.
        from .native_image_archive import compact
        from .cold_retention import reclaim as reclaim_cold
        for _ in range(2):
            # Same ordinary deletion roles apply to cold representations. A
            # verified rewrite may free bytes which the raw-only plan cannot.
            # At most two storage publications; neither changes game pending.
            result=reclaim_cold(root,directory=directory,max_containers=1)
            freed=result.get('freed_bytes',0)
            if freed<=0:
                room=reservation['budget']-workspace.size(root)-3_000_000
                if room<=0:break
                result=compact(root,max_bytes=min(8_000_000,room))
                freed=result.get('freed',0)
            if freed<=0:break
            reservation=plan(application_root,directory,additional_bytes,recent=2,**options)
            if reservation['sufficient']:
                value=apply(application_root,directory,reservation) if reservation['files'] else reservation
                return dict(value,storage_maintenance=True,**vault)
    if not reservation['sufficient']:
        raise ValueError('Workspace budget exceeded; protected captures retained; '
                         'used=%d requested=%d reclaimable=%d limit=%d recent=%d%s' % (
                             reservation['used_bytes'],additional_bytes,
                             reservation['reclaimable_bytes'],reservation['budget'],reservation['recent'],
                             ' local_vault_unavailable' if vault.get('vault_unavailable') else ''))
    if vault.get('vault_project_bytes_freed'):
        vault['storage_maintenance']=True
    return dict(reservation,**vault)


#: After a task has ended the program brings the folder this far under the warning line,
#: so the next task starts with room instead of starting over the line.
SETTLE_HEADROOM=400_000_000
#: The longest the moving phase of one end-of-task reclaim may take. What it did not
#: reach keeps its intent in the trail and is the first thing the next task moves.
SETTLE_SECONDS=180.0
#: How long one full read of the references is trusted while frames are being moved.
SETTLE_RECHECK_SECONDS=15.0
#: The program never trims the archive. Past this size it says how large the archive is.
ARCHIVE_NOTICE_BYTES=8_000_000_000


def settle(application_root,directory,*,headroom=None,recent=8,budget=None,seconds=None):
    """End-of-task reclaim: move out of the project what the retention rule already allows.

    `reserve` serves an offline allocation. A live task checks free disk space and
    reclaims nothing, so an installation that is left running grew past the warning
    line task after task (3.4 GB measured 2026-11-23 after two days of runs, and a
    start had to be unblocked by hand the day before). This runs once after a task has written
    its ending, under that task's controller lease and with no game input.

    Selection is `plan`'s and retirement is `_delete_rows`': the same references win and
    every frame leaves through the same hash-bound trail into the archive. Two things
    differ: the target lies `headroom` below the line, and a plan that cannot reach the
    target is still applied, because moving some frames out is progress. "Could not
    reach the target" is reported in the summary, never raised. The moving phase is
    bounded by `seconds`; frames it did not reach are reported as `left`.
    """
    import time
    from .native_image_archive import verified_reads
    root,runtimes=roots(application_root)
    if seconds is None:seconds=SETTLE_SECONDS
    if type(seconds) not in (int,float) or seconds<0:raise ValueError('Invalid settle time bound')
    line=workspace.BUDGET_BYTES if budget is None else budget
    if type(line) is not int or not 0<line<=workspace.BUDGET_BYTES:raise ValueError('Invalid workspace cap')
    if headroom is None:headroom=SETTLE_HEADROOM
    if type(headroom) is not int or not 0<=headroom<line:raise ValueError('Invalid settle headroom')
    target=line-headroom
    # Only a task's own run folder inside this installation gives authority to reclaim.
    # A task pointed at a folder elsewhere (a test, a diagnostic) touches nothing here,
    # and is answered before the folder is even measured.
    if Path(directory).resolve().parent not in runtimes:
        return dict(kind='capture_settle',skipped='run_folder_outside_this_installation',moved=0,moved_bytes=0,
                    target_bytes=target,line_bytes=line,over_line=False,archive_notice=False)
    used=workspace.size(root)
    summary=dict(kind='capture_settle',used_bytes=used,target_bytes=target,line_bytes=line,moved=0,moved_bytes=0,
                 left=0)
    if used>target:
        with verified_reads():
            current=_plan(application_root,directory,0,recent=recent,budget=target)
            files=current['files']
            if files:
                moved=_delete_rows(root,Path(current['directory']),files,current['manifest_reservation'],
                                   budget=max(target,used),recheck_seconds=SETTLE_RECHECK_SECONDS,
                                   deadline=time.monotonic()+seconds)
                summary.update(moved=moved,moved_bytes=sum(row['bytes'] for row in files[:moved]),
                               left=len(files)-moved)
        used=workspace.size(root)
    archive=root.parent/(root.name+ARCHIVE_SUFFIX)
    archive_bytes=workspace.size(archive)
    summary.update(after_bytes=used,reached=used<=target,over_line=used>line,
                   archive=str(archive),archive_bytes=archive_bytes,
                   archive_notice=archive_bytes>ARCHIVE_NOTICE_BYTES)
    return summary
