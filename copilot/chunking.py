"""Paragraph-aware chunks bounded by the embedding tokenizer, including specials."""
import re
import json
from dataclasses import dataclass, replace

from .config import CHUNK_OVERLAP, CHUNK_TOKENS
from .documents import DocumentPart

CHUNK_SCHEMA = "paragraph-layout-v2"


@dataclass(frozen=True)
class Chunk:
    text: str
    filename: str
    file_type: str
    section: str
    location: str
    page: int
    section_id: str = ""
    chunk_index: int = 0
    paragraph_start: int = 0
    paragraph_end: int = 0
    paragraph_split: bool = False
    token_count: int = 0
    block_type: str = "paragraph"
    source_regions: str = "[]"


def chunk_parts(parts: list[DocumentPart], size: int = CHUNK_TOKENS,
                overlap: int = CHUNK_OVERLAP, *, tokenizer=None) -> list[Chunk]:
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be > overlap >= 0")
    if tokenizer is None:
        from .embeddings import _model
        model = _model()
        tokenizer = model.tokenizer
        size = min(size, model.max_seq_length)
    count = lambda text: len(tokenizer.encode(text, add_special_tokens=True))
    if count("") >= size or overlap >= size:
        raise ValueError("Token budget must accommodate special tokens and exceed overlap")

    def split_long(text):
        """Prefer sentences, then words; split a long unbroken word as a last resort."""
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
            while sentence:
                if count(sentence) <= size:
                    yield sentence
                    break
                lo, hi = 1, len(sentence)
                best = 0
                while lo <= hi:
                    middle = (lo + hi) // 2
                    if count(sentence[:middle]) <= size:
                        best = middle
                        lo = middle + 1
                    else:
                        hi = middle - 1
                if not best:
                    raise ValueError("Token budget cannot accommodate one character")
                boundary = sentence.rfind(" ", 0, best + 1)
                end = boundary if boundary > 0 else best
                fragment = sentence[:end].strip()
                # Count actual submitted text, including tokenizer special tokens.
                if count(fragment) > size:
                    raise ValueError("Unable to split paragraph within token budget")
                yield fragment
                sentence = sentence[end:].lstrip()

    groups = []
    previous = None
    section_number = 0
    for position, part in enumerate(parts, 1):
        if part.block_type in {"header", "footer"}:
            continue
        identity = (part.filename, part.file_type, part.section)
        if identity != previous:
            section_number += 1
        previous = identity
        part = replace(part, paragraph_index=part.paragraph_index or position,
                       section_id=part.section_id or f"section-{section_number:06d}")
        # Keep PDF pages separate for accurate single-page citations.
        key = (part.filename, part.file_type, part.section_id,
               part.page if part.file_type == "pdf" else 0,
               "table-" + str(part.paragraph_index) if part.block_type == "table"
               else "list" if part.block_type == "list_item" else "prose")
        if groups and groups[-1][0] == key:
            groups[-1][1].append(part)
        else:
            groups.append((key, [part]))

    chunks = []
    for _, group in groups:
        units = []
        for part in group:
            if not part.text.strip():
                continue
            oversized = count(part.text) > size
            texts = split_long(part.text) if oversized else [part.text]
            units.extend((text, part, oversized) for text in texts)

        def joined(batch):
            return "\n\n".join(unit[0] for unit in batch)

        def emit(batch):
            first, last = batch[0][1], batch[-1][1]
            location = first.location if first.location == last.location else f"{first.location} to {last.location}"
            chunks.append(Chunk(
                text=joined(batch), filename=first.filename, file_type=first.file_type,
                section=first.section, section_id=first.section_id, location=location,
                page=first.page, chunk_index=len(chunks),
                paragraph_start=first.paragraph_index, paragraph_end=last.paragraph_index,
                paragraph_split=any(unit[2] for unit in batch),
                token_count=count(joined(batch)), block_type=first.block_type,
                source_regions=json.dumps([
                    {"paragraph_index": part.paragraph_index, "page": part.page,
                     "bbox": part.bbox, "block_type": part.block_type}
                    for part in dict((unit[1].paragraph_index, unit[1]) for unit in batch).values()
                ])))

        current = []
        for unit in units:
            if current and count(joined(current + [unit])) > size:
                emit(current)
                # Repeat complete units only, and always leave space for new content.
                trailing = []
                if overlap:
                    for candidate in reversed(current):
                        proposed = [candidate] + trailing
                        if count(joined(proposed)) > overlap or count(joined(proposed + [unit])) > size:
                            break
                        trailing = proposed
                current = trailing
            current.append(unit)
        if current:
            emit(current)
    return chunks
