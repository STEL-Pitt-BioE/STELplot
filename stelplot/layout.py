"""Layout sheets: several graphs arranged in one figure with panel letters (A, B, C).

SVG layouts keep every graph as editable vector artwork for Illustrator. PNG and TIFF
layouts are 600 dpi images.
"""

__author__ = "Daniel Shiwarski"

import re
import string

POINTS_PER_INCH = 72.0


def panel_letter(i):
    letters = string.ascii_uppercase
    return letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26]


def arrange(sizes, ncols, gap, label_space):
    """Top-left positions for panels of the given (width, height), in rows of ncols."""
    positions, y, total_w = [], 0.0, 0.0
    for start in range(0, len(sizes), ncols):
        row = sizes[start:start + ncols]
        x = 0.0
        for w, _h in row:
            positions.append((x, y))
            x += w + gap
        total_w = max(total_w, x - gap)
        y += label_space + max(h for _w, h in row) + gap
    return positions, (total_w, max(y - gap, 0.0))


def _read_svg(path):
    text = open(path, encoding="utf-8").read()
    head = re.search(r"<svg\b[^>]*>", text)
    w = float(re.search(r'width="([\d.]+)pt"', head.group(0)).group(1))
    h = float(re.search(r'height="([\d.]+)pt"', head.group(0)).group(1))
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', head.group(0)).group(1).split()]
    body = text[head.end():text.rindex("</svg>")]
    body = re.sub(r"<metadata>.*?</metadata>", "", body, flags=re.S)
    return w, h, vb, body


def _prefix_ids(body, prefix):
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', body)
    body = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{prefix}{m.group(1)})", body)
    return re.sub(r'((?:xlink:)?href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{prefix}{m.group(2)}"', body)


def compose_svg(panel_paths, out_path, ncols=2, gap_in=0.25, letters=True, letter_size=10.0,
                font="Arial", author="", title="Layout"):
    """Arrange panel SVG files (from save_figure) into one SVG. Sizes in points."""
    panels = [_read_svg(p) for p in panel_paths]
    gap = gap_in * POINTS_PER_INCH
    label_space = letter_size * 1.4 if letters else 0.0
    positions, (W, H) = arrange([(w, h) for w, h, *_ in panels], max(1, ncols), gap, label_space)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{W:.2f}pt" height="{H:.2f}pt" viewBox="0 0 {W:.2f} {H:.2f}" version="1.1">',
           f"<title>{title}</title>", f"<desc>Author: {author}. Created with STELplot.</desc>"]
    for i, ((w, h, vb, body), (x, y)) in enumerate(zip(panels, positions)):
        sx, sy = w / vb[2], h / vb[3]
        out.append(f'<g id="panel_{panel_letter(i)}" transform="translate({x:.2f} {y + label_space:.2f}) '
                   f'scale({sx:.6f} {sy:.6f}) translate({-vb[0]:.2f} {-vb[1]:.2f})">')
        out.append(_prefix_ids(body, f"p{i}_"))
        out.append("</g>")
        if letters:
            out.append(f'<text x="{x:.2f}" y="{y + letter_size:.2f}" style="font-family: {font}; '
                       f'font-size: {letter_size:.1f}px; font-weight: bold">{panel_letter(i)}</text>')
    out.append("</svg>")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    return out_path, (W, H)


def compose_raster(panel_paths, out_path, ncols=2, gap_in=0.25, letters=True, letter_size=10.0,
                   dpi=600, white=True):
    """Arrange panel PNG files (rendered at `dpi`) into one PNG or TIFF image."""
    from matplotlib import font_manager
    from PIL import Image, ImageDraw, ImageFont

    from .lab_style import available_font
    images = [Image.open(p).convert("RGBA") for p in panel_paths]
    gap = gap_in * dpi
    letter_px = letter_size / POINTS_PER_INCH * dpi
    label_space = letter_px * 1.4 if letters else 0.0
    positions, (W, H) = arrange([im.size for im in images], max(1, ncols), gap, label_space)
    canvas = Image.new("RGBA", (int(round(W)), int(round(H))),
                       (255, 255, 255, 255) if white else (255, 255, 255, 0))
    for im, (x, y) in zip(images, positions):
        canvas.alpha_composite(im, (int(round(x)), int(round(y + label_space))))
    if letters:
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype(font_manager.findfont(
                font_manager.FontProperties(family=available_font(), weight="bold")), int(round(letter_px)))
        except OSError:
            font = ImageFont.load_default()
        for i, (x, y) in enumerate(positions):
            draw.text((x, y), panel_letter(i), fill=(0, 0, 0, 255), font=font)
    if out_path.lower().endswith((".tif", ".tiff")):
        canvas.convert("RGB").save(out_path, dpi=(dpi, dpi), compression="tiff_lzw")
    else:
        canvas.save(out_path, dpi=(dpi, dpi))
    return out_path, canvas.size
