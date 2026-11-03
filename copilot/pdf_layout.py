"""Conservative geometry-based PDF reading order and paragraph reconstruction.

No OCR or model inference. Every output retains its original page coordinates;
uncertain layout is kept as text rather than guessed into a semantic structure.
"""
from collections import Counter
from dataclasses import dataclass, replace
from statistics import median
import math
import logging
import re

PDF_LAYOUT_SCHEMA = "pdf-lines-v1"


@dataclass(frozen=True)
class LayoutItem:
    text: str
    bbox: tuple[float, float, float, float]
    size: float = 11.0
    bold: bool = False
    font: str = ""
    block: int = 0
    kind: str = "paragraph"
    rows: tuple[tuple[str, ...], ...] = ()
    direction: tuple[float, float] = (1.0, 0.0)


def _clean(text):
    return re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()


def _union(items):
    return (min(x.bbox[0] for x in items), min(x.bbox[1] for x in items),
            max(x.bbox[2] for x in items), max(x.bbox[3] for x in items))


def _lines(page):
    lines = []
    # Explicitly exclude images; dict output provides line/span/font geometry.
    data = page.get_text("dict", flags=3)
    for block_number, block in enumerate(data["blocks"]):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = _clean("".join(s["text"] for s in line["spans"]))
            dominant = max(spans, key=lambda s: len(s["text"]))
            lines.append(LayoutItem(text, tuple(line["bbox"]), dominant["size"],
                                    bool(dominant["flags"] & 16), dominant["font"],
                                    block_number, direction=tuple(line.get("dir", (1, 0)))))
    return lines


def _table_items(page):
    # Ruled tables only: inferring borderless tables from aligned text alone can
    # mistake two prose columns for a table. Keep that text for normal parsing.
    tables = []
    try:
        detected = page.find_tables(strategy="lines_strict").tables
    except (RuntimeError, ValueError) as exc:
        logging.getLogger(__name__).warning(
            "Table detection failed on page %s; preserving native text: %s", page.number + 1, exc)
        return []
    for table in detected:
        rows = tuple(tuple(_clean((cell or "").replace("\n", " ")) for cell in row)
                     for row in table.extract())
        if len(rows) < 2 or table.col_count < 2:
            continue
        bbox = tuple(table.bbox)
        # External header is not inside bbox, so leave it in normal text.
        tables.append(LayoutItem("\n".join(" | ".join(row) for row in rows),
                                 bbox, kind="table", rows=rows))
    return tables


def _inside(line, box):
    x = (line.bbox[0] + line.bbox[2]) / 2
    y = (line.bbox[1] + line.bbox[3]) / 2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _margin_key(text):
    text = " ".join(text.casefold().split())
    # Normalize page counters, but never erase arbitrary section numbers/doses.
    text = re.sub(r"\bpage\s+\d+(?:\s*(?:of|/)\s*\d+)?", "page #", text)
    if re.fullmatch(r"\d+(?:\s*/\s*\d+)?", text):
        return "#"
    return text


def _margin(item, height):
    if item.bbox[3] <= height * 0.09:
        return "header"
    if item.bbox[1] >= height * 0.91:
        return "footer"
    return None


def _column_order(items):
    """Read separated columns left-to-right, honoring spanning title bands."""
    if len(items) < 2:
        return items
    intervals = sorted((item.bbox[0], item.bbox[2]) for item in items)
    merged = []
    for left, right in intervals:
        if merged and left <= merged[-1][1] + 18:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    if len(merged) > 1:
        # A genuine vertical gutter across this region permits column traversal.
        return [item for left, right in merged for item in
                _column_order([x for x in items if left <= x.bbox[0] <= right])]

    center = (min(x.bbox[0] for x in items) + max(x.bbox[2] for x in items)) / 2
    left = [x for x in items if x.bbox[2] < center - 9]
    right = [x for x in items if x.bbox[0] > center + 9]
    overlap = (min(max((x.bbox[3] for x in left), default=0),
                   max((x.bbox[3] for x in right), default=0))
               - max(min((x.bbox[1] for x in left), default=math.inf),
                     min((x.bbox[1] for x in right), default=math.inf)))
    spanning = [x for x in items if x.bbox[0] < center - 9 and x.bbox[2] > center + 9]
    if left and right and overlap > 5 and spanning:
        # Full-width headings divide the page into independent column regions.
        pending = list(items)
        ordered = []
        for divider in sorted(spanning, key=lambda x: (x.bbox[1], x.bbox[0])):
            if divider not in pending:
                continue
            band = [x for x in pending if x != divider and x.bbox[3] <= divider.bbox[1] + 1]
            ordered.extend(_column_order(band))
            pending = [x for x in pending if x not in band and x != divider]
            ordered.append(divider)
        ordered.extend(_column_order(pending))
        return ordered
    return sorted(items, key=lambda x: (round(x.bbox[1], 1), x.bbox[0]))


