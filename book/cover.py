"""Generates a simple placeholder cover image as JPEG bytes."""

import io
import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)

_BG_COLOR = (18, 18, 54)
_ACCENT_COLOR = (200, 160, 90)
_TEXT_COLOR = (230, 210, 170)
_SUB_COLOR = (160, 170, 210)
WIDTH, HEIGHT = 600, 900


def _find_font(size: int):
    """Return a PIL ImageFont that supports Cyrillic, falling back to default."""
    from PIL import ImageFont

    candidates: list[str] = []
    sys = platform.system()

    if sys == "Darwin":
        candidates = [
            "/Library/Fonts/Arial Unicode MS.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    elif sys == "Linux":
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    elif sys == "Windows":
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue

    return ImageFont.load_default()


def _center_text(draw, text: str, font, y: int, color: tuple, width: int) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, fill=color, font=font)


def generate(volume: int) -> bytes:
    """Return JPEG bytes for the cover of *volume*."""
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (WIDTH, HEIGHT), color=_BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Border
        for inset, width in ((15, 3), (25, 1)):
            draw.rectangle(
                [inset, inset, WIDTH - inset, HEIGHT - inset],
                outline=_ACCENT_COLOR,
                width=width,
            )

        font_title = _find_font(52)
        font_sub = _find_font(38)
        font_vol = _find_font(34)

        _center_text(draw, "Звільнити", font_title, 220, _ACCENT_COLOR, WIDTH)
        _center_text(draw, "цю відьму", font_title, 290, _ACCENT_COLOR, WIDTH)
        _center_text(draw, "Release That Witch", font_sub, 390, _TEXT_COLOR, WIDTH)
        _center_text(draw, f"Том {volume}", font_vol, 700, _SUB_COLOR, WIDTH)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    except Exception as exc:  # noqa: BLE001
        logger.warning("Cover generation failed (%s); using blank cover.", exc)
        # Return a 1×1 white pixel JPEG as fallback
        from PIL import Image
        img = Image.new("RGB", (1, 1), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
