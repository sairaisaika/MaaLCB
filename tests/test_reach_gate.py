"""一格可达性：两格外的目标不能进入候选（D427）。"""
import pathlib

SOURCE = (pathlib.Path(__file__).resolve().parents[1]
          / 'src' / 'maalimbus' / 'runner.py')


def test_the_gate_uses_a_measured_segment_or_falls_back_to_the_frame_side():
    source = SOURCE.read_text(encoding='utf-8')
    assert "self.note('map_candidates_too_far'" in source
    assert "(record.get('map_connected_step') or {}).get('step')" in source
    assert 'or _side_hint)' in source
    assert '0.55 * _pitch_hint <= dist <= 1.75 * _pitch_hint' in source


def test_the_side_comes_from_the_candidates_not_a_constant():
    source = SOURCE.read_text(encoding='utf-8')
    assert '_side_hint = _sides[len(_sides) // 2]' in source
    assert 'int(box[2]) > 100' in source


def test_an_empty_result_replaces_the_unfiltered_list():
    source = SOURCE.read_text(encoding='utf-8')
    assert "if len(_kept) != len(candidates):" in source
    assert "if _kept and len(_kept) != len(candidates):" not in source
