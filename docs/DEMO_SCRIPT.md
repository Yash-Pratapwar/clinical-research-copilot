# Suggested 7-minute demo script

0:00–0:45 — Introduce the business problem: CRAs need source-backed answers
from protocols, investigator brochures, monitoring reports and deviations.
Explain free and entirely local stack, 8 GB Windows suitability.

0:45–1:30 — Walk through architecture diagram: ingestion, chunking,
embeddings, ChromaDB, LangGraph intent router, Ollama answer, citations.

1:30–2:15 — Upload synthetic PDF and DOCX documents from `sample_docs`.
Call out Chroma persistence and the difference between PDF pages and DOCX
paragraph references. DO NOT upload sensitive real records in the recording.

2:15–3:00 — Ask inclusion/exclusion criteria; expand PDF source page.
Mention no plain prompt-only LLM: the prompt includes retrieved passages.

3:00–3:40 — Ask SAE reporting requirement; explain that the reported deadline
is *study-specific synthetic example*, never universal medical advice.

3:40–4:50 — Ask deviations potentially affecting patient safety. Check
that protocol requirement, monitoring observation and deviation log all appear.
Separate observation from potential implications (do not assert patient harm).

4:50–5:40 — Compare v1 and v2; point out Week 8 post-dose monitoring addition.
Cross-check both versions in citations.

5:40–6:20 — Ask unknown fact such as sponsor phone number: demonstrate
fallback/limitations; note tiny model can still hallucinate and must be checked.

6:20–7:00 — Show code separation, automatic tests, assumptions and next steps:
real clinical security and validation are out of scope for this prototype.

Before recording: index all documents; verify expected examples with your installed
model; keep original files at hand to confirm citations; don't claim a test passes
if the model gave an incorrect or unsupported answer.
