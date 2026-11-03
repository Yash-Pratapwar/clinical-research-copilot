# Suggested 7-minute demo script

Updated 4 November 2026. See [USER_GUIDE.md](USER_GUIDE.md) for full instructions
and [ARCHITECTURE.pdf](ARCHITECTURE.pdf) for the two-page technical handout.

## Prepare before recording

Start Ollama and the app. Use only bundled synthetic documents. Prepare
`Protocol_v1_generated.pdf`, `Protocol_v2_generated.pdf`, `Investigator_Brochure.pdf`,
`Monitoring_Visit_Report.docx`, and `Deviation_Log.docx`. Other bundled fixtures
can make generic version references ambiguous; use exact library names. Review
answers and originals in advance. Model latency may require cuts; seven minutes
is a presentation target.

## 0:00-0:45 - Purpose and boundaries

Explain source-backed research document review across protocols, brochures,
monitoring reports and deviations. Show the local stack and explain that this
prototype is not clinical decision support or a validated clinical system.

## 0:45-1:30 - Current architecture

Show ingestion branching into retained originals/version records, complete
extracted text for comparison, and tokenizer-bounded search chunks. Exactly two
resolved versions use deterministic full-text comparison; ordinary questions use
retrieval and the local LLM.

## 1:30-2:30 - Upload and version history

Upload `Protocol_v1_generated.pdf`, leave **Version history** on **Detect from
filename**, optionally label it `Baseline`, and click **Index selected documents**.
Upload `Protocol_v2_generated.pdf` separately, explicitly select the first history,
and label it `Revision 2`. Show both rows in **Version history and exact comparison**,
their shared **Document** ID, UTC upload times, hashes and original availability.
Upload the other three files together with the version label blank. Explain that
uploads persist, earlier versions remain, and selecting files alone does not index.

## 2:30-3:15 - Answer and source citations

Ask `What are the inclusion and exclusion criteria in Protocol_v1_generated.pdf?`.
Expand **Source citations**: show the cited ID, filename, section, location and
retrieved passage. Uncited retrieval results are hidden; citations still require
checking against originals. PDF page and DOCX paragraph locations differ.
Use **Deselect documents** before a whole-library question.

## 3:15-4:15 - Safety evidence across documents

Ask `Which monitoring deviations may impact patient safety?`. If clarification is
requested, choose the relevant protocol, monitoring report and deviation log and
click **Answer using selected documents**. Check which sources the answer actually
cites. Separate documented observations from possible implications; do not assert
patient harm. Any SAE deadline is specific to these synthetic documents.

## 4:15-5:20 - Complete-version comparison

In **Version history and exact comparison**, select generated v1 as **Before
version** and generated v2 as **After version**, then click **Compare complete
versions**. Show section changes, locations, matching methods, diff and any word
changes or ambiguity warnings. Download an original. Formatting and images are
excluded. Optionally ask `Compare Protocol_v1_generated.pdf and
Protocol_v2_generated.pdf.`: chat uses the same comparator and shows sources
directly in before/after text, without a separate citation panel.

## 5:20-6:10 - Reset and unsupported questions

Choose an **Example questions** item, then click **New chat**. Show empty messages
and the selector reset to **Choose an example...**, while selected scope and
indexed versions remain. There is no saved chat archive. **Deselect documents**
clears scope; **Clear index and conversation** also deletes saved history and
originals, so leave it untouched during the demo.

Ask an unsupported fact such as the sponsor's phone number. Verify the app reports
that the documents do not establish it. If the model invents an answer, report
the failure candidly; do not present it as a successful grounding example.

## 6:10-7:00 - Verification and next steps

Show module separation and relevant test output. Fake embeddings in offline tests
validate behavior, not clinical answer quality. Mention OCR, complex layout
fidelity, retrieval evaluation, stronger models, security and clinical validation
as remaining work. Refer viewers to the user guide for upload errors, legacy
original recovery and storage/backup details.
