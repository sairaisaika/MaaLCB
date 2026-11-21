"""Detect digits in the anchored Available header; keep independent reads."""
import re
from .vision import Text, find
from .grace_vision import AVAILABLE_LABEL
from .native_gestures import frame_coordinates


def repair(run, image, records):
    from maa.pipeline import JRecognitionType, JOCR
    size=(image.shape[1],image.shape[0])
    readings=[];proof=[]
    if size not in ((1920,1080),(1280,720)):return records,proof
    if len(find(records,AVAILABLE_LABEL,(.70,.02,.80,.10),size,.85))!=1:
        # A reduced full-frame read can omit the final e (actual modal0010).
        # That fragment only requests a new native label read; it cannot stand
        # in for the exact label or authorize the following numeric reads.
        fragments=find(records,r'^Ava[l1i]{1,3}ab[l1i]$',(.70,.02,.80,.10),size,.9)
        if len(fragments)!=1:return records,proof
        roi=frame_coordinates((1360,40,145,54),size)
        detail=run(JRecognitionType.OCR,JOCR(roi=roi,only_rec=True,
            expected=[AVAILABLE_LABEL],threshold=.85),image)
        if detail is None:raise RuntimeError('Maa Available label OCR returned no evidence')
        found=[]
        if detail.hit:
            found=[dict(text=r.text,score=r.score,box=list(roi)) for r in detail.filtered_results
                   if r.score>=.85 and re.fullmatch(AVAILABLE_LABEL,r.text,re.I)]
        proof.append(dict(purpose='available_starlight_label',roi=list(roi),only_rec=True,results=found))
        if len(found)!=1:return records,proof
        records=list(records)+[Text(found[0]['text'],roi,found[0]['score'])]
    # Recognition-only stretched a 75 to a low-confidence token in actual
    # pi-20261014-053727/frame-0012. Detect text inside the numeric band first.
    # Both crops exclude Owned at the left and the shop coin counter at right.
    for calibrated in ((1505,40,92,50),(1510,45,80,40)):
        roi=frame_coordinates(calibrated,size)
        detail=run(JRecognitionType.OCR,JOCR(roi=roi,only_rec=False,
            expected=[r'^\d{1,5}$'],threshold=.85),image)
        if detail is None:raise RuntimeError('Maa Available balance OCR returned no evidence')
        found=[]
        if detail.hit:
            for item in detail.filtered_results:
                if item.score>=.85 and re.fullmatch(r'\d{1,5}',item.text):
                    found.append(dict(text=item.text,score=item.score,box=list(roi)))
        proof.append(dict(purpose='available_starlight_detected',roi=list(roi),only_rec=False,results=found))
        readings.append(found)
    # Never erase a contrary full-frame read or replace it with an assumed delta.
    if all(len(row)==1 for row in readings):
        records=list(records)+[Text(row[0]['text'],tuple(row[0]['box']),row[0]['score']) for row in readings]
    return records,proof
