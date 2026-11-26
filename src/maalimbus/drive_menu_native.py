"""Same-image native caption repair; a probe never grants page/input authority."""
import re
from .vision import Text,find,drive_menu_probe,DRIVE_MIRROR_BAND
from .native_gestures import frame_coordinates


#: The 2026-11-26 client update redrew the Mirror Dungeons card: its title is now a
#: glowing caption over a banner, and neither the full-frame read nor the band read
#: finds it at the frame's own scale (live pi-20261126-023925: HOME -> Drive -> a page
#: nobody could name, five times, then `the_same_plan_repeated`). Read alone and
#: enlarged, the same pixels give 'Dungeons' at .999. So when the band read comes back
#: empty the band is cut into overlapping slices, each enlarged by a whole factor and
#: read by the same detector; a hit's box is carried back by that exact factor.
MAGNIFY=4
#: Slice height and step as shares of the frame's height: about one card, half a card.
SLICE,STEP=170/1080,85/1080


def magnified(run_recognition,image,roi,pattern,threshold,band):
    """Captions the band shows only when enlarged, as ``(Text, slice record)`` pairs.

    Same image, no second screenshot: every slice is a crop of `image`, pasted enlarged
    onto a blank frame of the image's own size. A box comes back in the enlarged frame
    and is divided by `MAGNIFY` and offset by the slice's corner, which is arithmetic on
    known integers, not a guess at a scale. A box that does not land inside `band`
    after that is dropped.
    """
    import cv2
    import numpy as np
    from maa.pipeline import JRecognitionType,JOCR
    height,width=image.shape[:2];left,top,wide,tall=roi
    slice_tall=max(1,round(SLICE*height));step=max(1,round(STEP*height))
    if wide*MAGNIFY>width or slice_tall*MAGNIFY>height:return []
    found=[];seen=set()
    for offset in range(0,max(1,tall-slice_tall+1),step):
        crop=image[top+offset:top+offset+slice_tall,left:left+wide]
        big=cv2.resize(crop,None,fx=MAGNIFY,fy=MAGNIFY,interpolation=cv2.INTER_CUBIC)
        canvas=np.zeros_like(image);canvas[:big.shape[0],:big.shape[1]]=big
        detail=run_recognition(JRecognitionType.OCR,
            JOCR(roi=(0,0,big.shape[1],big.shape[0]),only_rec=False,expected=[pattern],threshold=threshold),canvas)
        for row in detail.filtered_results if detail is not None and detail.hit else []:
            box=tuple(getattr(row,'box',()) or ())
            if (not hasattr(row,'text') or row.score<threshold or not re.search(pattern,row.text,re.I)
                    or len(box)!=4 or any(type(v) is not int for v in box) or min(box[2:])<=0 or min(box[:2])<0
                    or box[0]+box[2]>big.shape[1] or box[1]+box[3]>big.shape[0]):continue
            native=(left+box[0]//MAGNIFY,top+offset+box[1]//MAGNIFY,
                    max(1,box[2]//MAGNIFY),max(1,box[3]//MAGNIFY))
            token=Text(row.text,native,row.score)
            if native in seen or not find([token],pattern,band,(width,height),threshold):continue
            seen.add(native)
            found.append((token,dict(text=row.text,score=row.score,box=list(native),
                                     slice=[left,top+offset,wide,slice_tall],magnify=MAGNIFY)))
    return found


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
        if purpose=='drive_mirror_caption' and not found and not find(records,pattern,DRIVE_MIRROR_BAND,size):
            # Nothing at the frame's own scale, from either read: look again, enlarged.
            enlarged=magnified(run_recognition,image,roi,pattern,threshold,DRIVE_MIRROR_BAND)
            output.extend(token for token,_ in enlarged)
            proof.append(dict(purpose='drive_mirror_caption_magnified',roi=list(roi),only_rec=False,
                              threshold=threshold,expected=pattern,results=[row for _,row in enlarged]))
    return output,proof
