"""Write a value into the settings the player sees in the MXU window.

A task can read something the settings should then show: the deployment order printed on
the game's team screen is the first. The stock MXU client has no option that runs code
and no way for a task to fill a field in, but it does serve its own configuration on the
loopback address when its web service is on (``GET`` and ``PUT /api/config``; a ``PUT``
saves the file, updates the running program and tells every open window to load it
again -- read from MXU 2.7.1's ``web_server.rs`` at the pinned commit). The window and
the page in a browser use the same door, so this is the client's own mechanism, not a
change to it.

Only the option values named by the caller are changed; everything else in the
configuration is sent back exactly as it was received. Nothing is written when the web
service is off or does not answer: the caller is told and shows the player the text to
paste instead. The address is always the loopback one and the request carries nothing
but the configuration it just received.

The user asked for this on 2026-11-27, after a version that kept the reading in a file
of its own and offered "use the record" in the settings: the order belongs where the
order is set, where it can be seen, edited and removed.
"""
import json
from pathlib import Path
import urllib.error
import urllib.request

from .storage import SINNERS

#: Names a player reads in the settings, in roster order, by interface language.
NAMES = {'zh': ('李箱', '浮士德', '堂吉诃德', '良秀', '默尔索', '鸿璐', '希斯克利夫', '以实玛利', '罗佳', '辛克莱', '奥提斯', '格里高尔'),
         'en': tuple(sinner.replace(' ', '') for sinner in SINNERS)}
TIMEOUT = 8


def service(config_directory):
    """``(port, language)`` of the running client's web service, or ``(None, language)``.

    Read from the client's own saved configuration; a service that is switched off there
    is not looked for.
    """
    for path in sorted(Path(config_directory).glob('mxu-*.json')):
        try:
            settings = json.loads(path.read_text(encoding='utf-8')).get('settings') or {}
        except (OSError, ValueError):
            continue
        language = 'zh' if str(settings.get('language') or '').lower().startswith('zh') else 'en'
        port = settings.get('webServerPort')
        if settings.get('webServerEnabled') is True and type(port) is int and 1024 <= port <= 65535:
            return port, language
        return None, language
    return None, 'zh'


def order_text(positions, picked=12, language='zh'):
    """The order as the settings' own input line: names, first to deploy first.

    `positions[i]` is the roster number of the sinner in deployment place ``i + 1``.
    A team that is not full lists only the sinners the game numbered; the settings put
    the rest after them in roster order by themselves (`global_settings.parse_order`).
    """
    names = NAMES.get(language, NAMES['en'])
    return ' '.join(names[position - 1] for position in list(positions)[:picked])


def _ask(port, method='GET', body=None):
    request = urllib.request.Request('http://127.0.0.1:%d/api/config' % port, method=method,
                                     data=None if body is None else json.dumps(body).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8'))


def write_orders(config_directory, orders, *, ask=_ask):
    """Put each team's order into its "deployment order" setting; returns what happened.

    `orders` maps a team number to its input line. The team's order choice becomes
    "write the whole order" and the line becomes that order's text, which is what the
    player would have typed. Returns ``dict(written=[slots], reason)``.
    """
    port, _language = service(config_directory)
    if port is None:
        return dict(written=[], reason='mxu_web_service_is_off')
    try:
        config = ask(port)
        values = config.get('globalOptionValues') if isinstance(config, dict) else None
        if not isinstance(values, dict) or not isinstance(config.get('instances'), list):
            return dict(written=[], reason='mxu_configuration_not_recognised')
        written = []
        for slot, text in sorted(orders.items()):
            if type(slot) is not int or not 1 <= slot <= 40 or not isinstance(text, str) or not text.strip():
                raise ValueError('A team order needs a team number 1..40 and a line of names')
            values['global_team_%d_order' % slot] = dict(type='select', caseName='custom')
            values['global_team_%d_order_text' % slot] = dict(type='input', values=dict(order=text))
            written.append(slot)
        if written:
            answer = ask(port, 'PUT', config)
            if not (isinstance(answer, dict) and answer.get('ok') is True):
                return dict(written=[], reason='mxu_refused_the_configuration')
        return dict(written=written, reason='mxu_settings_written')
    except (OSError, urllib.error.URLError, ValueError) as error:
        return dict(written=[], reason='mxu_web_service_did_not_answer', error=str(error))
