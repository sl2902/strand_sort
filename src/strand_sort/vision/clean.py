# vision/clean.py
import cv2
import numpy as np
from loguru import logger


def _load_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image — unsupported format or corrupt data")
    return img


def _encode_image(img: np.ndarray, format: str = ".jpg") -> bytes:
    success, buf = cv2.imencode(format, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not success:
        raise ValueError("Failed to encode cleaned image")
    return buf.tobytes()


def remove_background(img: np.ndarray, iterations: int = 5) -> np.ndarray:
    """
    Separates the foreground object from its background using GrabCut,
    replacing the background with white. Assumes the subject roughly
    fills the center of the frame — starts from a rectangle inset from
    the image edges rather than trying to auto-detect the object first
    """
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    # Inset rectangle: assumes the subject isn't touching the frame edges.
    margin_x, margin_y = int(w * 0.05), int(h * 0.05)
    rect = (margin_x, margin_y, w - 2 * margin_x, h - 2 * margin_y)

    try:
        cv2.grabCut(img, mask, rect, bgd_model, fgd_model, iterations, cv2.GC_INIT_WITH_RECT)
    except cv2.error as e:
        logger.warning(f"GrabCut failed, returning original image uncropped: {e}")
        return img

    # Keep definite + probable foreground pixels
    binary_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype("uint8")

    # If GrabCut collapsed to near-nothing (bad init), bail out rather than
    # return an almost-blank image.
    if binary_mask.sum() < 0.02 * h * w:
        logger.warning("GrabCut foreground mask too small — skipping background removal")
        return img

    white_bg = np.full_like(img, 255)
    result = img * binary_mask[:, :, None] + white_bg * (1 - binary_mask[:, :, None])
    return result.astype("uint8")


def crop_to_subject(img: np.ndarray, padding_ratio: float = 0.08) -> np.ndarray:
    """
    Crops tightly to the non-white region of the image (expects
    remove_background to have run first). Falls back to the original
    image if no clear subject region is found
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        logger.warning("No subject contour found — skipping crop")
        return img

    x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
    pad_x, pad_y = int(w * padding_ratio), int(h * padding_ratio)
    img_h, img_w = img.shape[:2]

    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(img_w, x + w + pad_x), min(img_h, y + h + pad_y)

    return img[y0:y1, x0:x1]


def normalize_size(img: np.ndarray, target: int = 1024) -> np.ndarray:
    """
    Resizes so the longer side equals `target`, then pads to a square
    canvas — keeps aspect ratio intact rather than distorting the subject
    """
    h, w = img.shape[:2]
    scale = target / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    canvas = np.full((target, target, 3), 255, dtype=np.uint8)
    y_off, x_off = (target - new_h) // 2, (target - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return canvas


def clean_image(image_bytes: bytes, target_size: int = 1024) -> bytes:
    """Full pipeline: decode -> remove background -> crop -> normalize -> encode"""
    img = _load_image(image_bytes)
    img = remove_background(img)
    img = crop_to_subject(img)
    img = normalize_size(img, target=target_size)
    return _encode_image(img)