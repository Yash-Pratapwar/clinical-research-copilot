"""Full-text section alignment and exact differences, independent of RAG."""
import difflib
import hashlib
import re


def compare_parts(before, after):
    def sections(parts):
        groups = []
        for part in parts:
            if part.get("block_type") in {"header", "footer"}:
                continue
            if (groups and groups[-1]['section'] == part['section']
                    and groups[-1].get('section_id', '') == part.get('section_id', '')):
                groups[-1]['text'] += '\n' + part['text']
                if part['location'] not in groups[-1]['locations']:
                    groups[-1]['locations'].append(part['location'])
            else:
                groups.append(dict(section=part['section'], section_id=part.get('section_id', ''),
                                   text=part['text'], locations=[part['location']]))
        return groups
    old, new = sections(before), sections(after)
    matches = _align_sections(old, new)
    aligned = [(i, matches[i][0], left, new[matches[i][0]]) if i in matches
               else (i, None, left, None) for i, left in enumerate(old)]
    used = {j for j, _, _ in matches.values()}
    aligned.extend((None, j, None, right) for j, right in enumerate(new) if j not in used)
    order = [j for i, j, _, _ in aligned if i is not None and j is not None]
    changes = []
    for i, j, left, right in aligned:
        if left is None:
            kind = 'added'
        elif right is None:
            kind = 'removed'
        elif left['text'] != right['text'] or left['section'] != right['section']:
            kind = 'modified'
        elif order.index(j) != sorted(order).index(j):
            kind = 'moved'
        else:
            continue
        a, b = (left or {}).get('text', ''), (right or {}).get('text', '')
        changes.append(dict(kind=kind, before=left, after=right,
            match_method=matches[i][1] if i in matches else 'unmatched',
            ambiguous=matches[i][2] if i in matches else False,
            diff='\n'.join(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile='Before', tofile='After', lineterm='')),
            word_changes=[{'kind': tag, 'before': ' '.join(a.split()[a0:a1]), 'after': ' '.join(b.split()[b0:b1])}
                          for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).get_opcodes() if tag != 'equal']))
    return changes


def _normalize_text(text):
    # Preserve case, numbers and punctuation: these can carry meaning.
    return " ".join(text.split())


def _section_body(section):
    lines = section["text"].splitlines()
    # Extraction includes the heading in text. Remove only a complete leading
    # heading line; never drop an arbitrary first sentence.
    heading = _normalize_text(section["section"])
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _normalize_text(lines[0]) == heading:
        lines.pop(0)
    return _normalize_text("\n".join(lines))


def section_body_hash(section):
    """Hash normalized body text, excluding an extracted leading heading."""
    body = _section_body(section)
    return hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None


def _heading(section):
    return re.sub(r"^\s*(?:section\s+)?\d+(?:\.\d+)*[\s:.)-]*",
                  "", section["section"].lower())


def _align_sections(old, new):
    """Reserve content matches globally before attempting headings/similarity."""
    old_hash = [section_body_hash(s) for s in old]
    new_hash = [section_body_hash(s) for s in new]
    available = set(range(len(new)))
    matches = {}

    def context(i, j):
        exact = old[i]["section"] == new[j]["section"]
        heading = _heading(old[i]) == _heading(new[j])
        # Numeric parent prefixes provide a secondary identity clue.
        parent = lambda s: re.match(r"^(?:section\s+)?(\d+(?:\.\d+)*)", s.lower())
        a, b = parent(old[i]["section"]), parent(new[j]["section"])
        same_parent = bool(a and b and "." in a[1] and "." in b[1]
                           and a[1].rsplit(".", 1)[0] == b[1].rsplit(".", 1)[0])
        neighbors = sum(0 <= i + delta < len(old) and 0 <= j + delta < len(new)
                        and old_hash[i + delta] is not None
                        and old_hash.count(old_hash[i + delta]) == 1
                        and new_hash.count(new_hash[j + delta]) == 1
                        and old_hash[i + delta] == new_hash[j + delta]
                        for delta in (-1, 1))
        anchors = sum((i - oi) * (j - nj) > 0 for oi, (nj, _, _) in matches.items())
        return (exact, heading, same_parent, neighbors, anchors)

    def assign(i, candidates, method):
        ranked = sorted(candidates, key=lambda j: (
            context(i, j), -abs(i / max(1, len(old) - 1) - j / max(1, len(new) - 1)), -j),
            reverse=True)
        best = ranked[0]
        # Position makes the result deterministic, but cannot prove identity.
        ambiguous = len(ranked) > 1 and context(i, best) == context(i, ranked[1])
        matches[i] = (best, method, ambiguous)
        available.remove(best)

    # Unique bodies first, including renamed and moved sections.
    for i, digest in enumerate(old_hash):
        if digest and old_hash.count(digest) == new_hash.count(digest) == 1:
            assign(i, [new_hash.index(digest)], "body_hash")
    # Repeated boilerplate must use context, rather than an arbitrary hash lookup.
    for digest in dict.fromkeys(old_hash):
        if not digest:
            continue
        pending = [i for i, value in enumerate(old_hash) if value == digest and i not in matches]
        while pending:
            candidates = [j for j in available if new_hash[j] == digest]
            if not candidates:
                break
            i = max(pending, key=lambda oi: (max(context(oi, j) for j in candidates), -oi))
            assign(i, candidates, "body_hash")
            j, method, ambiguous = matches[i]
            competing = any(context(oi, j) == context(i, j) for oi in pending if oi != i)
            matches[i] = (j, method, ambiguous or competing)
            pending.remove(i)
    for method in ("heading", "normalized_heading"):
        for i, left in enumerate(old):
            if i in matches:
                continue
            candidates = [j for j in available if (
                left["section"] == new[j]["section"] if method == "heading"
                else _heading(left) == _heading(new[j]))]
            if candidates:
                assign(i, candidates, method)
    # Rank all remaining pairs together so an early weak match cannot steal a
    # later section's stronger match.
    pairs = sorted(((difflib.SequenceMatcher(None, _section_body(left),
                        _section_body(right), autojunk=False).ratio(), i, j)
                    for i, left in enumerate(old) if i not in matches
                    for j, right in enumerate(new) if j in available
                    and _section_body(left) and _section_body(right)), reverse=True)
    for score, i, j in pairs:
        if score < 0.55:
            break
        if i in matches or j not in available:
            continue
        tied = [candidate for value, oi, candidate in pairs
                if oi == i and candidate in available and abs(value - score) < 1e-9]
        assign(i, tied, "text_similarity")
    return matches
