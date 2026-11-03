"""Conservative spelling tolerance for intent words, never document names."""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Intent:
    mode: str
    clarification: str = ''


def _distance(left: str, right: str) -> int:
    """Edit distance including adjacent transpositions (e.g. comapre)."""
    rows = [list(range(len(right) + 1))]
    for i, a in enumerate(left, 1):
        row = [i]
        for j, b in enumerate(right, 1):
            value = min(row[-1] + 1, rows[-1][j] + 1,
                        rows[-1][j - 1] + (a != b))
            if i > 1 and j > 1 and a == right[j - 2] and left[i - 2] == b:
                value = min(value, rows[i - 2][j - 2] + 1)
            row.append(value)
        rows.append(row)
    return rows[-1][-1]


def detect_intent(question: str) -> Intent:
    normalized = unicodedata.normalize('NFKC', question).lower()
    # A filename containing "summary" or "amendment" is not an instruction.
    text = re.sub(r'[\w.\[\]-]+\.(?:pdf|docx)\b', ' ', normalized)
    words = re.findall(r'[a-z]+|\d+', text)
    comparison = ('compare', 'comparison', 'difference', 'differences',
                  'differ', 'diff', 'versus', 'vs', 'amendment', 'amendments')
    phrases = {
        'compare': [(word,) for word in comparison] + [('changed', 'between')],
        'safety': [('deviation',), ('deviations',), ('patient', 'safety'),
                   ('safety', 'impact'), ('safety', 'risk'),
                   ('monitoring', 'observation'), ('monitoring', 'observations'),
                   ('monitoring', 'visit')],
        'summary': [('summarize',), ('summarise',), ('summary',),
                    ('overview', 'of', 'the', 'protocol'), ('study', 'overview')],
    }
    # Exact intent takes precedence over any approximate match.
    for mode, patterns in phrases.items():
        for pattern in patterns:
            if any(tuple(words[i:i + len(pattern)]) == pattern
                   for i in range(len(words) - len(pattern) + 1)):
                return Intent(mode)

    paired_versions = bool(re.search(
        r'\b(?:version|versions|ver|v)\s*\d+(?:\.\d+)*\s*'
        r'(?:and|to|vs\.?|versus|&)\s*(?:(?:version|ver|v)\s*)?\d+', text))
    paired_names = len(re.findall(r'\.(?:pdf|docx)\b', normalized)) >= 2
    context = paired_versions or paired_names or 'between' in words

    matches = set()
    for mode, patterns in phrases.items():
        for pattern in patterns:
            for i in range(len(words) - len(pattern) + 1):
                window = words[i:i + len(pattern)]
                edits = 0
                for actual, expected in zip(window, pattern):
                    if actual == expected:
                        continue
                    # Short tokens such as "vs" must match exactly.
                    if min(len(actual), len(expected)) < 5 or abs(len(actual) - len(expected)) > 1:
                        edits = 99
                        break
                    edits += _distance(actual, expected)
                # One edit in the whole phrase, supported by an action position
                # or comparison context. Do not rewrite the user's question.
                if edits == 1 and (len(pattern) > 1 or i <= 2 or (mode == 'compare' and context)):
                    matches.add(mode)
    if len(matches) == 1:
        return Intent(matches.pop())
    # A weaker comparison hint needs explicit confirmation before retrieval.
    weak_comparison = context and any(
        len(word) >= 6 and abs(len(word) - len(target)) <= 2
        and _distance(word, target) == 2
        for word in words for target in ('compare', 'comparison', 'difference'))
    if weak_comparison or len(matches) > 1:
        return Intent('compare', 'Did you mean to compare documents? Select the documents below to confirm, or rephrase your question.')
    return Intent('lookup')
