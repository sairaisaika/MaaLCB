"""Nothing ahead on the map, twice: the party's own node is offered once.

A battle the session left before it ended is still owed, and the game takes it back in by
a press on the node the party stands on. The reader only looks ahead of the party. Live
`pi-20261126-213041`: the sixth run had been cut off in a floor-1 battle, was resumed on
the map with the party at (939, 447), read three frames with no destination and stopped
with `no_candidate_node_observed`. The same happened on a floor-5 boss on 2026-11-24 and
was pressed by hand then.
"""
from maalimbus.run_wiring import OWN_NODE_AFTER_EMPTY_READS, own_node_offer

PARTY, SIDE = (939, 447), 192


def test_the_second_empty_read_offers_the_node_under_the_party_and_only_once():
    state = {}
    assert own_node_offer(state, PARTY, SIDE, []) is None          # one empty read may be a fade
    box = own_node_offer(state, PARTY, SIDE, [])
    assert state['map_empty_offers'] == OWN_NODE_AFTER_EMPTY_READS and state['map_own_node_tried']
    # A small box centred on the party, inside the node it stands on.
    assert box == [939 - 32, 447 - 32, 64, 64]
    assert own_node_offer(state, PARTY, SIDE, []) is None           # not pressed again and again
    assert own_node_offer(state, PARTY, SIDE, []) is None


def test_a_map_that_offers_a_destination_again_clears_the_memory():
    state = {}
    own_node_offer(state, PARTY, SIDE, [])
    own_node_offer(state, PARTY, SIDE, [])
    assert own_node_offer(state, PARTY, SIDE, [[100, 100, 192, 192]]) is None
    assert state == dict(map_empty_offers=0, map_own_node_tried=False)
    assert own_node_offer(state, PARTY, SIDE, []) is None
    assert own_node_offer(state, PARTY, SIDE, []) is not None      # a later interrupted battle is owed too


def test_without_a_party_nothing_is_offered_and_without_a_ruler_the_box_is_the_smallest():
    state = {}
    for _ in range(4):
        assert own_node_offer(state, None, SIDE, []) is None
    assert not state.get('map_own_node_tried')
    for side in (None, 0, 192.0):
        state = {}
        own_node_offer(state, PARTY, side, [])
        assert own_node_offer(state, PARTY, side, []) == [939 - 16, 447 - 16, 32, 32]