_LIST = re.compile(r"^(?:[•●▪‣*\-–]|\(?\d+[.)]|\(?[A-Za-z][.)])\s+")
_NUMBERED = re.compile(r"^(?:[Ss]ection\s+)?\d+(?:\.\d+){0,3}\s+[A-Z]")


def _is_heading(line, body_size):
    short = len(line.text) <= 110 and len(line.text.split()) <= 14
    if not short or line.text.endswith((".", ";", ",")) or _LIST.match(line.text):
        return False
    numbered = bool(_NUMBERED.match(line.text))
    typography = line.size >= body_size * 1.15 or line.bold
    return typography or (numbered and line.size >= body_size * 0.95)


def _paragraphs(items, body_size):
    # Estimate normal line advance from nearby same-block lines. Fall back to
    # body font size for PDFs where each rendered line is a separate block.
    advances = [b.bbox[1] - a.bbox[1] for a, b in zip(items, items[1:])
                if a.block == b.block and a.kind == b.kind == "paragraph"
                and abs(a.bbox[0] - b.bbox[0]) < body_size * 2
                and body_size * 0.8 < b.bbox[1] - a.bbox[1] < body_size * 1.8]
    advance = median(advances) if advances else body_size * 1.25
    output, current = [], []

    def flush():
        if current:
            # Retain hyphens: automatic dehyphenation can alter drug names/codes.
            output.append(replace(current[0], text=" ".join(x.text for x in current),
                                  bbox=_union(current)))
            current.clear()

    for item in items:
        if item.kind in {"table", "header", "footer"}:
            flush()
            output.append(item)
            continue
        heading = _is_heading(item, body_size)
        marker = bool(_LIST.match(item.text))
        if heading:
            flush()
            output.append(replace(item, kind="heading"))
            continue
        if current:
            previous = current[-1]
            dy = item.bbox[1] - previous.bbox[1]
            indent = item.bbox[0] - previous.bbox[0]
            hanging_list = current[0].kind == "list_item" and 0 <= indent <= body_size * 3
            first_indent = len(current) == 1 and -body_size * 3 <= indent < 0
            family = lambda name: re.sub(r"(bold|italic|oblique|regular|[-,+])", "", name.lower())
            font_change = bool(item.font and previous.font and family(item.font) != family(previous.font))
            boundary = (marker or font_change or dy <= 0 or dy > advance * 1.4
                        or abs(item.size - previous.size) > body_size * 0.12
                        or item.direction != previous.direction
                        or (abs(indent) > body_size * 0.9 and not hanging_list and not first_indent))
            # A short completed line followed by a new PDF block is evidence of
            # a paragraph break, but punctuation alone does not split a block.
            short_end = (previous.text.endswith((".", "?", "!"))
                         and previous.bbox[2] < max(x.bbox[2] for x in current) - body_size * 2)
            if boundary or (item.block != previous.block and short_end and not hanging_list):
                flush()
        current.append(replace(item, kind="list_item") if marker else item)
    flush()
    return output


def parse_pdf_layout(document):
    """Return one list per page, including separately typed repeated furniture."""
    pages = []
    counts = Counter()
    for page in document:
        lines = _lines(page)
        keys = {(_margin(line, page.rect.height), _margin_key(line.text))
                for line in lines if _margin(line, page.rect.height)}
        counts.update(keys)
        pages.append(lines)
    threshold = max(2, math.ceil(len(pages) * 0.6))
    output = []
    for page, lines in zip(document, pages):
        sizes = Counter()
        for line in lines:
            sizes[round(line.size, 1)] += len(line.text)
        body_size = sizes.most_common(1)[0][0] if sizes else 11.0
        tables = _table_items(page)
        remaining = []
        for line in lines:
            if any(_inside(line, table.bbox) for table in tables):
                continue
            margin = _margin(line, page.rect.height)
            if margin and counts[(margin, _margin_key(line.text))] >= threshold:
                line = replace(line, kind=margin)
            remaining.append(line)
        output.append(_paragraphs(_column_order(remaining + tables), body_size))
    return output
