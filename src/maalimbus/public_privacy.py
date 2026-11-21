"""Fail public exports on local user paths and literal player identifiers.

Reports contain file/line/category only. Images and Git history still need review.
"""
import ipaddress
import re
TEXT={'.md','.py','.json','.jsonl','.toml','.txt','.ps1','.yml','.yaml','.js','.ts','.tsx','.rs','.html',
      '.ini','.conf','.cfg','.xml','.cmd','.bat','.sh','.env'}
PATTERNS={
    'local_user_path':re.compile(r'(?i)[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b|<|%|\$)[^\\/\s"\x27]+'),
    'player_id_literal':re.compile(r'(?i)(?:\buser[_ -]?id|\buid|玩家(?:编号|ID)|好友(?:代码|ID))["\x27]?\s*[:=]\s*["\x27]?[A-Z]?\d{7,}'),
    'credential_literal':re.compile(
        r'(?<![\w-])(?:gh[opurs]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}'
        r'|sk-proj-[A-Za-z0-9_\-]{25,})(?![\w-])'),
}

DEVICE_FIELD=re.compile(
    r'(?i)\b(adb[_-]?serial|device[_-]?(?:uuid|id)|android[_-]?id|'
    r'hardware[_-]?id|mac[_-]?address|(?:mumu|device|adb)[_-]?(?:ip|host|address))'
    r'["\x27]?\s*[:=]\s*(?:["\x27]([^"\x27\r\n]+)["\x27]|'
    r'([0-9a-f.:\[\]-]+)(?=[,;\s]|$))')
MAC_LITERAL=re.compile(r'(?i)(?<![0-9a-f])[0-9a-f]{2}([:-])(?:[0-9a-f]{2}\1){4}[0-9a-f]{2}(?![0-9a-f])')
DOCUMENTATION_NETWORKS=tuple(ipaddress.ip_network(value) for value in (
    '192.0.2.0/24','198.51.100.0/24','203.0.113.0/24','2001:db8::/32'))


def device_identifier(line):
    for match in DEVICE_FIELD.finditer(line):
        key = re.sub(r'[_-]', '', match[1]).lower()
        value = (match[2] or match[3]).strip()
        if (not value or value.startswith(('<', '$', '%')) or value.lower().startswith(
                ('fake-', 'test-', 'unit-test-', 'mock-', 'synthetic-', 'example-')) or
                value.lower() in ('auto', 'default', 'localhost', 'none', 'unknown')):
            continue
        endpoint = value
        if endpoint.startswith('[') and ']' in endpoint:
            endpoint = endpoint[1:endpoint.index(']')]
        elif endpoint.count(':') == 1 and endpoint.rsplit(':',1)[1].isdigit():
            endpoint = endpoint.rsplit(':',1)[0]
            if endpoint.lower() == 'localhost':
                continue
        try:
            address = ipaddress.ip_address(endpoint)
        except ValueError:
            if key.endswith(('ip','host','address')) and key != 'macaddress':
                continue
            if len(value) < 5:
                continue
        else:
            if address.is_loopback or address.is_unspecified or any(
                    address in network for network in DOCUMENTATION_NETWORKS):
                continue
        return True
    return False

def public_member(path):
    return ('__pycache__' not in path.parts and path.suffix.lower() not in {
                '.pyc', '.log', '.jsonl', '.pem', '.key', '.pfx', '.p12', '.ppk'}
            and not path.name.lower().endswith('.local.json')
            and path.name.lower() != '.env' and not path.name.lower().startswith('.env.'))


def public_file(path):
    return path.is_file() and not path.is_symlink() and public_member(path)


def text_findings(name, content):
    """Report categories and line numbers without reproducing matched values."""
    if isinstance(content, bytes):
        encoding='utf-16' if content.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
        content=content.decode(encoding,errors='replace')
    result = []
    for number,line in enumerate(content.splitlines(),1):
        for category,pattern in PATTERNS.items():
            if pattern.search(line):result.append(dict(file=name,line=number,category=category))
        if device_identifier(line) or MAC_LITERAL.search(line):
            result.append(dict(file=name,line=number,category='device_identifier'))
    return result

def findings(paths):
    result=[]
    for path in paths:
        if path.suffix.lower() not in TEXT:continue
        result.extend(text_findings(path.as_posix(),path.read_bytes()))
    return result

def reject_findings(issues):
    if issues:
        # Never embed the matched identifier or an absolute home path in errors.
        first=issues[0]
        raise ValueError('Public privacy gate: %s in %s line %d (%d findings)'%
                         (first['category'],first['file'].split('/')[-1],first['line'],len(issues)))


def require_public(paths):
    paths=list(paths)
    reject_findings(findings(paths))
    return paths
