

def _header(text, box):
    from maalimbus.vision import Text
    return Text(text=text, box=box, score=.99)


def test_a_compound_keyword_takes_the_first_column_the_page_offers():
    """A charge+tremor team must not stall just because its keyword names two systems."""
    from maalimbus.initial_gifts import group_target
    size = (1920, 1080)
    records = [_header('Bleed', (300, 240, 64, 32)),
               _header('Tremor', (700, 240, 90, 32))]
    assert group_target(records, size, 'charge+tremor') is not None, (
        'the page has no Charge column, so Tremor is the team\'s column here')
    assert group_target(records, size, 'charge') is None
    assert group_target(records, size, 'tremor') == group_target(records, size, 'charge+tremor')


def initial_page_records(y):
    return [_header(name,(x,y,75,30)) for name,x in
            [('Sinking',288),('Poise',512),('Charge',728)]] + [
        _header('Selected E.G.O Gift',(1176,220,330,42)),
        _header('Refuse Gift',(1256,865,150,28)),
        _header('0/2',(1678,847,74,60))]


def test_initial_catalogue_remains_identifiable_after_preview_scroll():
    from maalimbus.initial_gifts import page
    locale={'initial_selected':r'^Selected E\.G\.O Gift$',
            'initial_refuse':r'^Refuse Gift$'}
    assert page(initial_page_records(545),(1920,1080),locale)
    assert page(initial_page_records(258),(1920,1080),locale)


def test_partial_or_scattered_catalogue_headers_do_not_name_the_page():
    from maalimbus.initial_gifts import page
    locale={'initial_selected':r'^Selected E\.G\.O Gift$',
            'initial_refuse':r'^Refuse Gift$'}
    rows=initial_page_records(258)
    assert not page(rows[1:],(1920,1080),locale)
    assert not page(rows[:-1],(1920,1080),locale)
    assert not page(rows[:-2]+rows[-1:],(1920,1080),locale)
    assert not page([rows[0],_header('Poise',(512,545,75,30))]+rows[2:],(1920,1080),locale)
    assert not page(rows+[_header('Charge',(728,300,75,30))],(1920,1080),locale)
