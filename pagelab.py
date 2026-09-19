"""Page image analysis for PDF OCR Extractor.

Everything that looks at pixels lives here: rendering, furniture and stamp
removal, template-matched exclusions, ruled-table geometry, emphasis
measurement, column detection and figure extraction.
"""

import re

import numpy as np
import pymupdf
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_edt, find_objects, label

INK = 200  # anything darker than this counts as ink
GLYPH = 160  # tighter threshold for measuring glyph strokes


# ------------------------------------------------------------------ rendering


def page_count(pdf_path):
    doc = pymupdf.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def render_pages(pdf_path, dpi, only=None):
    """Render pages to RGB arrays at the requested DPI.

    Rendering rather than extracting embedded images means pages holding
    several images, or a mix of image and vector content, still work. `only`
    renders a single page, which is what the parallel workers ask for.
    """
    doc = pymupdf.open(pdf_path)
    pages = [doc[only]] if only is not None else doc
    out = []
    for page in pages:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        out.append(np.asarray(img).astype(int))
    doc.close()
    if not out:
        raise SystemExit("No pages found.")
    return out


def parse_pages(spec, total):
    """Turn '1,5-7,12' into a zero-based set of page indices."""
    if not spec:
        return set()
    out = set()
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise SystemExit(f"Cannot read page range: {part!r}")
        lo = int(m.group(1))
        hi = int(m.group(2) or lo)
        out |= {n - 1 for n in range(lo, hi + 1) if 1 <= n <= total}
    return out


# -------------------------------------------------------- furniture and ink


def furniture_bounds(rgb):
    """Rows bounding the body, between coloured letterhead and footer.

    Returns None when the page carries no such furniture, in which case the
    whole page is body.
    """
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    red = ((R > 120) & (R - G > 50) & (R - B > 50)).sum(1)
    rows = np.where(red > 8)[0]
    if len(rows) < 2:
        return None

    top = rows[0]
    for i in range(1, len(rows)):
        if rows[i] - rows[i - 1] > 60:
            top = rows[i - 1]
            break
    bot = rows[-1]
    for i in range(len(rows) - 2, -1, -1):
        if rows[i + 1] - rows[i] > 60:
            bot = rows[i + 1]
            break
    if bot - top < rgb.shape[0] * 0.4:
        return None
    return int(top), int(bot)


def stamp_mask(rgb, bot):
    """Pixels belonging to a blue ink stamp in the lower part of the page.

    Only the stamp's own ink is returned. Whitening its bounding box would take
    the black body text underneath with it.
    """
    h, w, _ = rgb.shape
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    blue = (B > 90) & (B - R > 40) & (B - G > 25)
    zone = np.zeros_like(blue)
    zone[int(h * 0.62) : bot, int(w * 0.5) :] = True
    found = blue & zone
    return found if found.sum() > 2500 else None


