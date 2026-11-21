"""Optional video plugin removal must not weaken the Maa image runtime."""
from pathlib import Path
import json
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from frozen_image_bundle import trim_image_bundle,static_imports


def candidate(tmp_path):
    bundle=tmp_path/'dist/MaaLimbusAgent';cv=bundle/'_internal/cv2';cv.mkdir(parents=True)
    plugin=cv/'opencv_videoio_ffmpeg4110_64.dll';plugin.write_bytes(b'optional-video')
    core=cv/'cv2.pyd';core.write_bytes(b'image-core')
    source=tmp_path/'source';(source/'agent').mkdir(parents=True);(source/'src').mkdir()
    (source/'agent/main.py').write_text('import cv2\ncv2.imread("frame.png")\n')
    return bundle,source,plugin,core


def test_image_profile_keeps_core_and_records_original_optional_binary(tmp_path):
    bundle,source,plugin,core=candidate(tmp_path);before=core.read_bytes()
    result=trim_image_bundle(bundle,'MaaLimbusAgent',source,imports=lambda p:set())
    assert not plugin.exists() and core.read_bytes()==before
    assert result['excluded'][0]['bytes']==len(b'optional-video')
    assert json.loads((bundle/'_internal/image-runtime-profile.json').read_text())['profile']=='maa_screenshots_and_images'


@pytest.mark.parametrize('video',['cv2.VideoCapture("x")','from cv2 import VideoCapture as reader'])
def test_future_video_feature_requires_full_profile_before_any_deletion(tmp_path,video):
    bundle,source,plugin,core=candidate(tmp_path)
    (source/'agent/main.py').write_text(video)
    with pytest.raises(ValueError,match='Video APIs'):trim_image_bundle(bundle,'MaaLimbusAgent',source,imports=lambda p:set())
    assert plugin.exists() and core.exists()


def test_native_import_cannot_be_removed_even_when_source_does_not_name_it(tmp_path):
    bundle,source,plugin,core=candidate(tmp_path)
    with pytest.raises(ValueError,match='native dependency'):
        trim_image_bundle(bundle,'MaaLimbusAgent',source,imports=lambda p:{plugin.name.casefold()})
    assert plugin.exists()


def test_installed_component_and_other_executables_are_not_trim_targets(tmp_path):
    bundle,source,plugin,core=candidate(tmp_path)
    assert trim_image_bundle(bundle,'MaaLimbusLauncher',source,imports=lambda p:set()) is None
    installed=tmp_path/'agent';bundle.rename(installed)
    with pytest.raises(ValueError,match='generated frozen candidate'):
        trim_image_bundle(installed,'MaaLimbusAgent',source,imports=lambda p:set())
    assert (installed/'_internal/cv2'/plugin.name).exists()


def test_actual_installed_opencv_image_extension_does_not_statically_import_ffmpeg():
    core=ROOT/'dist/MaaLimbus/agent/_internal/cv2/cv2.pyd'
    if not core.exists():pytest.skip('local Windows installed image runtime absent')
    assert not any('ffmpeg' in name for name in static_imports(core))
