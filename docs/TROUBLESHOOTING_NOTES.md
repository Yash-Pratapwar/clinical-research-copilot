# Troubleshooting and performance notes

Keep observed behavior, measurements, fixes, and practical troubleshooting tips
here as the app evolves. Timings are observations, not performance guarantees.

For the current upload and version workflow, see [USER_GUIDE.md](USER_GUIDE.md).
For implementation and storage, see [ARCHITECTURE.md](ARCHITECTURE.md).

## 2026-11-04: Chat controls and source citations

- **New chat** clears messages, pending questions and clarification choices,
  and resets **Example questions** to **Choose an example...**. It preserves
  indexed documents and the selected document scope. If the next question should
  search all files, click **Deselect documents** too. There is no chat archive.
- **Clear index and conversation** deletes the stored library, version history
  and originals as well as resetting chat and scope. It is not needed for a new chat.
- **Source citations** replaces the former Supporting excerpts label. Only source
  IDs cited in the answer appear; missing numbers are expected because IDs are
  not renumbered after filtering. No citation IDs means no citation panel.
- A two-version chat comparison shows source names and locations directly in
  before/after text; a separate citation panel is not expected on this path.
- Filtering is not claim validation: cited passages may include extra context,
  and a model can still cite the wrong evidence. Check originals.

## 2026-11-04: Upload and version-history problems

| Symptom | What to check |
| --- | --- |
| File selected but not listed | Click **Index selected documents** and inspect each result message. |
| Already saved | Latest entry has the same filename/bytes and no new label; use a fresh label for an intentional repeat. |
| Version label already exists | Choose a label unique within the selected history. |
| Custom label rejected for several files | Select one file, or clear the label before a batch upload. |
| Renamed revision grouped separately | Choose the intended **Version history** before uploading; automatic grouping uses filename markers, not document-body identity. Existing entries cannot be reassigned in the UI. |
| Repeated filenames have suffixes | Use the unique displayed library name to select or ask about a saved version. |
| Original unavailable / legacy comparison error | Re-upload the original file. An old chunk-only index cannot reconstruct it or recover earlier overwritten content. |
| No extracted text differences | Text comparison found no changes; formatting/images may still differ. Verify the chosen Before/After entries. |
| Repeated-content ambiguity warning | Check source locations and originals; automatic section identity remains heuristic. |
| Empty, scanned, encrypted or oversize file | Use a nonempty searchable PDF or DOCX up to 15 MB; OCR and password-protected PDFs are unsupported. |

For the bundled demo use explicit names such as `Protocol_v1_generated.pdf` and
`Protocol_v2_generated.pdf`. The optional retrieval-check fixture currently names
`Protocol_v2.pdf`, which is not a bundled file under that exact name. Align expected
fixture names with the indexed library before interpreting that check's result;
do not treat a name mismatch as loss of stored embeddings.

Back up the complete configured database directory while the app is stopped.
History SQLite, original blobs and Chroma data belong together. A normal refresh
or restart does not require re-uploading, but it does not provide durable chat history.

## 2026-11-03: Slow first search

The saved index opened quickly; loading the embedding model accounted for most
of the first-search delay in this diagnostic run.

| Operation | Observed time |
| --- | ---: |
| Open the existing index (34 chunks, 5 documents) | 0.68 seconds |
| First retrieval, including embedding-model initialization | 43.14 seconds |
| Repeat retrieval in the same process | 0.10 seconds |

The probe used the existing local index and cached embedding model with offline
model loading enabled. These retrieval timings exclude Ollama answer generation.
They do not isolate model loading from query encoding and vector search within
the first retrieval. Ollama was unreachable from the diagnostic process, so no
generation timing was measured.

### Why this happens

- Document chunks and embeddings persist on disk, but the embedding model must
  load into memory in each new Python process. A process restart or a code change
  that invalidates cached resources can cause another cold start.
- Warm searches reuse the loaded embedding model. They still encode each new
  question; they do not recreate the saved document embeddings on every search.
- The UI spinner says “Searching indexed evidence and asking local Ollama...”.
  It covers retrieval and answer generation together, so a long spinner does
  not establish that vector search is slow.
- `copilot/llm.py` currently sets Ollama `keep_alive="2m"`. After that idle period,
  a later request may need to reload the language model as well. This is a
  possible additional delay, not a measured cause in the run above.
- A resolved comparison of exactly two versions uses extracted-text comparison,
  bypassing similarity retrieval and Ollama generation.

### What to check

1. Compare the first question after startup with another question in the same
   running app. A large improvement points to model initialization.
2. If consecutive questions remain slow, measure retrieval and generation
   separately before attributing the delay to the index.
3. If answer generation fails, check that Ollama is running and that the
   configured model is installed (`ollama list`).
4. Do not clear or rebuild the index merely because the first search is slow.

## 2026-11-03: Index persistence

- The default database directory is `.chroma` under the project root, resolved
  independently of the shell's working directory. `COPILOT_DB_PATH` overrides it.
- Chroma uses `PersistentClient`. Document history and original files are stored
  alongside the vector database under `.chroma/history`.
- Restarting or refreshing the app does not normally require uploading again.
  Conversation state and selected documents are Streamlit session state and
  have a different lifetime from the persisted index.
- Changing the database path points the app at a different index. The **Clear
  index and conversation** button explicitly deletes the stored library.
- Extraction or chunk-schema upgrades can refresh derived chunks from retained
  originals when the index opens; this is separate from ordinary retrieval.

## 2026-11-03: “Insufficient relevant evidence” for a version comparison

Observed question: `whats the differenc between version 1 and 2`.

The deterministic router did not recognize `differenc` as a comparison and chose
`lookup`. Similarity retrieval returned evidence from only one selected version,
so the evidence guard rejected the answer. This did not indicate missing saved
embeddings.

The router now accepts this spelling, `diffrence`, `diff`, and `differ`, in addition
to the existing comparison phrases. A regression test reopens a saved index and
checks that the observed question produces the exact comparison without retrieval
or model generation. The related core, index, resolution, and UI suite passed
29 tests after the fix. Routing remains rule based; other wording may need
additional handling. Check **Tool selected** when diagnosing an unexpected answer.

## 2026-11-03: Document selection and pinned chat input

The input stays pinned at the bottom using a top-level `st.chat_input`. The main
content has extra bottom padding so the final controls can scroll above it.
When document references are ambiguous, select the desired files and click
**Answer using selected documents**, or reply with their exact names to resume
the original question.
