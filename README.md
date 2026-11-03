# Clinical Research AI Copilot

**Purpose:** A PDF/DOCX document-search and question-answering prototype for the
*Clinical Research AI Copilot Challenge*. It uses RAG, source-backed answers,
multidocument comparison, and a transparent LangGraph tool router. **Not** a
medical device, a validated clinical workflow, or a safe place for patient records.

See [Troubleshooting and performance notes](docs/TROUBLESHOOTING_NOTES.md) for
observed timings, index persistence, and fixes for common issues.

## Resolving document questions

The app resolves document references before searching their contents. Exact
filenames (with or without their extension) take precedence. Numbered versions
and filename words identify candidates, but ambiguous candidates trigger a
clarification instead of using vector similarity or a shared suffix to guess.
This applies to arbitrary document names, not just protocols. A missing version
or unknown explicit filename also requests clarification. General topic questions
without a document reference can still search the whole library.

When asked to clarify, select the documents and click **Answer using selected
documents**, or reply with their exact names. The original question resumes
against those files only, with balanced retrieval and a check for evidence from
every selected document. The selected names appear with the answer and remain
the scope for follow-ups. Use **Search the whole library instead** to clear that
scope, or name different files. Clearing the index clears pending questions and
document selections too. Existing indexed documents do not need re-indexing.

Resolution currently uses indexed filenames and explicit user choices; it does
not verify study identity, dates, or versions from document bodies. Use descriptive
filenames including study identifiers, or select files explicitly when uncertain.

## The 8 GB Windows 11 setup

| Component | Choice | Cost |
|---|---|---|
| Local text LLM | Ollama + `qwen2.5:1.5b` (~986 MB model download) | Free |
| Local embeddings | `all-MiniLM-L6-v2` via Sentence Transformers | Free |
| Persistent vector search | ChromaDB, local directory `.chroma` | Free |
| Workflow | LangGraph StateGraph with explicit intent routing | Free |
| UI | Streamlit | Free |
| Parsing | PyMuPDF (text PDFs), python-docx | Free |

**Why this size:** The 1.5B LLM is a conservative CPU/RAM choice; 3B or 7B models
might slow down an 8 GB Windows laptop. A small model may miss nuances; citations
and testing are especially important. You need a network connection **once** to
download Python packages, the LLM, and the embedding model. After caching them,
queries remain local and do not require a paid API.

### Step 1: prerequisite installations

1. Install **Python 3.11, 64-bit** from https://www.python.org/downloads/ .
   On the installer, check **Add python.exe to PATH** and **pip**.
2. Install **Ollama for Windows**: https://ollama.com/download . Start it.
3. Optionally install **VS Code**: https://code.visualstudio.com/ .

Open **PowerShell** or **Command Prompt**. Confirm:

```powershell
py -3.11 --version
ollama --version
```

Then download the **exact lightweight model** (not plain `qwen2.5`, which defaults
to 7B and is much heavier):

```powershell
ollama pull qwen2.5:1.5b
ollama list
```

### Step 2: install packages

**Easiest:** Double-click `install_windows.bat` in the unzipped project folder.
Or run these commands from PowerShell in this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**You do not need to activate the venv**, which avoids PowerShell execution-policy
problems. Python dependencies, including `torch` for embeddings, may take several
minutes to download. Make sure you have several GB of available disk space.

### Step 3: start the application

Double-click `start_windows.bat`, or run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://localhost:8501` if the browser does not open automatically.
The *first document index* downloads `all-MiniLM-L6-v2` to your Hugging Face
cache. This requires internet access once, no Hugging Face subscription.

### Step 4: reproduce the 5-minute demo

1. Upload all five files from `sample_docs/` using **Index selected documents**.
   They are synthetic and do **not** contain real patient data.
2. Ask: `What are the inclusion and exclusion criteria?`
3. Ask: `What are the SAE reporting requirements?`
4. Ask: `Which monitoring deviations may impact patient safety?`
5. Ask: `Compare protocol version 1 and version 2.`
6. Expand **Source citations** to inspect document names, section and PDF
   page number or DOCX paragraph location.
