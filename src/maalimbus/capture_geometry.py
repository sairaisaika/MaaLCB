"""Calibration analysis and capture coordinates, without page or input authority."""
CALIBRATION_SIZE=(1920,1080)
ANALYSIS_PROFILES=((1920,1080),(1280,720))


def frame_coordinates(values,size):
    """Convert the original calibration once; Maa alone converts to device pixels."""
    return tuple(round(v*s) for v,s in zip(values,(size[0]/1920,size[1]/1080)*2))


def calibration_coordinates(values,size):
    """Capture geometry into analysis coordinates; words/scores keep their owner."""
    return tuple(round(v*s) for v,s in zip(values,(1920/size[0],1080/size[1])*2))


def analysis_image(image):
    """An explicitly interpolated analysis view, never a replacement witness."""
    if image is None:return None
    height,width=image.shape[:2]
    if (width,height) not in ANALYSIS_PROFILES:return None
    if (width,height)==CALIBRATION_SIZE:return image
    import cv2
    return cv2.resize(image,CALIBRATION_SIZE,interpolation=cv2.INTER_CUBIC)
