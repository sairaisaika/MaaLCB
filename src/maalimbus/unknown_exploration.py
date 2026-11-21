"""Bounded navigation probes and immutable human-review bundles.

Page identity can be unknown while a native Close/Back control is known. These
probes never approve spending, choices, receipts, or their own training labels.
"""
import hashlib
import re
from pathlib import Path
from .storage import read_json, write_json
from .learning_dataset import original_bytes,read_image


class NavigationOutcomeUnproven(ValueError):
    """An unacknowledged attempt has no independent positive successor yet."""


MAP_EPISODE_EXITS = frozenset(('NODE_PANEL','NODE_PREVIEW','PRE_BATTLE_TEAM',
    'BATTLE_HUD','SHOP','EVENT_CHOICE','THEME_PACKS'))


def _episode_ended(attempt):
    if attempt.get('success'):
        return True
    return bool(attempt.get('episode_resolved') and (
        not attempt['candidate']['kind'].startswith('map_')
        or attempt.get('resolution_page') in MAP_EPISODE_EXITS))


def digest(path):
    return hashlib.sha256(original_bytes(path)).hexdigest()


def proof(path):
    path=Path(path).resolve(); record=read_json(path)
    png=path.with_suffix('.png'); image=read_image(png)
    if image is None or digest(png)!=record.get('image_sha256'):
        raise ValueError('Exploration frame pixels/hash not proven')
    if record.get('size')!=[image.shape[1],image.shape[0]]:
        raise ValueError('Exploration frame geometry not proven')
    return dict(record=str(path),record_sha256=digest(path),
                image=str(png),image_sha256=digest(png)),record


def candidates(record, frame=None):
    # Resource dialogs and destructive/run-exit controls require their normal
    # transaction, even when the surrounding page cannot yet be classified.
    text=' '.join(str(t.get('text','')) for t in record.get('ocr',[]))
    if re.search(r'enkephalin|lunacy|refill|give\s*up|forfeit|dungeon\s*progress|to\s*window|claim|rewards? acquired|purchase|confirm|convert',text,re.I):
        return []
    size=record.get('size')
    if not isinstance(size,list) or len(size)!=2:return []
    w,h=size; rows=[]
    if record.get('scene')=='MAP':
        from .map_vision import map_header
        from .vision import Text
        header=map_header([Text(t['text'],tuple(t['box']),t['score']) for t in record.get('ocr',[])],size)
        if header and header.floor is not None and header.pack:
            # This gesture moves only the identified map viewport. Both ends
            # stay above the party strip and away from header/side controls.
            for name,dx,dy in (('down',0,.21),('left',-.20,0),('right',.20,0)):
                rows.append(dict(kind='map_viewport_pan_'+name,action='swipe',
                    box=[round(w*.49),round(h*.55),round(w*.02),round(h*.03)],
                    to_box=[round(w*(.49+dx)),round(h*(.55+dy)),round(w*.02),round(h*.03)],
                    teacher='native_map_header_and_floor',score=1.0,floor=header.floor,pack=header.pack))
            if frame is not None:
                import cv2
                from .map_node_geometry import occupied_node
                identity, original = proof(frame)
                if any(original.get(key)!=record.get(key)
                       for key in ('scene','size','ocr','image_sha256','frame')):
                    raise ValueError('Exploration candidate record differs from canonical frame')
                found = occupied_node(read_image(identity['image']))
                if found:
                    rows.append(dict(kind='map_current_node_inspection', action='click',
                        box=found['box'], teacher=found['source'], score=1.0,
                        floor=header.floor, pack=header.pack,
                        target_role='current_node_inspection',
                        anchor=found, expected_pages=['NODE_PANEL','NODE_PREVIEW',
                            'PRE_BATTLE_TEAM','BATTLE_HUD','SHOP','EVENT_CHOICE']))
            return rows
    closer=record.get('overlay_dismissal') or {}
    if closer.get('kind') in ('tutorial_book','identity_details','unclassified_overlay_return') and closer.get('native_score',0)>=.92:
        rows.append(dict(kind='matched_header_return',box=closer['box'],
                         teacher=closer.get('template'),score=closer['native_score']))
    for label in ('Close','Back','Return','閉じる','戻る','关闭','返回'):
        hits=[t for t in record.get('ocr',[]) if t.get('text','').strip()==label
              and t.get('score',0)>=.95 and len(t.get('box',[]))==4
              and t['box'][1]+t['box'][3]<=h*.22]
        if len(hits)==1:
            rows.append(dict(kind='native_header_'+label,box=list(hits[0]['box']),
                             teacher='native_ocr',score=hits[0]['score']))
    return [r for r in rows if all(type(v) is int for v in r['box'])
            and r['box'][2]>0 and r['box'][3]>0
            and r['box'][0]>=0 and r['box'][1]>=0
            and r['box'][0]+r['box'][2]<=w and r['box'][1]+r['box'][3]<=h]


