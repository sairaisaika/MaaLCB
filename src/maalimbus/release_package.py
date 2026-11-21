"""Export updater-compatible assets from an already verified public package."""
import json
from pathlib import Path
import zipfile

from .local_assets import packaged_game_assets
from .update_install import metadata, plain_tree
from .update_stage import verify_package, file_digest, StageError


def export_assets(app, destination):
    app, destination = Path(app), Path(destination)
    plain_tree(app)
    count = verify_package(app)
    identity = metadata(app)
    info = json.loads((app / 'build-info.json').read_text(encoding='utf-8'))
    if info.get('source_dirty') is not False:
        raise StageError('Release candidate requires a clean source revision')
    for name in ('launcher/MaaLimbusLauncher.exe', 'sources/MaaLimbus-source.zip',
                 'sources/MXU-v2.7.1-source.zip', 'sources/MaaFramework-v5.12.2-source.zip'):
        if not (app / name).is_file():
            raise StageError('Missing launcher or corresponding source')
    # Inspect the nested project source too; a clean outer manifest does not
    # establish that its source archive omitted runtime state.
    with zipfile.ZipFile(app / 'sources/MaaLimbus-source.zip') as source:
        for name in source.namelist():
            parts = name.replace('\\', '/').split('/')
            if parts[0].casefold() in ('config', 'evidence', 'build', 'logs', 'dist'):
                raise StageError('Private state in corresponding source archive')
    # Game artwork is supplied locally and is never published. A package folder assembled
    # on a machine that holds the bitmaps would carry them out, so refuse it here, at the
    # last step before an archive exists.
    carried = packaged_game_assets(app)
    if carried:
        raise StageError('Release package carries %d game asset file(s), first %s; game artwork is '
                         'supplied locally and never published' % (len(carried), carried[0]))
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / f'MaaLimbus-win-x64-{identity["version"]}.zip'
    # The manifest is checked immediately before export; include every public
    # member, including the manifest itself, with installation-relative paths.
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as output:
        for file in sorted(app.rglob('*')):
            if file.is_file():
                output.write(file, file.relative_to(app).as_posix())
    digest = file_digest(archive)
    sums = destination / 'SHA256SUMS'
    # Bytes, not text: on Windows write_text turns the newline into CRLF, and then
    # `sha256sum -c` looks for a file whose name ends in a carriage return.
    sums.write_bytes(f'{digest}  {archive.name}\n'.encode('ascii'))
    return dict(archive=str(archive), checksum=str(sums), sha256=digest,
                version=identity['version'], source_commit=info.get('source_commit'),
                files=count, published=False)
