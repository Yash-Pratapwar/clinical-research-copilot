"""Resolve answer citations against the evidence supplied to generation."""
import re


def source_citations(answer, evidence):
    """Filter explicit citations; otherwise retain supplied evidence for review.

    The pre-fe66c54 UI displayed evidence even when local models omitted IDs.
    Keep that fallback without claiming these sources are verified citations.
    """
    cited = {int(value) for value in re.findall(r'\[S(\d+)\]', answer)}
    return [{
        'label': f'[S{i}]', 'filename': entry.metadata['filename'],
        'location': entry.metadata['location'], 'section': entry.metadata['section'],
        'excerpt': entry.text,
    } for i, entry in enumerate(evidence, 1) if not cited or i in cited]


def cited_saved_sources(answer, sources):
    """Preserve the same fallback when rendering saved conversations."""
    labels = set(re.findall(r'\[S\d+\]', answer))
    return [source for source in sources if not labels or source['label'] in labels]
