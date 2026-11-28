"""Resolve the choices MXU saved for a task into the pipeline overrides it would apply.

Reads data only: no controller, no agent, no game. `tests/test_mxu_choices.py` runs it
against the maintained `assets/interface.json`, so an option whose cases write into
each other's nodes is caught without starting the GUI.

This function lived in `tools/verify_mxu_deployment_replay.py` until 2026-11-27. That
verifier replayed the `DeploymentStart` pipeline task, which was removed with the rest of
the pipeline-only Mirror layer; the resolver is the part still in use.
"""

#: Saved choices of cases that were removed from the interface, by option.
RETIRED_CASES={'mirror_star_source':('saved','auto')}     # removed 2026-11-27: the game keeps no selection


def resolve_choices(interface, task):
    """Select only active children, using exact stored case names."""
    spec=next((t for t in interface['task'] if t['name']==task['taskName']),None)
    if spec is None:raise ValueError('Saved task no longer exists in this interface')
    overrides={}
    def visit(name):
        value=task['optionValues'].get(name)
        if value is None:
            # A queue saved before this option existed names no value for it, and MXU
            # would have left the option's own default in place: replay that instead of
            # refusing a config the UI itself produced.
            default=interface['option'][name].get('default_case')
            if default is None:raise ValueError('Saved queue names no value for a required option')
            value={'type':'select','caseName':default}
        if value['type']!='select':raise ValueError('Expected fixed select option')
        case=next((c for c in interface['option'][name]['cases'] if c['name']==value['caseName']),None)
        if case is None and value['caseName'] in RETIRED_CASES.get(name,()):
            # A case the interface offered once and no longer does: MXU itself shows the
            # option's default for such a saved value (seen live for a removed order
            # choice), so the replay does the same. Only the cases named here; any other
            # unknown value is still refused before a controller exists.
            default=interface['option'][name].get('default_case')
            case=next((c for c in interface['option'][name]['cases'] if c['name']==default),None)
        if case is None:raise ValueError('Unknown saved option case')
        for node,params in case.get('pipeline_override',{}).items():
            if node in overrides:raise ValueError('Unexpected overlapping PI nodes')
            overrides[node]=params
        for child in case.get('option',[]):visit(child)
    for name in spec['option']:visit(name)
    return overrides
