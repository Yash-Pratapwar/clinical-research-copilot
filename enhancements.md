# Enhancements

This document records the changes made during this work, their purpose, practical
benefits, and limitations. Retrieval quality improvements are expected from better
boundaries and traceability; they have not been measured on a clinical benchmark.

## 1. Supported PyMuPDF import

Replaced `import fitz` and `fitz.open` with `import pymupdf` and `pymupdf.open` in
extraction and tests. This removes the deprecated import warning and avoids relying
on an API scheduled for removal. No intended extraction behavior change.

## 2. Immutable version history

Added a SQLite registry at `.chroma/history/versions.sqlite3`. Each version records
its document family ID, version ID, version label, source filename, unique display
label, timestamp, and source-file SHA-256 hash. Uploading changed content under an
existing filename preserves earlier versions. Filename version markers suggest
families; the upload UI can explicitly link a renamed file to an existing history.

Benefit: earlier protocols remain available for retrieval, download, and comparison.
Tradeoffs: retained versions consume disk space; filename-based grouping is a
heuristic and spelling differences require explicit selection. IDs describe identity,
not whether documents belong to the same clinical study. This is not a regulated
audit trail or an access-controlled document management system.

## 3. Shared content for identical versions

Version records reference a content hash. Byte-identical files share one original
at `.chroma/history/sources/<sha256>`, one full extracted-text record in SQLite,
and one set of Chroma chunks and embeddings. Version-specific document IDs,
version IDs, filenames and section IDs are attached when evidence is retrieved,
so shared content does not cite the wrong version. Enter a new version label to
record an intentional repeat of the latest identical upload; an unlabeled repeat
of that same latest upload is a no-op.

Benefit: avoids duplicate originals and embedding work while preserving separate
history entries. Limitation: this is binary deduplication. Files with equal text but
different PDF/DOCX bytes have different hashes and are stored separately. Original
files and SQLite/Chroma must be backed up together. Concurrent ingestion and crash
recovery across these storage systems are not a distributed transaction.

## 4. Full-text version comparison

Added complete-section alignment, added/removed/modified/moved section detection,
line differences and word changes. The history view shows both source locations
and before/after text and allows original downloads. Two-document chat comparisons
use the same deterministic comparison instead of relying on retrieved excerpts or
an LLM to discover differences. Larger chat selections still use RAG.

Benefit: small edits outside the most relevant search results are still compared.
Limitations: this compares extracted text, not images or formatting. Section
alignment is heuristic, sentence/paragraph moves inside a section are represented
as text edits, and section splits/merges have no dedicated many-to-many alignment.
Long comparisons can produce long outputs. No clinical significance is inferred.

## 5. Section-body hashes and repeated-content context

Comparison first reserves SHA-256 matches of normalized section bodies. It removes
an exact leading heading line and collapses whitespace, preserving case, numbers and
punctuation. Section numbers, document IDs and headings are excluded from the body
hash, allowing unchanged text to match after renaming, renumbering or relocation.
These section hashes are computed during comparison; they are separate from the
persisted binary-file hashes used for content deduplication.

Repeated boilerplate has the same body hash. Headings, numeric parent sections,
unique neighboring body hashes and relative order help align those copies. Ties
that remain after context are flagged in the UI/chat. Remaining sections are
matched by heading and then text similarity, followed by an exact text diff.

Benefit: unchanged moved or renamed content is matched before a weaker heading
match can take it. Limitations: a hash proves equal normalized input, not section
identity or semantic equivalence. A one-character edit changes the hash completely.
For example, `24 hours` and `48 hours` require similarity alignment, then an exact
diff to identify `24` → `48`. Duplicate contexts may still be ambiguous. Whitespace
normalization aids matching, while original text remains available for the diff.

## 6. Paragraph-aware, tokenizer-bounded retrieval chunks

Replaced 145-word windows with complete-paragraph packing using the embedding
model's actual tokenizer. The default budget is 256 tokens including special
tokens, capped by the model's runtime sequence limit. Complete paragraphs are
added until the next one would exceed the budget. That paragraph starts the next
chunk rather than being cut halfway. If all four section paragraphs fit, all four
are stored together. Otherwise, for example, paragraphs 1–2 and 3–4 form separate
chunks if each pair fits. Chunks never cross section, document or PDF-page boundaries.

Only a paragraph that is itself too large is split: sentence boundaries first,
then word boundaries, and character fragments for an oversized unbroken word.
Every resulting chunk is counted again before embedding. Optional overlap repeats
complete trailing paragraphs/sentence fragments within a 32-token allowance,
including special tokens, and only when there is room for new content. Overlap may
therefore be zero rather than cutting a normal paragraph to fill a quota.

DOCX extraction preserves body paragraph/table order. Tables are ordered blocks;
oversized tables follow the same text splitting rules rather than a table-aware
row/header strategy. PDF extraction uses sorted PyMuPDF text blocks, split at
detected headings, as paragraph approximations. Docling is not used.

Each chunk retains a content-local section ID, zero-based chunk index, one-based
parser-block/paragraph start and end, token count, source location, and a flag for
an oversized paragraph split. Paragraph positions count extracted nonempty blocks,
including headings and tables. The citation location still retains the parser's
original DOCX paragraph/table label or PDF page. Retrieval qualifies the section ID
with the version ID and adds document/version identity. Section IDs are local to
a version, not guaranteed stable across edits; cross-version identity uses alignment.