7. Ask a question not in the documents, e.g., `What is the sponsor's phone number?`
   Correct behavior is to say the documents do not establish it.

### Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe evaluation\run_retrieval_checks.py
```

The retrieval check requires the demo files to have been indexed first. The
`evaluation/expected_cases.json` describes expected source documents; manually
review the generated answers in the UI. Passing retrieval tests does **not**
prove clinical correctness.

## How it works

```text
Documents: PDF/DOCX -> ordered paragraphs/blocks -> tokenizer-bounded paragraph chunks
          -> MiniLM embeddings (CPU) -> local ChromaDB + source metadata

Question: User -> LangGraph intent router
                  |-- lookup   -> semantic retrieval
                  |-- summary  -> expanded retrieval
                  |-- compare  -> full-text diff for two versions; retrieval for larger selections
                  |-- safety   -> protocol + monitoring + deviation retrieval
          -> evidence prompt -> Ollama qwen2.5:1.5b -> answer + [S#] sources
          -> UI renders source excerpt, filename and location from metadata
```

The router is **deterministic** (keyword-based) rather than an autonomous
LLM agent. This is a deliberate, testable MVP decision; LangGraph still performs
conditional tool selection. Don't market it as a self-directed clinical agent.

## Modules

- `app.py`: Streamlit uploader, conversations, citations and reset.
- `copilot/documents.py`: PDF text extraction and DOCX paragraphs/tables with location tracking.
- `copilot/chunking.py`: Bound passages to avoid MiniLM truncation and preserve references.
- `copilot/embeddings.py`: Lazy, cached, local CPU embeddings.
- `copilot/index.py`: Chroma persistence, idempotent ingestion, similarity search,
  diversity-enriched multi-document retrieval.
- `copilot/workflow.py`: LangGraph intent router and four retrieval tools.
- `copilot/llm.py`: Local Ollama prompt, evidence injection and allowed-source checks.
- `tests/`: deterministic tests of parsing, routing, chunking, references, and indexing.
- `evaluation/`: retrieval regression checks for synthetic documents.
- `docs/ARCHITECTURE.pdf`: two-page engineering architecture handout.
- `docs/DEMO_SCRIPT.md`: suggested 5–10 minute video script.

## Design decisions and limitations

- **No paid API / no external RAG hosting.** Chroma and model execution are local; Chroma anonymized telemetry and Streamlit usage statistics are disabled.
- **Source citations show only passages referenced in the answer.**
  The code removes nonexistent source IDs and hides uncited retrieved passages, but a small
  LLM can still misinterpret, overstate or cite the wrong supporting passage.
- **PDF page vs DOCX paragraph:** PDF location is the actual file page. DOCX has
  no trustworthy physical page before rendering, so it reports paragraph/table
  locations rather than inventing page numbers.
- **Scanned PDFs/images are unsupported** (OCR would be a future enhancement).
- **Complex tables and PDF section detection are heuristic.** Verify against source.
- **Retrieval cutoff is heuristic, not calibrated confidence.** Change the threshold
  based on labeled evaluation cases; score does not prove factuality.
- **Document content can contain adversarial instructions.** Prompts warn the LLM
  against obeying them, but there is no hardened prompt-injection defense.
- **No authentication, audit immutability, PHI handling or RBAC.** Use only local,
  synthetic or explicitly authorized data. Do not expose Streamlit publicly.
- **No study-level separation:** all indexed documents live in one local collection.
  Filter by study and user before any real deployment.
- **No end-to-end clinical validation.** Human verification is required.

## Submission checklist

- [ ] Upload repository to GitHub, excluding `.chroma`, `.venv`, `.env` and private data.
- [ ] Attach `docs/ARCHITECTURE.pdf` (max. two pages).
- [ ] Keep this README with setup, assumptions, limitations and enhancements.
- [ ] Record `docs/DEMO_SCRIPT.md` as a 5–10 minute screen recording.
- [ ] Do a fresh-machine setup test if possible.

## Document version history

Uploads create immutable version records in `.chroma/history/versions.sqlite3`.
Changed uploads with the same filename preserve previous versions. Filename markers
such as `Protocol_v1_generated` and `Protocol_v2_generated` suggest a shared history.
Select an existing **Version history** during upload to link renamed files or
filenames with spelling differences explicitly.

Identical file bytes share one SHA-256-addressed original in
`.chroma/history/sources` and one set of Chroma chunks and embeddings. Each version
still has its own ID, label, timestamp and document identity. Re-uploading the latest
identical file without a label is a no-op; enter a fresh version label to record
another version with identical content. Different filenames are recorded even when
their bytes match. Equal extracted text in different binary files has different hashes.

Open **Version history and exact comparison**, select Before and After, and click
**Compare complete versions**. The comparison aligns full extracted sections and
shows additions, removals, modifications, section moves, source locations and word
changes. Two-document chat comparisons also use full text instead of vector search
or an LLM. Section alignment first reserves normalized section-body SHA-256 matches, excluding\na leading heading line. Repeated bodies use headings, numeric parent sections,\nunique neighboring bodies and order to resolve identity; unresolved ties are flagged.\nRemaining sections use heading matching and then text similarity, followed by exact\nline and word differences. Hashes preserve case, numbers and punctuation;
check ambiguous matches against the downloadable originals. Formatting and images
are outside this text comparison.

Existing Chroma records are imported automatically. Their original files and full
pre-chunking text were not retained by the previous app: re-upload those files to
enable exact comparison and original downloads. Previously overwritten content
cannot be recovered. Clearing the index also clears version history and originals.

## Future enhancements

Study-specific collections, BM25 hybrid retrieval, calibrated retrieval evaluation,
risk terminology taxonomy, stronger local LLM on better hardware, OCR, PDF table
reconstruction, audit trails, user consent, encryption, access controls, medical
safety review, model/version monitoring, feedback ratings and human-in-the-loop.

## Troubleshooting

**`ollama` is not recognized:** reinstall Ollama, reopen your terminal, check
`ollama --version` and launch Ollama from Start. On some installations, run
`ollama serve` in a separate terminal if Ollama's service is not running.

**Model not found:** run `ollama pull qwen2.5:1.5b` (include `:1.5b`).

**Out of memory:** close Chrome/other heavy apps. Exit other Ollama processes.
Use `ollama stop qwen2.5:1.5b` if needed. Change model to `qwen2.5:0.5b` via
`COPILOT_MODEL` environment variable as a last resort, knowing quality drops.

**Torch/Hugging Face model download fails:** check internet and retry; the first
embedding run caches model weights. No paid account is needed for public model.

**PowerShell says scripts are disabled:** don't activate `.venv`; use the direct
`.venv\Scripts\python.exe` invocation above.

**DOCX source shows paragraph rather than page:** expected and intentional.

**Garbage PDF text:** likely a scanned document. Use native digital PDFs for demo.


## Paragraph-aware retrieval chunks

Chunks now pack complete paragraphs under the same section, up to 256 embedding
tokens including special tokens (or the model limit if lower). Oversized paragraphs
split at sentences, then words if necessary. Up to 32 tokens of complete trailing
units overlap when space permits. PDF chunks stay within a page; PyMuPDF text blocks
approximate paragraphs. Metadata records section identity, paragraph ranges, chunk
order and token counts. Saved originals are automatically re-chunked after a chunk
schema change without altering version records or stored full-text comparison input.

See [enhancements.md](enhancements.md) for all changes, benefits, migration behavior,
limitations, and the distinction between search chunks and complete-version comparison.


## PDF layout reconstruction

PDF extraction now uses line/span geometry, spacing, indentation and font cues to
reconstruct paragraphs and detect headings. Basic columns are read in order;
detected ruled tables retain rows/cells; list items retain continuation lines.
Repeated margin headers/footers are retained as typed source records but excluded
from search and version comparisons. Page coordinates and source regions are
preserved for traceability.

Saved PDF originals are automatically re-parsed and re-indexed after an extraction
schema change, without creating new versions or changing the original files.
This improves derived comparison text as well as retrieval. Borderless tables,
complex layouts and scanned PDFs remain limitations; OCR is not included.
See [enhancements.md](enhancements.md) for thresholds, behavior and tradeoffs.
