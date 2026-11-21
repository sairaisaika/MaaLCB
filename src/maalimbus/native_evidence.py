"""Keep canonical Journal proof, without duplicate native debug screenshots."""
from pathlib import Path
import hashlib
import json
import re

from .runtime_contracts import FrameRef


def journal_scope(rows):
    """One explicit recording scope, without treating absence as a null fact.

    Legacy starts can omit run_scope while a later semantic proposal supplies
    episode. Present null/empty/malformed or conflicting facts still reject the
    recording. This binds diagnostic ownership, never business/input authority.
    """
    values=set()
    for row in rows:
        if not isinstance(row,dict):return None
        event=row.get('event')
        if not isinstance(event,str):return None
        key={'mirror_loop_start':'run_scope','semantic_frame_proposal':'episode'}.get(event)
        if key is None or key not in row:continue
        value=row[key]
        if not isinstance(value,str) or not value.strip():return None
        values.add(value)
    return next(iter(values)) if len(values)==1 else None


def bound_frame(path):
    """Read original Journal bytes and image binding; no page/outcome inference."""
    path=Path(path);body=path.read_bytes();record=json.loads(body);png=path.with_suffix('.png')
    if path.is_symlink() or png.is_symlink():raise ValueError('Linked native proof')
    from .native_image_archive import verified_png
    image=verified_png(png)
    if (not isinstance(record,dict) or image is None
            or record.get('size')!=list(image.size)
            or image.sha256!=record.get('image_sha256')):
        raise ValueError('Native capture image binding differs')
    return dict(record=path.name,json_sha256=hashlib.sha256(body).hexdigest(),
                png_sha256=record['image_sha256']),record


def frame_reference(path):
    """Bind one named canonical pair using the existing native byte verifier."""
    path=Path(path)
    if not re.fullmatch(r'frame-\d+',path.stem) or path.suffix!='.json':
        raise ValueError('Native frame reference requires its canonical JSON name')
    binding,record=bound_frame(path)
    if record.get('frame') not in (None,'',path.stem,path.name,path.stem+'.png'):
        raise ValueError('Native record frame id conflicts with its file name')
    return FrameRef(path.stem,str(path.resolve()),record.get('utc'),
                    binding['json_sha256'],binding['png_sha256'],tuple(record['size'])),record


def observation_frame(directory,event):
    """Complete native metadata from that event's own pair, never latest files.

    Page hypotheses and domain controls stay with their semantic producer. This
    binding owns only original capture identity/OCR provenance, not game success.
    """
    if not isinstance(event,dict):raise ValueError('Native observation must be a record')
    name=event.get('frame')
    if not isinstance(name,str) or '/' in name or '\\' in name:
        raise ValueError('Native observation has no canonical frame id')
    stem=Path(name).stem
    if not re.fullmatch(r'frame-\d+',stem) or Path(name).suffix not in ('','.json','.png'):
        raise ValueError('Native observation has no canonical frame id')
    reference,raw=frame_reference(Path(directory)/(stem+'.json'))
    if event.get('image_sha256') not in (None,'',reference.png_sha256):
        raise ValueError('Native observation image hash conflicts with its named frame')
    if event.get('size') is not None and list(event['size'])!=list(reference.size):
        raise ValueError('Native observation dimensions conflict with its named frame')
    for key in ('ocr','local_ocr'):
        if event.get(key) and event[key]!=raw.get(key):
            raise ValueError('Native observation '+key+' conflicts with its named frame')
    encoded=reference.as_dict()
    if event.get('frame_ref') is not None and event['frame_ref']!=encoded:
        raise ValueError('Native observation FrameRef conflicts with its original bytes')
    completed=dict(event,frame=reference.frame_id,image_sha256=reference.png_sha256,
                   size=list(reference.size),frame_ref=encoded)
    for key in ('ocr','local_ocr'):
        if key in raw:completed[key]=raw[key]
    return completed,reference,raw


def configure_host(directory, *, tasker_api=None, toolkit_api=None, library_api=None):
    """Configure the controlling process, after library load and before tasks.

    Native failed recognition probes can save several full-size copies per
    observation. Journal owns the actual proof pair and its hashes. Text logs
    remain enabled; disabling native draw/error copies does not disable Journal,
    recognition, input intents or learning candidates. AgentServer is not the
    controlling host and must not claim to have changed MXU's configuration.
    """
    if library_api is None:
        from maa.library import Library
        library_api=Library
    if library_api.is_agent_server():
        raise ValueError('Configure native debug images in the controlling host')
    if tasker_api is None:
        from maa.tasker import Tasker
        tasker_api=Tasker
    if toolkit_api is None:
        from maa.toolkit import Toolkit
        toolkit_api=Toolkit
    directory=Path(directory)
    if not toolkit_api.init_option(directory):
        raise RuntimeError('Native host logging configuration failed')
    for name in ('set_save_draw','set_save_on_error','set_debug_mode'):
        if not getattr(tasker_api,name)(False):
            raise RuntimeError('Native host refused '+name)
    return dict(native_debug_images=False,canonical_journal_enabled=True,
                native_text_logs=True,configuration_owner='controller_host')
