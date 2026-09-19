"""Per-page work, isolated so it can run in parallel and be cached.

One page in, one plain-data result out: words with positions, confidence and
stroke measurements, table geometry, and any figures already cropped to PNG.
Nothing here touches the Word document, and nothing returned holds a large
array, so results move cheaply between processes and onto disk.
"""

import hashlib
import io
import json
import os
import pickle
import shutil
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image

import pagelab as P

CACHE_VERSION = 3  # bump when page analysis changes shape or meaning
LOW_CONFIDENCE = 70  # a line below this is re-read, then flagged


def cache_root():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "pdf-ocr-extractor" / "cache"
    else:
        base = Path.home() / ".cache" / "pdf-ocr-extractor"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_key(pdf_path, index, options):
    stat = Path(pdf_path).stat()
    payload = json.dumps(
        {
            "pdf": str(pdf_path),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "index": index,
            "options": options,
            "version": CACHE_VERSION,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def clear_cache():
    shutil.rmtree(cache_root(), ignore_errors=True)


def _ocr(img):
    return pytesseract.image_to_data(
        img, lang="eng", config="--psm 3 --dpi 300", output_type=pytesseract.Output.DICT
    )


def _words_from(data, gray, measure, keep=25):
    out = []
    for i, txt in enumerate(data["text"]):
        if not txt.strip() or int(data["conf"][i]) <= keep:
            continue
        w = {
            "t": txt.strip(),
            "c": int(data["conf"][i]),
            "x": int(data["left"][i]),
            "y": int(data["top"][i]),
            "w": int(data["width"][i]),
            "h": int(data["height"][i]),
            "line": (
                int(data["block_num"][i]),
                int(data["par_num"][i]),
                int(data["line_num"][i]),
            ),
            "bold": False,
            "italic": False,
            "low": False,
        }
        w["style"] = P.measure_emphasis(gray, w) if measure else None
        out.append(w)
    return out


def _reread(img, gray, words, measure):
    """Re-read weak lines at higher magnification, and keep the better result.

    A line the first pass was unsure about is usually small, faint or crowded.
    Re-running just that strip at twice the size, in single-line mode, costs a
    fraction of a page and often resolves it. The original is kept whenever the
    second attempt does not actually score better, so this can only improve the
    text or leave it alone.
    """
    by_line = {}
    for w in words:
        by_line.setdefault(w["line"], []).append(w)

    improved, rescued = [], 0
    for key, group in by_line.items():
        confidence = float(np.mean([w["c"] for w in group]))
        if confidence >= LOW_CONFIDENCE:
            improved += group
            continue

        x0 = max(0, min(w["x"] for w in group) - 12)
        y0 = max(0, min(w["y"] for w in group) - 8)
        x1 = min(img.width, max(w["x"] + w["w"] for w in group) + 12)
        y1 = min(img.height, max(w["y"] + w["h"] for w in group) + 8)
        strip = img.crop((x0, y0, x1, y1))
        strip = strip.resize((strip.width * 2, strip.height * 2), Image.LANCZOS)
        data = pytesseract.image_to_data(
            strip,
            lang="eng",
            config="--psm 7 --dpi 300",
            output_type=pytesseract.Output.DICT,
        )

        fresh = [
            (t.strip(), int(c), int(l), int(tp), int(wd), int(ht))
            for t, c, l, tp, wd, ht in zip(
                data["text"],
                data["conf"],
                data["left"],
                data["top"],
                data["width"],
                data["height"],
            )
            if t.strip() and int(c) > 25
        ]
        if not fresh:
            improved += group
            continue
        second = float(np.mean([c for _, c, *_ in fresh]))
        if second <= confidence + 2:
            improved += group
            continue

        rescued += 1
        for text, conf, left, top, wide, high in fresh:
            w = {
                "t": text,
                "c": conf,
                "x": x0 + left // 2,
                "y": y0 + top // 2,
                "w": max(1, wide // 2),
                "h": max(1, high // 2),
                "line": key,
                "bold": False,
                "italic": False,
                "low": False,
            }
            w["style"] = P.measure_emphasis(gray, w) if measure else None
            improved.append(w)

    for w in improved:
        w["low"] = w["c"] < LOW_CONFIDENCE
    return improved, rescued


def analyse(pdf_path, index, options, rgb=None):
    """Everything one page needs, as plain data. Cached on disk by content."""
    key = cache_key(pdf_path, index, options)
    cached = cache_root() / f"{key}.pkl"
    if options.get("use_cache", True) and cached.exists():
        try:
            return pickle.loads(cached.read_bytes())
        except Exception:
            cached.unlink(missing_ok=True)

    pytesseract.pytesseract.tesseract_cmd = options["tesseract"]
    if rgb is None:
        rgb = P.render_pages(pdf_path, options["dpi"], only=index)[0]

    per_page = options.get("page_options", {}).get(str(index + 1), {})
    templates = [
        np.asarray(Image.open(p).convert("RGB")).astype(int)
        for p in options["templates"]
    ]

    img, offset, scale = P.prepare(
        rgb,
        crop_furniture=not (
            options["keep_furniture"] or per_page.get("keep_furniture")
        ),
        drop_stamp=not (options["keep_stamp"] or per_page.get("keep_stamp")),
        templates=templates,
        scale=options["scale"],
    )

    skew = 0.0
    gray = np.array(img)
    if not options["no_deskew"]:
        skew = P.estimate_skew(gray)
        img = P.deskew(img, skew)
        gray = np.array(img)
    if not options["no_despeckle"]:
        gray = P.despeckle(gray)
        img = Image.fromarray(gray)

    ink = gray < P.INK
    # A rotated page has softer rules than it did before it was turned.
    rule_ink = gray < (P.ROTATED_INK if abs(skew) >= P.SKEW_DEADBAND else P.INK)
    tables = [] if per_page.get("no_tables") else P.find_tables(rule_ink)
    flat = P.deinvert(img, ink, tables)
    words = _words_from(_ocr(flat), gray, not options["no_emphasis"])

    rescued = 0
    if not options["no_second_pass"]:
        words, rescued = _reread(flat, gray, words, not options["no_emphasis"])
    else:
        for w in words:
            w["low"] = w["c"] < LOW_CONFIDENCE

    figures = []
    if not options["no_figures"]:
        boxes = [(w["x"], w["y"], w["w"], w["h"]) for w in words]
        page = Image.fromarray(rgb.astype(np.uint8))
        for y0, x0, y1, x1 in P.find_figures(ink, tables, boxes):
            crop = page.crop(
                (
                    int(x0 / scale),
                    int(y0 / scale) + offset,
                    int(x1 / scale),
                    int(y1 / scale) + offset,
                )
            )
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
            figures.append(
                {"y": y0, "x": x0, "png": buffer.getvalue(), "width": crop.width}
            )

    result = {
        "index": index,
        "tables": tables,
        "words": words,
        "figures": figures,
        "height": int(gray.shape[0]),
        "width": int(gray.shape[1]),
        "skew": skew,
        "rescued": rescued,
        "printed": P.printed_number(
            img, lambda i, cfg: pytesseract.image_to_string(i, config=cfg)
        ),
        "single_column": bool(per_page.get("single_column")),
    }
    cached.write_bytes(pickle.dumps(result))
    return result


def run_job(args):
    """Entry point for the process pool."""
    pdf_path, index, options = args
    return analyse(pdf_path, index, options)
