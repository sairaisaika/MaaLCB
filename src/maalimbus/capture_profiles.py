"""Optional battle-read sizing; native page owners still decide every input.

Only a fresh bound HUD with readable counters/controls opts into the smaller
profile. Every insufficient small read gets an independent full read before
returning to the planner. Neither a prior page nor this policy grants input.
"""
from .battle_vision import auto_assign_buttons,battle_hud
from .native_evidence import observation_frame
from .vision import Text
from .capture_geometry import CALIBRATION_SIZE


class BattleCaptureObserver:
    # A small before-image may be followed by a full-resolution fallback.
    successor_size=CALIBRATION_SIZE
    def __init__(self, observer, controller, *, note=None):
        self.observer=observer
        self.controller=controller
        self.directory=observer.directory
        self.note=note or (lambda *args,**kwargs:None)
        self.current=None
        self.small_ready=False
        self.enabled=True

    @property
    def tasker(self):
        return self.observer.tasker

    @property
    def requires_frame_ref(self):
        return getattr(self.observer,'requires_frame_ref',False)

    @property
    def last_image(self):
        return self.observer.last_image

    @last_image.setter
    def last_image(self,value):
        self.observer.last_image=value

    def _set(self, side, *, force=False):
        if self.current==side and not force:return True
        accepted=self.controller.set_screenshot_target_long_side(side)
        self.note('capture_profile_requested',requested_long_side=side,
                  accepted=accepted is True,input_sent=False)
        if accepted is True:self.current=side
        return accepted is True

    def _identity(self, event):
        try:
            completed,reference,record=observation_frame(self.directory,event)
        except (OSError,ValueError,KeyError,TypeError):
            return None,'capture_binding_unavailable'
        event.update(completed)
        from pathlib import Path
        return (reference,record,Path(reference.record_path)),'bound'

    def _ready(self, event, identity):
        if not identity:return False
        _,raw,_=identity
        if (event.get('scene')!='BATTLE_HUD' or raw.get('scene')!='BATTLE_HUD'
                or event.get('battle_read')=='unreadable'
                or raw.get('size') not in ([1280,720],[1920,1080])):
            return False
        try:
            texts=[Text(t['text'],tuple(t['box']),t['score']) for t in raw.get('ocr',[])]
            hud=battle_hud(texts,raw['size'])
        except (KeyError,TypeError,ValueError,AttributeError):return False
        if (not hud or hud.get('detail_panel')
                or (hud.get('turn') is None and event.get('turn') is None)):return False
        # Native captions, not positional assignment defaults, qualify the read.
        if auto_assign_buttons(texts,raw['size'],positional=False):return True
        box=event.get('start_box')
        return bool(isinstance(box,(tuple,list)) and len(box)==4
                    and all(type(v) in (int,float) for v in box)
                    and box[0]>=0 and box[1]>=0 and min(box[2:])>0
                    and box[0]+box[2]<=raw['size'][0] and box[1]+box[3]<=raw['size'][1])

    def observe(self, *, deadline=None, battle_hint=None):
        from .runner import observe
        if not self.enabled:
            return observe(self.observer,deadline=deadline,battle_hint=battle_hint)
        side=1280 if self.enabled and self.small_ready else 1920
        if not self._set(side):
            self.enabled=False
            self.small_ready=False
            if side==1280:self._set(1920,force=True)
            side=1920
        first=observe(self.observer,deadline=deadline,battle_hint=battle_hint)
        identity,why=self._identity(first)
        ready=self._ready(first,identity)
        actual=identity[1].get('size') if identity else None
        if identity is None or actual!=[side,side*9//16]:
            # An optional optimization cannot replace the page owner's refusal
            # policy. A rejected/ineffective option disables further downsizing.
            self.enabled=False
        if side==1280 and not ready:
            self.small_ready=False
            self._set(1920,force=True)
            # Reuse the caller's original absolute deadline; never restart it.
            second=observe(self.observer,deadline=deadline,battle_hint=None)
            second_identity,second_why=self._identity(second)
            if second_identity is None or second_identity[1].get('size')!=[1920,1080]:
                from .runner import ReadNeverReturned
                raise ReadNeverReturned('independent full capture profile not proven')
            self.small_ready=self.enabled and self._ready(second,second_identity)
            self.note('capture_profile_full_reread',
                      before_record=str(identity[2]) if identity else None,
                      before_image_sha256=identity[1]['image_sha256'] if identity else None,
                      after_record=str(second_identity[2]) if second_identity else None,
                      after_image_sha256=second_identity[1]['image_sha256'] if second_identity else None,
                      low_read_status=why,full_read_status=second_why,input_sent=False)
            return second
        self.small_ready=self.enabled and ready
        return first
