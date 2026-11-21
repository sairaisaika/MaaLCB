"""Native caption evidence stays separate from mandatory synthetic guards."""
import json
from pathlib import Path
from maalimbus import service_notice
from maalimbus.native_evidence import bound_frame
from maalimbus.vision import Text,classify

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence/runtime/client-update-20261119-023500/frame-0001.json'


def test_retained_native_client_update_is_foreground_without_navigation_authority():
    binding,record=bound_frame(SOURCE)
    notice=service_notice.from_record(record)
    assert notice['kind']=='client_update_required' and notice['complete']
    locale=json.loads((ROOT/'assets/resource/en/locale.json').read_bytes())
    assert classify([Text(r['text'],tuple(r['box']),r['score']) for r in record['ocr']],locale,record['size'])=='UNKNOWN_DIALOG'
    assert not service_notice.close_candidates(record)