class Exploration:
    def __init__(self,path,review_root,scope,*,candidate_provider=candidates,successor_check=None):
        self.path=Path(path);self.review_root=Path(review_root);self.scope=scope
        self.candidate_provider=candidate_provider;self.successor_check=successor_check
        self.data=read_json(path) if self.path.exists() else dict(version=1,scope=scope,attempts=[],pending=None)
        if (not isinstance(self.data,dict) or self.data.get('version')!=1
                or self.data.get('scope')!=scope or not isinstance(self.data.get('attempts'),list)):
            raise ValueError('Exploration scope differs; preserve its evidence')
        pending=self.data.get('pending')
        if pending is not None and (type(pending) is not int or not 0<=pending<len(self.data['attempts'])):
            raise ValueError('Exploration pending index invalid; preserve its evidence')

    def choose(self,record,frame=None,*,episode=None):
        recent=[]
        for item in reversed(self.data['attempts']):
            if episode is not None and item.get('episode')!=episode:continue
            if episode is not None:
                recent.append(item);continue
            if _episode_ended(item):break
            recent.append(item)
        used={a['candidate']['kind'] for a in recent}
        count=len(used) if episode is None and all(kind.startswith('map_') for kind in used) else len(recent)
        if self.data.get('pending') is not None or count>=4:return None
        return next((c for c in self.candidate_provider(record,frame) if c['kind'] not in used
                     and (count<3 or c['kind']=='map_current_node_inspection')),None)

    def reserve(self,frame,candidate,point,delay,end=None,*,episode=None):
        before,record=proof(frame)
        if self.data.get('pending') is not None or candidate!=self.choose(record,frame,episode=episode):
            raise ValueError('Exploration candidate absent, repeated or exhausted')
        x,y,w,h=candidate['box']
        if not (x<=point[0]<x+w and y<=point[1]<y+h and 350<=delay<=750):
            raise ValueError('Exploration input outside verified control')
        if candidate.get('action')=='swipe':
            ex,ey,ew,eh=candidate['to_box']
            if end is None or not (ex<=end[0]<ex+ew and ey<=end[1]<ey+eh):
                raise ValueError('Map pan must end inside its bounded canvas region')
        entry=dict(candidate=candidate,before=before,point=list(point),delay_ms=delay,
                   input_attempted=True,dispatch_confirmed=False,successor=None,reviewed=False)
        if episode is not None:entry['episode']=episode
        if end is not None:entry['end']=list(end)
        self.data['attempts'].append(entry);self.data['pending']=len(self.data['attempts'])-1
        write_json(self.path,self.data)
        return self.data['pending']

    def acknowledge(self,index):
        """Call only after the native SDK returns success, never before dispatch."""
        if type(index) is not int or self.data.get('pending')!=index:
            raise ValueError('Exploration acknowledgement does not own pending input')
        if read_json(self.path)!=self.data:
            raise ValueError('Exploration changed during input; preserve pending')
        entry=self.data['attempts'][index]
        if any(digest(entry['before'][key])!=entry['before'][key+'_sha256'] for key in ('record','image')):
            raise ValueError('Exploration original proof changed; preserve pending')
        entry['dispatch_confirmed']=True
        write_json(self.path,self.data)

    def current_room_ready(self,record,frame):
        """An exhausted pan episode may inspect its own room before badge guesses."""
        if not self.data['attempts'] or _episode_ended(self.data['attempts'][-1]):
            return False
        candidate=self.choose(record,frame)
        return candidate is not None and candidate['kind']=='map_current_node_inspection'

    def continuing_map_recovery(self,record,frame):
        """Finish the two already-answered viewport probes' own episode first."""
        if record.get('scene')!='MAP':return False
        pans=set()
        for attempt in reversed(self.data['attempts']):
            if _episode_ended(attempt):break
            control=attempt['candidate']
            if control['kind'].startswith('map_viewport_pan_') and attempt.get('dispatch_confirmed'):
                pans.add((control.get('floor'),control.get('pack'),control['kind']))
        if len(pans)<2:return False
        control=self.choose(record,frame)
        if control is None:return False
        return sum((floor,pack)==(control.get('floor'),control.get('pack'))
                   for floor,pack,_ in pans)>=2

    def finish(self,frame,page):
        index=self.data.get('pending')
        if index is None:return None
        if read_json(self.path)!=self.data:
            raise ValueError('Exploration changed before successor; preserve pending')
        entry=self.data['attempts'][index]
        # Restart may observe a successor, but it cannot replay an attempted input.
        if any(digest(entry['before'][key])!=entry['before'][key+'_sha256'] for key in ('record','image')):
            raise ValueError('Exploration original proof changed; preserve pending')
        after,record=proof(frame)
        if page!=record.get('scene') and record.get('scene')!='UNKNOWN':
            raise ValueError('Exploration successor label not independently observed')
        changed=after['image_sha256']!=entry['before']['image_sha256']
        success=changed and record.get('scene')==page and page not in ('UNKNOWN','UNKNOWN_DIALOG','BATTLE_WAIT','CONNECTING','LOADING')
        if entry['candidate'].get('action')=='swipe':
            # Pixel movement confirms panning, not arrival at a node. Three
            # pans remain the limit until an independently named panel opens.
            success=changed and page=='NODE_PANEL'
        if entry['candidate']['kind']=='map_current_node_inspection':
            success=changed and record.get('scene')==page and page in entry['candidate']['expected_pages']
        if self.successor_check is not None:
            success=changed and bool(self.successor_check(record,page))
        if not entry.get('dispatch_confirmed') and not success:
            raise NavigationOutcomeUnproven('Navigation successor unproven; preserve unacknowledged pending')
        key=hashlib.sha256((self.scope+entry['before']['record_sha256']+after['record_sha256']).encode()).hexdigest()
        destination=self.review_root/key
        from .workspace import reserve_output
        # The proposal already binds the original four paths and hashes; its
        # references pin those canonical files through workspace.protected_evidence.
        reserve_output(destination,65536)
        entry.update(successor=after,page_after=page,changed=changed,success=success)
        destination.mkdir(parents=True,exist_ok=True)
        for prefix,item in (('before',entry['before']),('after',after)):
            for field,suffix in (('record','.json'),('image','.png')):
                target=destination/(prefix+suffix)
                if target.exists() and digest(target)!=item[field+'_sha256']:
                    raise ValueError('Conflicting exploration review proof')
        manifest=dict(version=1,scope=self.scope,attempt=entry,
                      proposed_label=(('dismiss_service_notice_to_' if entry['candidate']['kind']=='service_notice_close'
                                       else 'inspect_current_room_to_' if entry['candidate']['kind']=='map_current_node_inspection'
                                       else 'return_overlay_to_')+page) if success else 'unresolved_navigation',
                      teacher='native_successor_after_bounded_navigation',reviewed=False,
                      training_eligible=False,input_authorized=False,
                      review_file='review.json',success=success)
        write_json(destination/'proposal.json',manifest)
        (destination/'trace.log').write_text(
            'Bounded native navigation\nControl: '+entry['candidate']['kind']+
            '\nAfter: '+page+'\nSuccess: '+str(success)+'\n',encoding='utf-8')
        if not (destination/'review.json').exists():
            write_json(destination/'review.json',dict(status='pending',approved=False,corrected_label=None,notes=''))
        self.data['pending']=None
        write_json(self.path,self.data)
        return dict(proposal=str(destination/'proposal.json'),success=success,changed=changed,
                    training_eligible=False,input_authorized=False)

    def resolve_episode(self,frame,page):
        if self.data.get('pending') is not None or not self.data['attempts']:return
        last=self.data['attempts'][-1]
        if _episode_ended(last):return
        allowed=(MAP_EPISODE_EXITS if last['candidate']['kind'].startswith('map_')
                 else ('NODE_PANEL','BATTLE_HUD','SHOP','THEME_PACKS','HOME'))
        if page not in allowed:return
        evidence,record=proof(frame)
        if record.get('scene')!=page:return
        # A later normal task input may resolve the episode. Do not relabel
        # the earlier pan as an action that directly opened that page.
        last.update(episode_resolved=True,resolution_page=page,resolution=evidence,
                    resolved_via_subsequent_task_action=True)
        write_json(self.path,self.data)


