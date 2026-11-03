# Uploads, version history, and chat guide

Updated: 4 November 2026. This guide describes the controls in `app.py`.

## Start the app

Complete the installation in [README](../README.md), then double-click
`start_windows.bat` or run this command from the project folder:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://localhost:8501`. Use synthetic or authorized research documents.
Searchable PDF and DOCX files are supported, up to 15 MB per file. Scanned PDFs
need OCR outside this app; password-protected PDFs are unsupported.

## Upload and index documents

1. In the sidebar's **Document library**, use **Upload PDF or DOCX documents**
   to choose one or more files.
2. For unrelated files or a first upload, leave **Version history** set to
   **Detect from filename**. For a revision of an existing document, choose its
   history explicitly if its new name does not clearly match the old name.
3. Optionally enter a **Version label (optional, one file at a time)**, such as
   `Approved revision 2`. Select only one file when entering a label.
4. Click **Index selected documents**. Wait for each success, already-saved,
   or error message. Merely selecting a file does not index it.
5. Check the indexed list. Each saved version is available as a separate entry.
   The displayed document count counts version entries, not document families.

The first indexing operation may download the embedding model. After packages
and models are cached, ordinary local use does not require a paid API. Saved
documents persist across normal app restarts; chat messages are session state.

## Save another version

Version history groups revisions under a document family. Saving new content
does not overwrite previous version records or their retained original files.

For a concrete example using bundled files:

1. Upload `sample_docs/Protocol_v1_generated.pdf` with **Detect from filename**.
   Optionally label it `Baseline`, then click **Index selected documents**.
2. Replace the uploader selection with `sample_docs/Protocol_v2_generated.pdf`.
3. In **Version history**, choose the history represented by the first file.
   Enter `Revision 2` and click **Index selected documents**.
4. Open **Version history and exact comparison** and verify that both rows have
   the same **Document** ID and different version entries.

Filename markers such as `v1`, `v2`, `ver 2`, and `version 2` suggest a shared
history. This is a filename heuristic, not verification of study identity or
clinical chronology. Explicitly choose an existing history for renamed files,
spelling differences, or uncertain grouping. The selector displays a representative
filename for each history; use the history table's **Document** ID to check grouping.
The upload selector controls future uploads; it does not move an already saved version.

| Upload situation | Result |
| --- | --- |
| Changed bytes with the same filename in the same history | A new version is saved; the old one remains. |
| Same filename and bytes as the latest entry in that history, no label | Already saved; no new version. |
| Same bytes with a fresh version label | A separate version record can be saved, sharing stored content. |
| Different filenames with identical bytes | Separate version records share the original and embeddings. Choose a history to group them explicitly. |
| Version label already used in the same history | An error; choose a unique label. |
| Custom label with multiple selected files | An error; upload one file at a time or leave the label blank. |

Automatic labels are generated from the number of versions in a history, not
the document's written approval date. A repeated filename may gain a display
suffix such as `[Revision 2]` so saved entries remain selectable separately.
Use the exact display name from the library when asking about that entry.

## Inspect history and download originals

Expand **Version history and exact comparison**. The table shows:

| Column | Meaning |
| --- | --- |
| Document | Internal ID grouping a document's versions. |
| Version | Custom or automatically assigned version label. |
| File | Unique display name used to select the saved version. |
| Uploaded (UTC) | Upload timestamp in UTC; not the document's effective date. |
| Content hash | SHA-256 of the original file bytes. |
| Original available | Whether the app retained the original for download and full-text comparison. |

Choose **Before version** and **After version**. Use **Download before original**
and **Download after original** when those controls are available. A download is
the saved original, not an AI-generated reconstruction.

## Compare complete versions

1. Choose the intended **Before version** and **After version**.
2. Click **Compare complete versions**.
3. Review each change's kind, section, matching method, locations, before/after
   text, line diff, and word-change table when present.
