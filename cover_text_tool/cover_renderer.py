from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass(frozen=True)
class CoverOptions:
    title: str
    subtitle: str = ""
    badge: str = ""
    position: str = "bottom"
    align: str = "left"
    style: str = "gradient"
    text_color: str = "#FFFFFF"
    accent_color: str = "#FFD166"
    title_size_percent: float = 8.0
    output_format: str = "png"
    font_path: str | None = None


def render_cover(input_path: Path, output_path: Path, options: CoverOptions) -> None:
    image = Image.open(input_path)
    image = ImageOps.exif_transpose(image).convert("RGBA")
    width, height = image.size

    title_size = _clamp(int(width * options.title_size_percent / 100), 30, 180)
    title_font = _fit_title_font(image, options, title_size)
    subtitle_font = _load_font(options.font_path, max(18, int(title_font.size * 0.42)))
    badge_font = _load_font(options.font_path, max(16, int(title_font.size * 0.32)))

    draw = ImageDraw.Draw(image)
    max_text_width = int(width * 0.84)
    title_lines = _wrap_text(draw, options.title.strip(), title_font, max_text_width, _stroke_for(title_font))
    subtitle_lines = _wrap_text(draw, options.subtitle.strip(), subtitle_font, max_text_width, _stroke_for(subtitle_font))

    layout = _measure_layout(
        draw,
        width,
        height,
        title_lines,
        subtitle_lines,
        options.badge.strip(),
        title_font,
        subtitle_font,
        badge_font,
        options,
    )

    if options.style == "gradient":
        image = _apply_readability_gradient(image, layout["band"], options.position)
        draw = ImageDraw.Draw(image)
    elif options.style == "panel":
        _draw_panel(draw, layout["panel_box"], width)

    _draw_text_block(
        draw,
        layout,
        title_lines,
        subtitle_lines,
        options.badge.strip(),
        title_font,
        subtitle_font,
        badge_font,
        options,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if options.output_format == "jpg":
        image.convert("RGB").save(output_path, quality=94, optimize=True)
    else:
        image.save(output_path, optimize=True)


def default_font_path() -> str | None:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\SourceHanSansSC-Bold.otf",
        r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _fit_title_font(image: Image.Image, options: CoverOptions, starting_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    draw = ImageDraw.Draw(image)
    max_width = int(image.width * 0.84)
    max_height = int(image.height * 0.42)
    size = starting_size
    while size >= 24:
        font = _load_font(options.font_path, size)
        lines = _wrap_text(draw, options.title.strip(), font, max_width, _stroke_for(font))
        line_height = _line_height(draw, font, _stroke_for(font))
        block_height = len(lines) * line_height + max(0, len(lines) - 1) * int(size * 0.12)
        if len(lines) <= 4 and block_height <= max_height:
            return font
        size -= 4
    return _load_font(options.font_path, 24)


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    chosen_font = font_path or default_font_path()
    if chosen_font:
        try:
            return ImageFont.truetype(chosen_font, size=size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    stroke_width: int,
) -> list[str]:
    if not text:
        return []

    lines: list[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue

        tokens = _tokenize(paragraph)
        current = ""
        for token in tokens:
            candidate = f"{current}{token}" if current else token.strip()
            if not candidate:
                continue
            if _text_width(draw, candidate, font, stroke_width) <= max_width:
                current = candidate
                continue

            if current:
                lines.append(current.rstrip())
                current = ""

            if _text_width(draw, token, font, stroke_width) <= max_width:
                current = token.strip()
            else:
                current = _split_long_token(draw, token, font, max_width, stroke_width, lines)

        if current:
            lines.append(current.rstrip())
    return lines


def _tokenize(text: str) -> list[str]:
    if re.search(r"\s", text):
        return re.findall(r"\S+\s*", text)
    return list(text)


def _split_long_token(
    draw: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    stroke_width: int,
    lines: list[str],
) -> str:
    current = ""
    for char in token:
        candidate = f"{current}{char}"
        if _text_width(draw, candidate, font, stroke_width) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
    return current


def _measure_layout(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    title_lines: list[str],
    subtitle_lines: list[str],
    badge: str,
    title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    subtitle_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    badge_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    options: CoverOptions,
) -> dict[str, object]:
    title_stroke = _stroke_for(title_font)
    subtitle_stroke = _stroke_for(subtitle_font)
    max_text_width = int(width * 0.84)
    margin_x = int(width * 0.08)
    margin_y = int(height * 0.08)
    title_line_height = _line_height(draw, title_font, title_stroke)
    subtitle_line_height = _line_height(draw, subtitle_font, subtitle_stroke)
    title_gap = max(6, int(title_font.size * 0.12))
    subtitle_gap = max(10, int(title_font.size * 0.22))
    badge_gap = max(12, int(title_font.size * 0.24))

    badge_height = 0
    badge_width = 0
    if badge:
        badge_box = draw.textbbox((0, 0), badge, font=badge_font)
        badge_width = badge_box[2] - badge_box[0] + int(badge_font.size * 1.3)
        badge_height = badge_box[3] - badge_box[1] + int(badge_font.size * 0.7)

    title_height = len(title_lines) * title_line_height + max(0, len(title_lines) - 1) * title_gap
    subtitle_height = len(subtitle_lines) * subtitle_line_height + max(0, len(subtitle_lines) - 1) * int(subtitle_font.size * 0.18)
    block_height = title_height + subtitle_height
    if badge:
        block_height += badge_height + badge_gap
    if title_lines and subtitle_lines:
        block_height += subtitle_gap

    if options.position == "top":
        y = margin_y
    elif options.position == "center":
        y = int((height - block_height) / 2)
    else:
        y = height - block_height - margin_y

    max_line_width = max(
        [_text_width(draw, line, title_font, title_stroke) for line in title_lines]
        + [_text_width(draw, line, subtitle_font, subtitle_stroke) for line in subtitle_lines]
        + [badge_width, 1]
    )

    if options.align == "center":
        x = int((width - max_text_width) / 2)
    elif options.align == "right":
        x = width - margin_x - max_text_width
    else:
        x = margin_x

    padding_x = max(18, int(width * 0.035))
    padding_y = max(14, int(height * 0.025))
    panel_box = (
        max(0, x - padding_x),
        max(0, y - padding_y),
        min(width, x + max(max_line_width, badge_width) + padding_x),
        min(height, y + block_height + padding_y),
    )

    if options.position == "top":
        band = (0, 0, width, min(height, panel_box[3] + int(height * 0.12)))
    elif options.position == "center":
        band = (0, max(0, panel_box[1] - int(height * 0.08)), width, min(height, panel_box[3] + int(height * 0.08)))
    else:
        band = (0, max(0, panel_box[1] - int(height * 0.12)), width, height)

    return {
        "x": x,
        "y": max(0, y),
        "max_text_width": max_text_width,
        "title_line_height": title_line_height,
        "subtitle_line_height": subtitle_line_height,
        "title_gap": title_gap,
        "subtitle_gap": subtitle_gap,
        "badge_gap": badge_gap,
        "badge_height": badge_height,
        "badge_width": badge_width,
        "panel_box": panel_box,
        "band": band,
    }


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    layout: dict[str, object],
    title_lines: list[str],
    subtitle_lines: list[str],
    badge: str,
    title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    subtitle_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    badge_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    options: CoverOptions,
) -> None:
    x = int(layout["x"])
    y = int(layout["y"])
    max_text_width = int(layout["max_text_width"])

    if badge:
        badge_width = int(layout["badge_width"])
        badge_height = int(layout["badge_height"])
        badge_x = _aligned_x(draw, badge, badge_font, x, max_text_width, options.align, 0, badge_width)
        radius = badge_height // 2
        draw.rounded_rectangle(
            (badge_x, y, badge_x + badge_width, y + badge_height),
            radius=radius,
            fill=_hex_to_rgba(options.accent_color, 235),
        )
        badge_box = draw.textbbox((0, 0), badge, font=badge_font)
        badge_text_x = badge_x + (badge_width - (badge_box[2] - badge_box[0])) / 2
        badge_text_y = y + (badge_height - (badge_box[3] - badge_box[1])) / 2 - badge_box[1]
        draw.text((badge_text_x, badge_text_y), badge, font=badge_font, fill=(18, 18, 18, 255))
        y += badge_height + int(layout["badge_gap"])

    title_stroke = _stroke_for(title_font)
    title_fill = _hex_to_rgba(options.text_color, 255)
    for line in title_lines:
        line_x = _aligned_x(draw, line, title_font, x, max_text_width, options.align, title_stroke)
        draw.text(
            (line_x, y),
            line,
            font=title_font,
            fill=title_fill,
            stroke_width=title_stroke,
            stroke_fill=(0, 0, 0, 190),
        )
        y += int(layout["title_line_height"]) + int(layout["title_gap"])

    if title_lines and subtitle_lines:
        y += int(layout["subtitle_gap"]) - int(layout["title_gap"])

    subtitle_stroke = _stroke_for(subtitle_font)
    for line in subtitle_lines:
        line_x = _aligned_x(draw, line, subtitle_font, x, max_text_width, options.align, subtitle_stroke)
        draw.text(
            (line_x, y),
            line,
            font=subtitle_font,
            fill=_hex_to_rgba(options.text_color, 230),
            stroke_width=subtitle_stroke,
            stroke_fill=(0, 0, 0, 170),
        )
        y += int(layout["subtitle_line_height"]) + max(4, int(subtitle_font.size * 0.18))


def _draw_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], width: int) -> None:
    radius = max(16, int(width * 0.018))
    draw.rounded_rectangle(box, radius=radius, fill=(0, 0, 0, 118))


