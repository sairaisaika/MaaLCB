"""A known service foreground owns Close, never the background run's controls."""
from .vision import Text,find

TITLE=r'^Server\s+is\s+under\s+Scheduled\s+Maintenance\.?$'
RESUME=r'^You\s+will\s+be\s+able\s+to\s+log\s*in\s+after\s+((?:[01]?\d|2[0-3]):[0-5]\d)\s*\(KST\)\.?$'


#: The dialog a session gets when the server will not take its next request: live
#: pi-20261125-195746, 01:00 UTC on a Thursday, a run two minutes old. The maintenance
#: notice came first and its one owned Close was pressed; this dialog followed, over the
#: gift search page, which the reader then named as if nothing were in front of it.
SHUTDOWN_TITLE=r'^Cannot\s+operate\s+the\s+game\.?$'
SHUTDOWN_LINE=r'^Shutting\s+down\s+now\.?$'
#: A notice that ends the invocation with no input at all, and the reason it ends with.
STOP_REASONS={'client_update_required':'game_client_update_required',
              'session_shutdown':'the_game_says_it_cannot_be_operated_and_is_shutting_down',
              'restart_for_download':'the_game_asks_to_be_restarted_to_download_an_update'}


#: Pressed for after a run was claimed (live packaged-mirror-20261126-042150, 11:08 UTC):
#: the next request to the server answered with this dialog over the main menu, the
#: reader named the menu behind it, and Drive was pressed under it twice before the run
#: ended as `unexpected_successor`.
DOWNLOAD_TITLE=r'^A\s+new\s+download\s+has\s+been\s+added\.?$'
DOWNLOAD_LINES=(r'^The\s+game\s+will\s+be\s+closed;?\s+please\s+restart\s+the$',
                r'^game\s+to\s+download\s+the\s+update\.?$')


def restart_for_download(records,size):
    title=find(records,DOWNLOAD_TITLE,(.30,.39,.70,.48),size,.9)
    if not title:return None
    lines=[find(records,pattern,(.30,.43,.70,.56),size,.9) for pattern in DOWNLOAD_LINES]
    confirm=find(records,r'^[^A-Za-z]{0,2}\s*Confirm$',(.40,.62,.60,.74),size,.9)
    # Its Confirm closes the client so that it can download on the next start. Closing
    # the game and taking a download are the player's call, so nothing is pressed.
    return dict(kind='restart_for_download',
                complete=len(title)==len(confirm)==1 and all(len(found)==1 for found in lines),
                title=title[0].text,instruction=' '.join(found[0].text for found in lines if len(found)==1) or None,
                close_box=list(confirm[0].box) if len(confirm)==1 else None)


def session_shutdown(records,size):
    title=find(records,SHUTDOWN_TITLE,(.30,.39,.70,.53),size,.9)
    if not title:return None
    line=find(records,SHUTDOWN_LINE,(.30,.43,.70,.56),size,.9)
    close=find(records,r'^Close$',(.40,.58,.60,.73),size,.9)
    # Its Close shuts the client down. Nothing here grants it: the notice only says
    # who owns the foreground, and the run underneath is kept as it is.
    return dict(kind='session_shutdown',complete=len(title)==len(line)==len(close)==1,
                title=title[0].text,instruction=line[0].text if len(line)==1 else None,
                close_box=list(close[0].box) if len(close)==1 else None)


def scheduled_maintenance(records,size):
    title=find(records,TITLE,(.30,.39,.70,.53),size,.9)
    if not title:return None
    resume=find(records,RESUME,(.30,.45,.70,.56),size,.9)
    close=find(records,r'^Close$',(.40,.60,.60,.73),size,.9)
    # Even an incomplete known notice vetoes the underlying Enter. An absent or
    # ambiguous time/control is neither a new deadline nor permission to dismiss.
    complete=len(title)==len(resume)==len(close)==1
    return dict(kind='scheduled_maintenance',complete=complete,
                title=title[0].text,resume_text=resume[0].text if len(resume)==1 else None,
                close_box=list(close[0].box) if len(close)==1 else None)


def from_record(record):
    size=record.get('size')
    if not size or len(size)!=2:return None
    records=[Text(r['text'],tuple(r['box']),r['score']) for r in record.get('ocr') or []]
    return known_service_notice(records,size)


def known_service_notice(records,size):
    """Foreground ownership is separate from permission to dismiss a notice."""
    title=find(records,r'^Game\s+client\s+is\s+not\s+up\s+to\s+date\.?$',(.25,.30,.75,.55),size,.9)
    if title:
        instruction=find(records,r'^Please\s+update\s+to\s+the\s+latest\s+version\.?$',(.25,.35,.75,.58),size,.9)
        close=find(records,r'^Close$',(.30,.58,.50,.73),size,.9)
        store=find(records,r'^Go\s+to\s+Store$',(.50,.58,.70,.73),size,.9)
        return dict(kind='client_update_required',complete=len(title)==len(instruction)==len(close)==len(store)==1,
            title=title[0].text,instruction=instruction[0].text if len(instruction)==1 else None,
            close_box=list(close[0].box) if len(close)==1 else None,
            store_box=list(store[0].box) if len(store)==1 else None)
    return (restart_for_download(records,size) or session_shutdown(records,size)
            or scheduled_maintenance(records,size))


def close_candidates(record,frame=None):
    notice=from_record(record)
    if not notice or notice['kind']!='scheduled_maintenance' or not notice['complete']:return []
    return [dict(kind='service_notice_close',action='click',box=notice['close_box'],
                 teacher='native_exact_maintenance_title_time_and_close',score=.9)]


def dismissed_successor(record,page):
    """A fresh named page proves only dismissal, not server or run availability."""
    if record.get('scene')!=page or page not in ('HOME','TITLE','DRIVE','MIRROR_ENTRY'):
        return False
    size=record.get('size')
    if not size or len(size)!=2:return False
    rows=[Text(r['text'],tuple(r['box']),r['score']) for r in record.get('ocr') or []]
    # Weak/partial captions veto success; they never grant a click. A missed
    # title with the same central Close must not turn into the visible background.
    return not (from_record(record)
        or find(rows,r'Scheduled\s+Maintenance|login\s+after|Cannot\s+operate|Shutting\s+down',(.25,.30,.75,.60),size,.5)
        or find(rows,r'^Close$',(.40,.60,.60,.73),size,.5))
