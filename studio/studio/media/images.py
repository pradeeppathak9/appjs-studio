"""Validation and clean-up of uploaded images."""

import hashlib
import io
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps

FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}


class ImageTooLarge(Exception):
    pass


class InvalidImage(Exception):
    pass


@dataclass
class CleanImage:
    data: bytes
    mime_type: str
    ext: str
    width: int
    height: int
    sha256: str


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    """Read in chunks and stop as soon as the limit is passed."""
    buf = bytearray()
    while chunk := await upload.read(64 * 1024):
        buf += chunk
        if len(buf) > max_bytes:
            raise ImageTooLarge(f"file is larger than {max_bytes // (1024 * 1024)} MB")
    return bytes(buf)


def normalize_image(data: bytes, *, max_pixels: int, max_side: int) -> CleanImage:
    """Check the bytes really are PNG/JPEG/WebP, apply EXIF orientation, drop metadata
    (GPS, camera), and downscale so the long side is at most max_side."""
    if not data:
        raise InvalidImage("empty file")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            w, h = probe.size
            probe.verify()
    except Image.DecompressionBombError as e:
        raise InvalidImage("image has too many pixels") from e
    except Exception as e:
        raise InvalidImage("not a readable image") from e
    if fmt not in FORMATS:
        raise InvalidImage("only PNG, JPEG and WebP images are accepted")
    if w * h > max_pixels:
        raise InvalidImage(f"image has more than {max_pixels // 1_000_000} megapixels")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            if fmt == "JPEG":
                img.convert("RGB").save(out, "JPEG", quality=95, optimize=True)
            elif fmt == "WEBP":
                img.save(out, "WEBP", quality=95)
            else:
                img.save(out, "PNG", optimize=True)
            width, height = img.size
    except Exception as e:
        raise InvalidImage("image could not be decoded") from e

    clean = out.getvalue()
    mime, ext = FORMATS[fmt]
    return CleanImage(clean, mime, ext, width, height, hashlib.sha256(clean).hexdigest())


def image_size(data: bytes) -> tuple[int, int] | None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Exception:
        return None
