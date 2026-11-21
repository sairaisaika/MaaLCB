"""Native caption geometry from the aborted-entry offer; no account identifiers."""
import json
from pathlib import Path
from maalimbus.vision import Text,classify

LOCALE=json.loads((Path(__file__).resolve().parents[1]/'assets/resource/en/locale.json').read_text(encoding='utf8'))


def modal():
    return [Text('Exploration Reward',(790,158,340,42),.999),
            Text('To List',(904,817,112,36),.989),Text('Claim',(1248,817,88,36),1.0),
            Text('GiveUpRewards',(452,815,276,40),.98),
            Text('Enter',(1606,716,112,48),1.0),Text('Exploring:',(1354,214,104,34),.993)]


def test_lower_modal_button_strip_is_not_the_background_mirror_entry():
    assert classify(modal(),LOCALE,(1920,1080))=='RUN_REWARD_DIALOG'


def test_partially_read_reward_modal_never_exposes_background_entry_controls():
    rows=[t for t in modal() if t.text!='Claim']
    assert classify(rows,LOCALE,(1920,1080))=='UNKNOWN_DIALOG'
    rows=[Text(t.text,t.box,.7) if t.text=='Claim' else t for t in modal()]
    assert classify(rows,LOCALE,(1920,1080))=='UNKNOWN_DIALOG'


def test_unknown_nested_reward_confirmation_hides_the_claim_strip():
    rows=modal()+[Text('Confirm',(1108,718,124,36),1),Text('Cancel',(706,714,154,42),.99)]
    assert classify(rows,LOCALE,(1920,1080))=='UNKNOWN_DIALOG'
