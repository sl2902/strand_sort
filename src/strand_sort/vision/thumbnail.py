"""Small, dedicated resize-only thumbnail generation for card/list display.

Deliberately separate from vision/clean.py's clean_image() pipeline, which
does background removal and cropping for a different purpose (OCR
legibility) and has its own failure modes (GrabCut assumptions that don't
hold for every real photo). This function does nothing but resize —
no cropping, no background removal.
"""

from io import BytesIO

from PIL import Image

THUMBNAIL_MAX_DIMENSION = 400  # pixels, longer edge


def generate_thumbnail(image_bytes: bytes, max_dimension: int = THUMBNAIL_MAX_DIMENSION) -> bytes:
    """Resizes an image so its longer edge is at most max_dimension,
    preserving aspect ratio. No cropping, no background removal."""
    img = Image.open(BytesIO(image_bytes))
    img.thumbnail((max_dimension, max_dimension))  # in-place, preserves aspect ratio
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")  # JPEG doesn't support alpha/palette modes
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
