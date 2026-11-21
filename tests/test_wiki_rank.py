"""Precise intent must survive a broad route's many overlapping aliases."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('wiki_rank',Path(__file__).resolve().parents[1]/
    'tools/wiki_router.py')
router=importlib.util.module_from_spec(spec);spec.loader.exec_module(router)


def test_exact_phrase_beats_broad_alias_accumulation():
    rows=[dict(id='battle',title='battle teacher',aliases=['pre','battle','identity','teacher']*8),
          dict(id='sinner-caption-teacher',title='Independent captions',aliases=['pre battle identity teacher'])]
    ranked=router.rank(' PRE BATTLE IDENTITY TEACHER ',rows)
    assert ranked[0]['id']=='sinner-caption-teacher'
    assert ranked[0]['match_kind']=='exact_alias'
    assert ranked[1]['match_kind']=='related'


def test_unknown_intent_does_not_suggest_an_unrelated_route():
    assert router.rank('unrelated', [dict(id='battle',title='Combat',aliases=[])])==[]


def test_exact_route_id_is_stable_among_token_matches():
    rows=[dict(id='generic',title='slot order',aliases=['slot','order']*10),
          dict(id='slot-order',title='Saved deployment',aliases=[])]
    assert router.rank('slot-order',rows)[0]['id']=='slot-order'
