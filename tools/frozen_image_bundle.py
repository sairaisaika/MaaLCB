"""Keep the frozen Agent's image runtime without an unused video-file plugin."""
import ast
import hashlib
import json
from pathlib import Path
import re


def video_calls(root):
    found=[]
    for base in ('src','agent'):
        for path in (Path(root)/base).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf8'))):
                if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                        and node.func.attr in ('VideoCapture','VideoWriter')):
                    found.append(path.relative_to(root).as_posix())
                if (isinstance(node,ast.ImportFrom) and node.module=='cv2'
                        and any(x.name in ('VideoCapture','VideoWriter') for x in node.names)):
                    found.append(path.relative_to(root).as_posix())
    return found


def static_imports(path):
    import pefile
    with pefile.PE(str(path),fast_load=True) as pe:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        return {entry.dll.decode('ascii').casefold() for field in (
            'DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT')
            for entry in getattr(pe,field,())}


def trim_image_bundle(bundle,name,root,*,imports=static_imports):
    """Only a generated candidate is changed; installation keeps its rollback.

    Maa screenshots, PNG, template matching and neural images use image APIs.
    OpenCV's optional FFmpeg VideoCapture/Writer backend is separate. Refuse
    trimming if source calls those APIs or a bundled PE imports that backend.
    """
    if name!='MaaLimbusAgent':return None
    from maalimbus.update_install import plain_path,plain_tree
    bundle=plain_path(bundle);plain_tree(bundle)
    if bundle.name!=name or bundle.parent.name!='dist':
        raise ValueError('Expected a generated frozen candidate, not an installed component')
    cv2dir=bundle/'_internal/cv2'
    optional=[p for p in cv2dir.glob('opencv_videoio_ffmpeg*.dll')
              if re.fullmatch(r'opencv_videoio_ffmpeg\d+_64\.dll',p.name)]
    if video_calls(root):raise ValueError('Video APIs require the full OpenCV runtime profile')
    blocked={p.name.casefold() for p in optional}
    for path in bundle.rglob('*'):
        if path.is_file() and path.suffix.casefold() in ('.dll','.pyd') and path not in optional:
            if imports(path)&blocked:raise ValueError('Optional video backend is a native dependency')
    rows=[]
    for path in optional:
        if path.is_symlink() or path.resolve().parent!=cv2dir:
            raise ValueError('Video backend outside generated image runtime')
        rows.append(dict(path=path.relative_to(bundle).as_posix(),bytes=path.stat().st_size,
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result=dict(version=1,profile='maa_screenshots_and_images',excluded=rows,
                video_file_io=False,native_imports_checked=True,
                required=('PNG encode/decode','resize','template matching','native Maa screenshots'))
    for path in optional:path.unlink()
    (bundle/'_internal/image-runtime-profile.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result