def queue_trial(frame,offer,scope,root):
    source,record=proof(frame)
    key=hashlib.sha256((scope+source['record_sha256']+offer.title).encode()).hexdigest()
    folder=Path(root)/'trials'/key
    from .workspace import reserve_output
    reserve_output(folder,sum(len(original_bytes(source[field])) for field,suffix in (('record','.json'),('image','.png'))
                              if not (folder/('frame'+suffix)).exists())+65536)
    folder.mkdir(parents=True,exist_ok=True)
    for field,suffix in (('record','.json'),('image','.png')):
        destination=folder/('frame'+suffix)
        if destination.exists() and digest(destination)!=source[field+'_sha256']:
            raise ValueError('Conflicting trial review pixels')
        if not destination.exists():destination.write_bytes(original_bytes(source[field]))
    proposal=dict(version=1,scope=scope,source=source,title=offer.title,
        observed_level=offer.trial.level,printed_trial=offer.unpriced,
        proposed_label='unclassified_enemy_trial',teacher='native_ocr',
        reviewed=False,training_eligible=False,input_authorized=False)
    template=re.sub(r'\d+(?:\.\d+)?','#',offer.unpriced.casefold())
    template=re.sub(r'\s+',' ',template).strip()
    proposal.update(text_template=template,
        proposed_group='enemy_trial_text_'+hashlib.sha256(template.encode()).hexdigest()[:16],
        grouping_teacher='normalized_native_text_not_effect_interpretation')
    path=folder/'proposal.json'
    if not path.exists():write_json(path,proposal)
    if not (folder/'review.json').exists():
        write_json(folder/'review.json',dict(status='pending',approved=False,corrected_label=None,notes=''))
    (folder/'trace.log').write_text('Native trial reading queued; original effect remains unpriced.\n'
        +'Source: '+source['record']+'\nGift: '+offer.title+'\nText: '+offer.unpriced+'\n',encoding='utf-8')
    return dict(proposal=str(path),proposal_sha256=digest(path),training_eligible=False)