4. Check warnings about repeated content with ambiguous matches against originals.

The selectors allow any two saved entries, including entries from different
histories. Choose the correct study and revision order yourself. This action uses
complete extracted text, without similarity retrieval or Ollama generation.
It identifies added, removed, modified, and moved sections. Unchanged normalized
section bodies are matched first, then remaining headings/text are aligned.

**No extracted text differences** means the comparator found no text differences;
it does not establish that formatting, images, signatures, or clinical meaning are
identical. Section alignment is heuristic. Images and formatting are not compared.

You can also ask a chat question using two exact library names, for example:

> Compare Protocol_v1_generated.pdf and Protocol_v2_generated.pdf.

When exactly two versions are resolved, chat uses the same full-text comparator.
The response includes before/after document names, locations, text, and diffs
directly; it does not use an LLM or need a separate **Source citations** panel.
The history comparison view additionally shows matching methods and word-change
tables. Larger chat selections use retrieved evidence and the local model, so
they are not exhaustive complete-version comparisons.

## Ask questions and review citations

Type a question in the bottom chat input. Alternatively, choose an item in
**Example questions** and click **Ask selected example**. Selecting an example
alone does not submit it. **What can you do?** receives predefined local help
without document search or a model call.

For ambiguous document references, choose **Documents to use** and click
**Answer using selected documents**, or reply with exact library names. The app
then resumes the original unanswered question. **Cancel unanswered question**
cancels that pending request.

Selected documents remain the scope for follow-up questions and appear below
the conversation. **Deselect documents** removes that scope and any pending
clarification; the next question can search the whole library. It keeps prior
messages and their historical source labels.

For generated answers, **Source citations** lists only passages whose `[S#]`
IDs appear in the answer. Each entry shows the document's display name, PDF page
or DOCX paragraph/table location, section, and retrieved passage. IDs are preserved
rather than renumbered, so a list may start at `[S3]`. Uncited retrieval results
and similarity scores are hidden, including when saved chat messages rerender.

Filtering reflects the model's explicit citations; it does not verify which text
internally influenced generation or prove every cited claim. A displayed passage
can include context beyond the particular data stated in the answer. Unknown
source IDs are removed, and an answer with no source IDs has no citation panel.
Check claims against the originals.

## New chat, deselection, and deleting the library

| Control | Clears | Preserves |
| --- | --- | --- |
| **New chat** | Messages, pending question, clarification choices; resets **Example questions** to **Choose an example...** | Selected document scope, indexed versions, history, originals, cached models. |
| **Deselect documents** | Selected scope and pending clarification | Chat messages and indexed library. |
| **Clear index and conversation** | Indexed library, history records, saved originals, current messages, scope, pending clarification; resets examples | Model downloads and uploaded files outside the app's storage. |

**New chat** clears the current conversation; it does not archive it or create
a separately saved chat that you can reopen. Use **Deselect documents** as well
if you want the next question to search the entire library.

## Storage, backup, and older indexes

By default, vectors and chunks live in `.chroma`, with version records and full
extracted parts at `.chroma/history/versions.sqlite3` and content-addressed
originals at `.chroma/history/sources`. `COPILOT_DB_PATH` can point to another
library. Stop the app before copying the whole database directory for backup;
keep Chroma, SQLite history, and originals together. There is no in-app restore UI.

Indexes from before original-file retention may show **Original available = False**.
Re-upload those original files to recover full-text comparison and download support.
Re-uploading cannot recover content overwritten before version history existed.
Retained files may be re-parsed or re-chunked automatically after schema upgrades;
derived search/comparison results can change while original bytes and version
identity remain preserved. This may make the first startup slower.

See [troubleshooting](TROUBLESHOOTING_NOTES.md) for common errors and
[architecture](ARCHITECTURE.md) for implementation details. Version retention is
not a regulated audit trail; the prototype has no authentication, access control,
encryption-at-rest implementation, or clinical validation.
