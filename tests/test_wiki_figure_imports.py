"""Every edge of the Wiki's module dependency figure is a real import in the source.

Figure 2-2 says it is drawn "from measured imports". On 2026-11-23 five of its 29 edges
no longer held (the runner had stopped importing three of the modules it pointed at)
and one node was imported by nobody, while 83 commits had touched the drawn modules
since the page last changed. Nothing checked the figure, so nothing said so. This test
reads the figure in both languages and the import statements of the files it names.
"""
import ast
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (ROOT / 'src/maalimbus', ROOT / 'agent')
PAGES = {'zh_cn': ('docs/wiki/zh_cn/2-architecture.md', '### 图 2-2'),
         'en_us': ('docs/wiki/en_us/2-architecture.md', '### Figure 2-2')}


def figure(language):
    page, heading = PAGES[language]
    text = (ROOT / page).read_text(encoding='utf-8')
    block = re.search(r'```mermaid\n(.*?)```', text[text.index(heading):], re.S).group(1)
    nodes = {m.group(1): m.group(2) for m in re.finditer(r'^\s*(\w+)\["([^"]*)"\]', block, re.M)}
    edges = re.findall(r'^\s*(\w+)\s*-->\s*(\w+)\s*$', block, re.M)
    return nodes, edges


def files(label):
    """The source files a node label names; ``*_x.py`` names every file ending in ``_x.py``."""
    found = []
    for name in re.findall(r'(\*?[A-Za-z_]\w*)\.py', label):
        for directory in SOURCES:
            if name.startswith('*'):
                found += sorted(directory.glob('*' + name[1:] + '.py'))
            elif (directory / (name + '.py')).is_file():
                found.append(directory / (name + '.py'))
    return found


def imported(path):
    """Names of this package's modules that ``path`` imports, at any depth."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.ImportFrom):
            parts = [p for p in (node.module or '').split('.') if p and p != 'maalimbus']
            if node.level >= 1 or (node.module or '').split('.')[0] == 'maalimbus':
                names.update([parts[0]] if parts else [alias.name for alias in node.names])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                if parts[0] == 'maalimbus' and len(parts) > 1:
                    names.add(parts[1])
    return names


@pytest.mark.parametrize('language', sorted(PAGES))
def test_every_node_names_a_source_file(language):
    nodes, _ = figure(language)
    assert len(nodes) >= 25
    missing = {key: label for key, label in nodes.items() if not files(label)}
    assert not missing, missing


@pytest.mark.parametrize('language', sorted(PAGES))
def test_every_edge_is_an_import(language):
    nodes, edges = figure(language)
    assert len(edges) >= 30
    false = []
    for source, target in edges:
        wanted = {path.stem for path in files(nodes[target])}
        if not any(wanted & imported(path) for path in files(nodes[source])):
            false.append((source, target))
    assert not false, 'drawn but not imported: %s' % false


def test_both_languages_draw_the_same_graph():
    zh_nodes, zh_edges = figure('zh_cn')
    en_nodes, en_edges = figure('en_us')
    assert sorted(zh_nodes) == sorted(en_nodes) and sorted(zh_edges) == sorted(en_edges)
    assert {key: sorted(p.name for p in files(label)) for key, label in zh_nodes.items()} == \
        {key: sorted(p.name for p in files(label)) for key, label in en_nodes.items()}


@pytest.mark.parametrize('language', sorted(PAGES))
def test_every_drawn_module_is_used_by_another_or_draws_an_edge(language):
    nodes, edges = figure(language)
    touched = {name for edge in edges for name in edge}
    assert not sorted(set(nodes) - touched), 'nodes with no edge: %s' % sorted(set(nodes) - touched)