Benefits: preserves paragraph meaning, reduces mid-sentence breaks and avoids
silently truncating long technical words based on an approximate word budget.
Tradeoffs: more tokenizer calls and variable chunk lengths; sometimes more chunks,
unused token capacity, and less overlap. A long paragraph still needs splitting.
PDF blocks and reading order can be imperfect for columns, tables, repeated headers,
and unusual layouts. There is no OCR or reliable physical DOCX pagination.

## 7. Migration and independence from chunk boundaries

Existing Chroma records are imported into the registry. Old indexes that never
saved originals need re-uploading to recover full extraction; already overwritten
versions cannot be recovered. Retained originals are automatically re-chunked when
the chunk schema changes, with stale search chunks removed and chunk counts updated.
This can load/download the embedding model and takes time at startup. Re-uploading
a legacy original also rebuilds its searchable chunks with the new schema.

Full comparison text and version records remain unchanged during re-chunking.
There are two independent paths:

```text
Source → full extracted sections in SQLite → section alignment → exact differences
       → paragraph/token chunks in Chroma → similarity search → question answering
```

Changing paragraphs 1–2 / 3–4 into paragraphs 1 / 2–4 changes retrieval units, not
the comparison input. If paragraph 4 changes `24 hours` to `48 hours`, comparison
examines that text regardless of which chunk contains it or whether search would
retrieve it. The paths share extraction quality, so parser omissions can affect both.

Clearing the index also clears version history and saved originals.

## 8. PDF paragraph reconstruction and structured layout

Replaced text-block-as-paragraph extraction with line/span geometry from
PyMuPDF dictionary output. Paragraphs are reconstructed using normal line advance,
vertical gaps, indentation, font family/size changes, and heading/list markers.
Wrapped lines become spaces inside a paragraph; intentional hyphens are retained
rather than guessing whether a drug name or identifier should be dehyphenated.
Numbered and short typographic headings establish section boundaries, including
unnumbered bold/large headings. Large font changes or indents can be imperfect
signals, so this is a heuristic reconstruction, not guaranteed semantic parsing.

Separated columns are traversed left-to-right and top-to-bottom within each column;
spanning headings divide independent column regions. Complex sidebars, overlapping
text and unusual layouts still require visual review. The implementation targets
horizontal reading order, not robust rotated/vertical-text layout reconstruction.

Repeated text in the top/bottom 9% of pages is typed as header/footer when present
on at least two pages and at least 60% of the document's pages. Only page counters
are normalized for that detection. Furniture stays in the full extraction for
traceability, but is excluded from search chunks and version comparisons.
Single-page margins and non-repeated text are retained to avoid silently deleting
content. Repeating meaningful margin text can still be misclassified; repeated
headers positioned below the detection zone will not be recognized.

Ruled tables are extracted into row/cell arrays and serialized as row text.
Their original cell text is excluded from ordinary paragraphs to avoid duplication.
Tables receive separate chunk groups, and list items retain hanging continuation
lines and individual item boundaries. Borderless tables remain native text rather
than guessing a table from aligned prose columns. Merged cells and complex tables
depend on PyMuPDF's detector. If detection raises a runtime/value error, native
text is retained and a diagnostic is logged. Oversized tables still use text
splitting, without repeating column headers in each resulting chunk.

Each PDF part records its page, bounding rectangle (PDF points), block type,
paragraph reading-order index, section identity and optional table rows. Search
metadata includes JSON source regions for the paragraphs contributing to a chunk.
Coordinates make source inspection possible; the UI does not yet draw overlays.
Excluded headers/footers still count in parser reading-order positions, so chunk
paragraph ranges may have gaps.

Benefits: fewer arbitrary mid-paragraph boundaries; cleaner evidence without
repeated page furniture; more reliable basic column order; explicit table/list
units and source geometry. No new dependencies, OCR, or model downloads are added
by extraction. Table finding, page-wide analysis and retained geometry add CPU,
memory and metadata overhead. Retrieval quality has not been benchmarked, and
this does not replace a layout model for difficult PDFs.

Existing saved PDF originals are upgraded automatically using an extraction-schema
marker. Both derived full comparison text and searchable chunks are refreshed,
while original bytes, source hashes, timestamps and version IDs remain unchanged.
Chunk-only migrations continue to preserve comparison text. Parser upgrades may
change comparison results because extraction itself improved; comparison still
operates on full sections rather than chunk boundaries. Legacy records without
originals need re-uploading.

Also corrected section-body normalization to treat line breaks as whitespace and
to recognize numbered heading/parent prefixes, avoiding false mismatches caused
by wrapping or renumbering.

## Verification

Tests cover existing routing and UI behavior; immutable versions; byte-identical
content sharing and correct citations; original downloads; legacy recovery;
full-text comparisons that bypass search and the LLM; moved/renamed/repeated bodies;
token budgets, paragraph boundaries, overlap, long-paragraph splitting, reading
order, section/page boundaries; and re-chunking without changing comparison text
or version IDs. Offline tests use a deterministic test tokenizer and embeddings;
production ingestion uses the configured SentenceTransformer tokenizer and model.

Validation after the paragraph-aware chunking change: **45 tests passed**, including
Streamlit UI tests. No clinical retrieval benchmark was run.

Validation after PDF layout reconstruction: **64 tests passed**, including real
in-memory PDF fixtures for wrapped paragraphs, indentation, font changes, columns,
spanning headings, repeated margins, list continuations, ruled tables, table-finder
fallback, source geometry and extraction upgrades. All six repository sample PDFs
preserved every source text token in the complete extraction. No clinical retrieval
benchmark was run.
