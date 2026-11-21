"""Same-image native caption repair; a probe never grants page/input authority."""
import re
from .vision import Text,find,drive_menu_probe,DRIVE_MIRROR_BAND
from .native_gestures import frame_coordinates


def repair(run_recognition,image,records,locale):
    from maa.pipeline import JRecognitionType,JOCR
    size=(image.shape[1],image.shape[0])
    if not drive_menu_probe(records,locale,size):return records,[]
    output=list(records);proof=[]
    crops=[]
    if not find(records,locale['inferno'],(.70,.07,.99,.3),size):
        crops.append(('drive_inferno_caption',frame_coordinates((1594,184,232,76),size),locale['inferno'],.9,True))
    # Event variants move menu rows. Detect within the same band the classifier
    # and native MirrorDrive target already accept; a fixed y is not a control.
    left,top,right,bottom=DRIVE_MIRROR_BAND
    roi=(round(left*size[0]),round(top*size[1]),round((right-left)*size[0]),round((bottom-top)*size[1]))
    crops.append(('drive_mirror_caption',roi,locale['mirror_menu'],.9,False))
    for purpose,roi,pattern,threshold,only_rec in crops:
        detail=run_recognition(JRecognitionType.OCR,
            JOCR(roi=roi,only_rec=only_rec,expected=[pattern],threshold=threshold),image)
        found=[]
        for row in detail.filtered_results if detail is not None and detail.hit else []:
            if (not hasattr(row,'text') or row.score<threshold
                    or not re.search(pattern,row.text,re.I)):continue
            box=tuple(roi) if only_rec else tuple(getattr(row,'box',()) or ())
            if (len(box)!=4 or any(type(v) is not int for v in box)
                    or min(box[2:])<=0 or min(box[:2])<0
                    or box[0]+box[2]>size[0] or box[1]+box[3]>size[1]):continue
            token=Text(row.text,box,row.score)
            if not only_rec and not find([token],pattern,DRIVE_MIRROR_BAND,size,threshold):continue
            # only_rec uses its measured crop; detector results are native-image
            # boxes (verified on real old/new menus), never manually rescaled.
            output.append(token)
            found.append(dict(text=row.text,score=row.score,box=list(box)))
        proof.append(dict(purpose=purpose,roi=list(roi),only_rec=only_rec,
                          threshold=threshold,expected=pattern,results=found))
    return output,proof
