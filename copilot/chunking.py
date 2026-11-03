"""Word-bounded chunks preserving the page/section of each source."""
from dataclasses import dataclass

from .config import CHUNK_OVERLAP, CHUNK_WORDS
from .documents import DocumentPart


@dataclass(frozen=True)
class Chunk:
    text: str
    filename: str
    file_type: str
    section: str
    location: str
    page: int


def chunk_parts(parts: list[DocumentPart], size: int = CHUNK_WORDS,
                overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be > overlap >= 0")
    chunks: list[Chunk] = []
    # DOCX: combine adjacent paragraphs inside each heading to avoid tiny embeddings.
    # PDF: keep pages separate, so every chunk has an accurate page reference.
    groups: list[list[DocumentPart]] = []
    for part in parts:
        if groups and part.file_type == "docx" and groups[-1][0].file_type == "docx" \
                and groups[-1][-1].section == part.section:
            groups[-1].append(part)
        else:
            groups.append([part])

    for group in groups:
        # Track token-to-source location for honest DOCX paragraph references.
        word_locs: list[str] = []
        words: list[str] = []
        for part in group:
            part_words = part.text.split()
            words.extend(part_words)
            word_locs.extend([part.location] * len(part_words))
        for start in range(0, len(words), size - overlap):
            end = min(start + size, len(words))
            if start == end:
                continue
            loc = group[0].location if group[0].file_type == "pdf" else (
                word_locs[start] if word_locs[start] == word_locs[end - 1]
                else f"{word_locs[start]} to {word_locs[end - 1]}"
            )
            chunks.append(Chunk(text=" ".join(words[start:end]),
                                filename=group[0].filename, file_type=group[0].file_type,
                                section=group[0].section, location=loc, page=group[0].page))
            if end == len(words):
                break
    return chunks
