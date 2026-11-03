"""Conservative document selection, independent of content similarity."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resolution:
    documents: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    clarification: str = ''


def named_documents(question: str, filenames: list[str]) -> list[str]:
    """Match complete filenames/stems, without treating a prefix as a name."""
    matches = []
    for name in filenames:
        stem = re.escape(Path(name).stem)
        suffix = re.escape(Path(name).suffix)
        if re.search(r'(?<![\w.-])' + stem + '(?:' + suffix + r')?(?![\w.-])', question, re.I):
            matches.append(name)
    return matches


def _versions(text: str) -> list[str]:
    pattern = r'(?<![a-z0-9])(?:version|ver|v)[ _.-]*(\d+(?:\.\d+)*)(?![a-z0-9])'
    versions = re.findall(pattern, text.lower())
    abbreviated = re.search(pattern + r'\s*(?:and|vs\.?|versus|to|&)\s*(\d+(?:\.\d+)*)(?![\w.])', text.lower())
    if abbreviated:
        versions.append(abbreviated.group(2))
    return list(dict.fromkeys(versions))


def resolve_documents(question: str, filenames: list[str], *, mode: str,
                      selected: list[str] | None = None, confirmed: bool = False) -> Resolution:
    """Never use shared suffixes or semantic chunk scores to break identity ties.

    Explicit names override a remembered scope. Generic topic lookups may search
    the library; comparisons and numbered document references must be resolved.
    """
    names = named_documents(question, filenames)
    versions = _versions(question)
    candidates = list(filenames)
    def clarify(message: str) -> Resolution:
        return Resolution(candidates=candidates or filenames, clarification=message)

    if confirmed and selected:
        if any(name not in filenames for name in selected):
            return clarify('A selected document is no longer available. Please select the documents again.')
        if mode == 'compare' and len(selected) < 2:
            return clarify('Please select at least two documents to compare.')
        return Resolution(documents=list(selected))
    if re.search(r'\.(?:pdf|docx)\b', question, re.I):
        remainder = question
        for name in sorted(names, key=len, reverse=True):
            remainder = re.sub(re.escape(name), '', remainder, flags=re.I)
        if re.search(r'\.(?:pdf|docx)\b', remainder, re.I):
            return clarify('I could not match a requested filename. Please specify the indexed document names or select them below.')
    if names and mode == 'compare' and selected and len(selected) >= 2 and set(names) <= set(selected):
        if all(name in filenames for name in selected):
            return Resolution(documents=list(selected))
    if names:
        if mode == 'compare' and len(names) < 2:
            return clarify('Which other document should I compare with ' + names[0] + '? Please specify the document names or select them below.')
        return Resolution(documents=names)
    # Filename words are identity hints only. Unknown terminology causes a
    # clarification for comparisons, rather than an arbitrary semantic match.
    words = set(re.findall(r'[a-z]+', question.lower()))
    stop = {'what', 'which', 'the', 'is', 'are', 'a', 'an', 'of', 'in', 'and', 'or',
            'to', 'between', 'compare', 'difference', 'differences', 'changed',
            'version', 'versions', 'v', 'ver', 'vs', 'versus', 'document', 'documents',
            'file', 'files', 'please', 'summarize', 'summary', 'with', 'these', 'those'}
    hints = words - stop
    matching = [n for n in candidates if hints & set(re.findall(r'[a-z]+', Path(n).stem.lower()))]
    if matching:
        candidates = matching
    if selected:
        if any(name not in filenames for name in selected):
            return clarify('A previously selected document is no longer available. Please select the documents again.')
        # A new document reference must not silently inherit an unrelated scope.
        compatible = not matching or bool(set(selected) & set(matching))
        if compatible and (not versions or all(any(v in _versions(Path(n).stem) for n in selected) for v in versions)):
            if mode != 'compare' or len(selected) >= 2:
                return Resolution(documents=list(selected))
    if versions:
        groups = [[n for n in candidates if v in _versions(Path(n).stem)] for v in versions]
        if any(not group for group in groups):
            return clarify('I could not identify every requested version. Can you specify the document names or select them below?')
        if any(len(group) != 1 for group in groups):
            candidates = list(dict.fromkeys(n for group in groups for n in group))
            return clarify('More than one document matches the requested versions. Can you specify the document names or select them below?')
        resolved = list(dict.fromkeys(group[0] for group in groups))
        if mode != 'compare' or len(resolved) >= 2:
            # Uniqueness alone does not establish that two different studies
            # or document families belong together. Ask instead of inferring it.
            identities = {re.sub(r'(?<![a-z0-9])(?:version|ver|v)[ _.-]*\d+(?:\.\d+)*',
                                 '{version}', Path(n).stem.lower()) for n in resolved}
            if len(resolved) > 1 and len(identities) > 1:
                return clarify('The requested versions may belong to different document families. Please specify the document names or select them below.')
            return Resolution(documents=resolved)
    if mode == 'compare':
        return clarify('Which documents should I compare? Please specify the document names or select them below.')
    if matching and len(candidates) > 1:
        return clarify('Several documents match that reference. Which document(s) do you mean? Please specify the names or select them below.')
    if matching:
        return Resolution(documents=candidates)
    if len(filenames) > 1 and re.search(r'\b(?:latest|current|previous|older|newer|this document|the document|that document)\b', question, re.I):
        return clarify('Which document do you mean? Please specify its name or select it below.')
    return Resolution()