def _apply_readability_gradient(image: Image.Image, band: tuple[int, int, int, int], position: str) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pixels = overlay.load()
    _, top, _, bottom = band
    band_height = max(1, bottom - top)
    for y in range(top, bottom):
        t = (y - top) / band_height
        if position == "top":
            alpha = int(160 * (1 - t))
        elif position == "center":
            alpha = int(120 * math.sin(math.pi * t))
        else:
            alpha = int(165 * t)
        for x in range(image.width):
            pixels[x, y] = (0, 0, 0, alpha)
    return Image.alpha_composite(image, overlay)


def _aligned_x(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    max_width: int,
    align: str,
    stroke_width: int,
    fixed_width: int | None = None,
) -> int:
    text_width = fixed_width or _text_width(draw, text, font, stroke_width)
    if align == "center":
        return int(x + (max_width - text_width) / 2)
    if align == "right":
        return int(x + max_width - text_width)
    return x


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, stroke_width: int) -> int:
    bbox = draw.textbbox((0, 0), "国Ag", font=font, stroke_width=stroke_width)
    return max(1, bbox[3] - bbox[1])


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    stroke_width: int,
) -> int:
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0]


def _stroke_for(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    size = getattr(font, "size", 32)
    return max(2, int(size * 0.055))


def _hex_to_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "FFFFFF"
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red, green, blue, alpha


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