def match_template(page_rgb, template_rgb, threshold=0.62):
    """Boxes on the page that look like the template image.

    Used for exclusions the user demonstrates by pasting a sample: a
    letterhead, a footer strip, a stamp. Matching is normalised correlation on
    the ink masks, which survives the brightness drift between scans.
    """
    page = (page_rgb.mean(2) < INK).astype(np.float32)
    tpl = (template_rgb.mean(2) < INK).astype(np.float32)
    th, tw = tpl.shape
    ph, pw = page.shape
    if th > ph or tw > pw or tpl.sum() < 50:
        return []

    # Correlation by FFT, normalised by the local ink energy of the page.
    shape = (ph, pw)
    F = np.fft.rfft2(page, shape)
    T = np.fft.rfft2(tpl[::-1, ::-1], shape)
    corr = np.fft.irfft2(F * T, shape)[th - 1 :, tw - 1 :]

    ones = np.fft.rfft2(np.ones_like(tpl), shape)
    energy = np.fft.irfft2(np.fft.rfft2(page**2, shape) * ones, shape)[
        th - 1 :, tw - 1 :
    ]
    denom = np.sqrt(np.maximum(energy, 1e-6) * max(tpl.sum(), 1e-6))
    score = corr / denom

    boxes = []
    work = score.copy()
    for _ in range(8):  # a template may repeat on a page
        y, x = np.unravel_index(np.argmax(work), work.shape)
        if work[y, x] < threshold:
            break
        boxes.append((int(y), int(x), int(y + th), int(x + tw)))
        work[max(0, y - th // 2) : y + th // 2, max(0, x - tw // 2) : x + tw // 2] = 0
    return boxes


def prepare(rgb, *, crop_furniture, drop_stamp, templates, scale):
    """Clean one page and return (greyscale image, y offset into the page).

    The offset lets figure crops be taken from the original colour page.
    """
    h, w, _ = rgb.shape
    top, bot = 0, h - 1
    if crop_furniture:
        found = furniture_bounds(rgb)
        if found:
            top, bot = found[0] + 8, found[1] - 8

    arr = rgb.copy()
    if drop_stamp:
        found = stamp_mask(rgb, bot)
        if found is not None:
            arr[found] = 255
    for tpl in templates:
        for y0, x0, y1, x1 in match_template(rgb, tpl):
            arr[y0:y1, x0:x1] = 255

    img = Image.fromarray(arr.astype(np.uint8)).crop((0, top, w, bot)).convert("L")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    return img, top, scale


PRINTED_NO = re.compile(r"(\d+)\s*of\s*(\d+)")


def printed_number(img, ocr):
    """The page number printed in the footer, if it can be read.

    Sparse-text mode, because a stamp often lands across the footer and
    line-based modes then read the number as part of the stamp.
    """
    w, h = img.size
    strip = img.crop((int(w * 0.35), int(h * 0.88), w, h))
    strip = strip.resize((strip.width * 2, strip.height * 2), Image.LANCZOS)
    text = ocr(strip, "--psm 11 --dpi 300")
    m = PRINTED_NO.search(text.replace("|", " "))
    return int(m.group(1)) if m else None


# --------------------------------------------------------- deskew, despeckle


def estimate_skew(gray, limit=2.0, step=0.25):
    """Rotation of the page in degrees, positive anticlockwise.

    Found by rotating a downsampled ink mask through small angles and keeping
    the one where the horizontal projection is spikiest: text lines line up,
    so the row sums swing hardest between line and gap. Everything downstream
    depends on this — rule detection, column gutters, stroke width — so it is
    worth doing before anything else looks at the page.
    """
    ink = (gray < INK).astype(np.uint8) * 255
    h, w = ink.shape
    # Centre crop: rotation pushes ink off the edges, and letting that reach
    # the score biases every measurement towards whichever angle spills least.
    ink = ink[int(h * 0.15) : int(h * 0.85), int(w * 0.15) : int(w * 0.85)]
    small = Image.fromarray(ink).resize((ink.shape[1] // 4, ink.shape[0] // 4))

    best, best_angle = -1.0, 0.0
    for notch in range(int(-limit / step), int(limit / step) + 1):
        angle = notch * step
        turned = np.asarray(
            small
            if angle == 0
            else small.rotate(angle, resample=Image.BILINEAR, fillcolor=0)
        ).astype(float)
        profile = turned.sum(1)
        total = profile.sum()
        if total <= 0:
            continue
        # Normalised, so angles are compared on line sharpness alone and not
        # on how much ink happens to remain inside the frame.
        score = float(np.square(np.diff(profile)).sum()) / (total**2)
        if score > best:
            best, best_angle = score, angle
    return best_angle


# Below this the rotation buys nothing: resampling softens the hairline rules
# that table detection depends on, and losing a column rule costs more than a
# fraction of a degree of tilt ever does. Above it, the tilt itself is what
# breaks rule detection, and straightening wins.
SKEW_DEADBAND = 1.0
ROTATED_INK = 215  # rotation greys the rules; meet them where they land


def deskew(img, angle):
    """Rotate a page upright, padding with paper white."""
    if abs(angle) < SKEW_DEADBAND:
        return img
    return img.rotate(angle, resample=Image.BICUBIC, fillcolor=255)


def despeckle(gray, max_size=12):
    """Erase specks too small to be type: scanner dust, toner spatter.

    Left alone they become stray punctuation in the text and false ink in the
    stroke-width measurement.
    """
    ink = gray < INK
    labels, count = label(ink)
    if count == 0:
        return gray
    sizes = np.bincount(labels.ravel())
    tiny = np.flatnonzero(sizes <= max_size)
    if not len(tiny):
        return gray
    out = gray.copy()
    out[np.isin(labels, tiny)] = 255
    return out


# ------------------------------------------------------------- table geometry


def spans_of(idx, gap=6):
    """Collapse runs of adjacent indices into (start, end) pairs."""
    if not len(idx):
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    return out


def centres(idx, gap=6, bar=18):
    """Rule positions from an eroded ink profile.

    A hairline rule becomes one position at its midpoint. A solid header bar is
    thicker than any rule, and its two edges are what bound the cells, so it
    contributes both of them instead.
    """
    out = []
    for a, b in spans_of(idx, gap):
        out += [a, b] if b - a >= bar else [(a + b) // 2]
    return out


def find_tables(ink):
    """Ruled tables on the page, as row and column rule positions.

    Scans render cell rules as faint grey hairlines that no brightness
    threshold separates from text, so rules are found by eroding the ink mask
    with a long kernel: only something rule-shaped survives.
    """
    rows = centres(np.where(binary_erosion(ink, np.ones((1, 120), bool)).any(1))[0])
    if len(rows) < 3:
        return []

    # Two rules belong to the same table when a column rule runs between them.
    # Row height is no guide: one tall row can exceed the gap between tables.
    vmask = binary_erosion(ink, np.ones((25, 1), bool))
    groups, cur = [], [rows[0]]
    for y in rows[1:]:
        slab = vmask[cur[-1] + 6 : y - 6]
        if slab.size and slab.mean(0).max() > 0.8:
            cur.append(y)
        else:
            groups.append(cur)
            cur = [y]
    groups.append(cur)

    tables = []
    for g in groups:
        if len(g) < 3:
            continue
        # Columns are measured inside the band: a rule elsewhere on the page
        # says nothing about this table, and a band with none is not a table.
        band = ink[g[0] : g[-1] + 1]
        support = binary_erosion(band, np.ones((25, 1), bool)).sum(0) / band.shape[0]
        cols = centres(np.where(support > 0.30)[0], 25)
        if len(cols) < 3:
            continue
        tables.append({"top": g[0], "bot": g[-1], "rows": g, "cols": cols})
    return tables


def deinvert(img, ink, tables):
    """Flip solid header bars to black-on-white so Tesseract can read them."""
    a = np.array(img)
    for t in tables:
        x0, x1 = t["cols"][0], t["cols"][-1]
        for y0, y1 in zip(t["rows"], t["rows"][1:]):
            band = ink[y0 + 4 : y1 - 4, x0:x1]
            if band.size and band.mean() > 0.55:
                a[y0 + 3 : y1 - 3, x0:x1] = 255 - a[y0 + 3 : y1 - 3, x0:x1]
    return Image.fromarray(a)


# ---------------------------------------------------------------- emphasis


def measure_emphasis(gray, word):
    """Raw stroke width and slant of one word.

    Tesseract's LSTM engine reports no font attributes and the legacy engine
    that did is not installed, so weight is measured from the glyphs
    themselves: mean stroke width, from the distance transform of the ink.

    The width is returned unnormalised. Dividing by the word's own height, the
    obvious move, is wrong: a word without ascenders or descenders is shorter
    than its neighbours at the same font weight, so 'or' and 'a' come out
    looking bold. Normalisation belongs to the line, which has a stable height.
    """
    x, y, w, h = word["x"], word["y"], word["w"], word["h"]
    patch = gray[max(0, y) : y + h, max(0, x) : x + w]
    if patch.size == 0:
        return None
    ink = patch < GLYPH
    if ink.sum() < 25 or h < 8:
        return None

    stroke = 2.0 * distance_transform_edt(ink)[ink].mean()
    ys, xs = np.nonzero(ink)
    ys = ys - ys.mean()
    xs = xs - xs.mean()
    cyy = (ys * ys).mean()
    # Shear of the vertical axis: positive leans right, as italics do.
    slant = float((xs * ys).mean() / cyy) if cyy > 1e-6 else 0.0
    return {"stroke": float(stroke), "slant": slant, "ink": int(ink.sum())}


# ----------------------------------------------------- columns and figures


def column_bounds(boxes, width, min_gutter=0.06, min_share=0.2, min_lines=5):
    """Vertical gutters splitting the page into columns.

    Returns a list of (x0, x1) column ranges, or a single full-width range when
    the page is not columnar.

    The guards matter more than the detection. A contents page has a gutter
    between its headings and its page numbers, and a ruled table has one
    between every pair of columns; reading either of those as newspaper columns
    would reorder the document. So a split is only accepted when both sides
    carry a real share of the words across a real number of distinct lines.
    """
    if not boxes:
        return [(0, width)]
    cover = np.zeros(width, bool)
    for x, _, w, _ in boxes:
        cover[max(0, x) : min(width, x + w)] = True

    gaps = [
        (a, b)
        for a, b in spans_of(np.where(~cover)[0], 1)
        if b - a >= width * min_gutter and a > width * 0.25 and b < width * 0.75
    ]
    if not gaps:
        return [(0, width)]

    a, b = max(gaps, key=lambda g: g[1] - g[0])
    cut = (a + b) // 2
    left = [x for x, _, w, _ in boxes if x + w / 2 < cut]
    right = [x for x, _, w, _ in boxes if x + w / 2 >= cut]
    rows_left = {y // 20 for x, y, w, _ in boxes if x + w / 2 < cut}
    rows_right = {y // 20 for x, y, w, _ in boxes if x + w / 2 >= cut}

    share = min(len(left), len(right)) / max(len(boxes), 1)
    if share < min_share or len(rows_left) < min_lines or len(rows_right) < min_lines:
        return [(0, width)]
    return [(0, cut), (cut, width)]


def find_figures(ink, tables, word_boxes, min_area=0.012):
    """Ink regions that are neither table nor text: diagrams, logos, charts."""
    mask = ink.copy()
    bands = []
    for t in tables:
        # Generous, because a coloured header bar can sit above the first rule
        # the detector found, and a leftover strip of it reads as a figure.
        top, bot = max(0, t["top"] - 45), t["bot"] + 45
        mask[top:bot, :] = False
        bands.append((top, bot))
    for x, y, w, h in word_boxes:
        mask[max(0, y - 3) : y + h + 3, max(0, x - 3) : x + w + 3] = False

    if not mask.any():
        return []
    # Close small gaps so a diagram's strokes label as one region.
    grown = mask
    for _ in range(2):
        grown = (
            np.pad(grown, 1)[:-2, 1:-1]
            | np.pad(grown, 1)[2:, 1:-1]
            | np.pad(grown, 1)[1:-1, :-2]
            | np.pad(grown, 1)[1:-1, 2:]
            | grown
        )

    labels, count = label(grown)
    page_area = ink.shape[0] * ink.shape[1]
    out = []
    for sl in find_objects(labels):
        if sl is None:
            continue
        ys, xs = sl
        area = (ys.stop - ys.start) * (xs.stop - xs.start)
        if area < page_area * min_area:
            continue
        if (ys.stop - ys.start) < 40 or (xs.stop - xs.start) < 40:
            continue
        region = mask[ys, xs]
        height, width = ys.stop - ys.start, xs.stop - xs.start
        fill = region.mean()
        if fill < 0.02:  # a stray speckle, not a figure
            continue
        # A solid block of ink is a decorative bar or a rule, not a figure. A
        # real diagram has internal structure: strokes with space between them.
        if fill > 0.85:
            continue
        if height < ink.shape[0] * 0.09 and width > ink.shape[1] * 0.4:
            continue
        if max(height / width, width / height) > 12:
            continue
        if any(ys.start < b and ys.stop > a for a, b in bands):
            continue  # part of a table, however the rules were detected
        out.append((int(ys.start), int(xs.start), int(ys.stop), int(xs.stop)))
    return out
