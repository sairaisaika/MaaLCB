"""The view normalisation is part of the map branch, not a helper nobody calls (D292)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src' / 'maalimbus' / 'runner.py').read_text(encoding='utf-8')


def test_the_map_branch_normalises_the_view_before_it_asks_for_candidates():
    call = SOURCE.index('self._normalise_view_once(record)')
    candidates = SOURCE.index('frame, candidates = candidates_of(directory, record')
    assert call < candidates, 'a view normalised after the candidates are read changes nothing'


def test_normalisation_reuses_a_stable_map_but_rearms_after_a_battle(tmp_path):
    from maalimbus.runner import MirrorRunner, FakeDevice
    loop=MirrorRunner(FakeDevice(),directory=tmp_path,settings={})
    loop.state['view_normalised']=True
    assert loop._normalise_view_once({'scene':'MAP'}) is None
    assert loop.state['view_normalised'] is True
    loop._normalise_view_once({'scene':'BATTLE_HUD'})
    assert not loop.state.get('view_normalised')
    assert loop.device.clicks==[]


def test_observe_only_does_not_change_the_view_or_its_normalization_state(tmp_path):
    from maalimbus.runner import MirrorRunner, FakeDevice
    loop=MirrorRunner(FakeDevice(),directory=tmp_path,settings={'observe_only':True})
    loop.state['view_normalised']=True
    loop._normalise_view_once({'scene':'BATTLE_HUD'})
    assert loop.state['view_normalised'] is True and loop.device.clicks==[]


def test_the_event_says_what_the_view_did():
    body = SOURCE[SOURCE.index('def _normalise_view_once'):SOURCE.index('def _frame_and_record')]
    assert "note('view_normalised'" in body
    for key in ('centred', 'steps'):
        assert key in body, key


def test_the_normalisation_journals_what_it_could_read():
    body = SOURCE[SOURCE.index('def _normalise_view_once'):SOURCE.index('def _frame_and_record')]
    assert "note('map_view_probe'" in body
    assert 'record_party' in body and 'image_party' in body


def test_the_result_event_names_the_two_paths():
    body = SOURCE[SOURCE.index('def _normalise_view_once'):SOURCE.index('def _frame_and_record')]
    assert "scale_lost_party=bool(result.get('scale_lost_party'))" in body
    assert "zoomed=result.get('zoomed')" in body


def test_a_drag_is_followed_by_an_observation():
    body = SOURCE[SOURCE.index('def _normalise_view_once'):SOURCE.index('def _frame_and_record')]
    drag_at = body.index('def drag(dx, dy):')
    swipe_at = body.index('device.swipe(', drag_at)
    observe_at = body.index("refresh('view_drag')", swipe_at)
    assert swipe_at < observe_at, 'the observation must come after the gesture'
