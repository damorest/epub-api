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


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Split *text* into lines that fit within *max_width* pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def generate(volume: int, title: str = "") -> bytes:
    """Return JPEG bytes for the cover of *volume* with the given *title*."""
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (WIDTH, HEIGHT), color=_BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Border
        for inset, border_width in ((15, 3), (25, 1)):
            draw.rectangle(
                [inset, inset, WIDTH - inset, HEIGHT - inset],
                outline=_ACCENT_COLOR,
                width=border_width,
            )

        font_title = _find_font(52)
        font_vol = _find_font(36)

        # Title — wrap long titles, center vertically in the upper half
        display_title = title or "Книга"
        lines = _wrap_text(display_title, font_title, WIDTH - 80, draw)
        line_h = font_title.getbbox("Ай")[3] + 14
        block_h = line_h * len(lines)
        y = (HEIGHT // 2 - block_h) // 2  # vertically center in top half
        for line in lines:
            _center_text(draw, line, font_title, y, _ACCENT_COLOR, WIDTH)
            y += line_h

        # Volume badge (bottom area)
        vol_text = f"Том {volume}" if volume > 0 else "Повне видання"
        _center_text(draw, vol_text, font_vol, HEIGHT - 160, _SUB_COLOR, WIDTH)

        # Thin divider above volume text
        draw.line([(80, HEIGHT - 185), (WIDTH - 80, HEIGHT - 185)],
                  fill=_ACCENT_COLOR, width=1)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    except Exception as exc:  # noqa: BLE001
        logger.warning("Cover generation failed (%s); using blank cover.", exc)
        from PIL import Image
        img = Image.new("RGB", (1, 1), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
