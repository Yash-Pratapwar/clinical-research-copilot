"""Conservative, local responses to standalone app-help questions."""
import re
import unicodedata


CAPABILITIES = """I help you explore uploaded clinical research documents. I can:
- Answer questions with source citations.
- Summarize study protocols.
- Compare document versions and show extracted text changes.
- Review documented deviations and potential safety implications.

Upload and index a PDF or DOCX to get started, then ask something like
"What are the eligibility criteria?" I support research document review, not clinical decision-making."""

GETTING_STARTED = """To get started:
1. Upload PDF or DOCX files in the Document library sidebar.
2. Click **Index selected documents**.
3. Ask a question, such as "What are the eligibility criteria?" or "Summarize the study protocol."
4. Review the source citations and verify answers in the original documents.

To compare versions, upload both versions and ask to compare their exact filenames, or use **Version history and exact comparison**."""


def general_response(question: str) -> str | None:
    """Match whole utterances so document questions retain their usual routing."""
    text = unicodedata.normalize('NFKC', question).lower().replace('’', "'")
    text = re.sub(r"[^\w\s']", ' ', text)
    text = ' '.join(text.split())
    text = re.sub(r'^(?:hi|hello|hey)\s+', '', text)
    text = re.sub(r'^please\s+|\s+please$', '', text).strip()
    if text in {
        'what can you do', 'what can you help me with', 'how can you help me',
        'how can you help', 'what are your capabilities', 'what do you do',
        'what is this app', 'help',
    }:
        return CAPABILITIES
    if text in {
        'how do i use this', 'how do i use this app', 'how to use this app',
        'how do i get started', 'how to get started', 'getting started',
    }:
        return GETTING_STARTED
    if text in {'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening'}:
        return ('Hello! I help you explore clinical research documents. Upload and index a PDF or DOCX, '
                'or ask "What can you do?" to see the available features.')
    return None
