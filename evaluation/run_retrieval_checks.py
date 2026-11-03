"""Run AFTER indexing demo sample documents; no LLM call is required."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from copilot.index import DocumentIndex  # noqa: E402
from copilot.workflow import choose_tool  # noqa: E402

cases = json.loads((Path(__file__).parent / 'expected_cases.json').read_text())
index = DocumentIndex()
if not index.list_files():
    raise SystemExit("No indexed files: first upload sample documents using Streamlit.")
correct = 0
for case in cases:
    mode = choose_tool(case['question'])
    evidence = index.retrieve(case['question'], mode=mode)
    files = {e.metadata['filename'] for e in evidence}
    passed = case['must_find_filename'] in files
    correct += int(passed)
    print(('PASS' if passed else 'FAIL') + f": {case['question']} -> {sorted(files)}")
print(f"Source-file retrieval hit rate: {correct}/{len(cases)}")
if correct != len(cases):
    raise SystemExit(1)
