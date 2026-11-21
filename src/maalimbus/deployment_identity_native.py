"""Independent title-line reads for the measured pre-battle card layout."""
import unicodedata

import cv2
from maa.pipeline import JOCR, JRecognitionType

from .pre_battle_identity import DEPLOYMENT_SIZES, card_box


_THREE_LINE_CROPS = (
    ((192, 30, 2), (218, 24, 3.2), (234, 29, 2)),
    ((195, 27, 3), (220, 22, 2.5), (235, 26, 3)),
)


def _letters(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())


def read_frontline_titles(native, image, slots, aliases):
    """Require two complete, agreeing title reads and one full catalogue match."""
    if image is None or image.shape[1::-1] not in DEPLOYMENT_SIZES:
        return [],[]
    source_size = (image.shape[1], image.shape[0])
    if source_size != DEPLOYMENT_SIZES[0]:
        image = cv2.resize(image, DEPLOYMENT_SIZES[0], interpolation=cv2.INTER_CUBIC)
    catalogue = {}
    for alias in aliases:
        catalogue.setdefault(_letters(alias['title']), {})[alias['identity_id']] = alias
    found, evidence = [],[]
    for slot in slots:
        x,y,width,_ = card_box(slot)
        paths = []
        for layout in _THREE_LINE_CROPS:
            readings = []
            for offset,height,scale in layout:
                roi = (x+5, y+offset, width-10, height)
                crop = image[roi[1]:roi[1]+height,roi[0]:roi[0]+roi[2]]
                expanded = cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                detail = native(JRecognitionType.OCR,JOCR(only_rec=True,threshold=.9),expanded)
                rows = detail.filtered_results if detail is not None and detail.hit else []
                if len(rows)!=1 or rows[0].score<.9 or not _letters(rows[0].text):
                    break
                readings.append(dict(text=rows[0].text,score=rows[0].score,roi=roi,scale=scale))
            if len(readings)!=len(layout):
                break
            paths.append(readings)
        if len(paths)!=2 or [_letters(row['text']) for row in paths[0]] != [_letters(row['text']) for row in paths[1]]:
            continue
        title = ' '.join(row['text'] for row in paths[0])
        matches = catalogue.get(_letters(title), {})
        if len(matches)!=1:
            continue
        identity = next(iter(matches.values()))
        found.append(dict(grid_slot=slot,caption=title,identity_id=identity['identity_id'],
                          sinner=identity['sinner'],sinner_index=identity['sinner_index'],method='exact_caption_crops'))
        evidence.append(dict(grid_slot=slot,paths=paths,source_size=source_size,
                             roi_size=DEPLOYMENT_SIZES[0]))
    return found,evidence
