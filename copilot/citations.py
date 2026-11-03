"""Resolve answer citations against the evidence supplied to generation."""
import re


def source_citations(answer, evidence):
    """Keep cited sources only, retaining their original IDs and source metadata."""
    cited = {int(value) for value in re.findall(r'\[S(\d+)\]', answer)}
    return [{
        'label': f'[S{i}]', 'filename': entry.metadata['filename'],
        'location': entry.metadata['location'], 'section': entry.metadata['section'],
        'excerpt': entry.text,
    } for i, entry in enumerate(evidence, 1) if i in cited]


def cited_saved_sources(answer, sources):
    """Apply the same rule to conversations saved before citation filtering."""
    labels = set(re.findall(r'\[S\d+\]', answer))
    return [source for source in sources if source['label'] in labels]
