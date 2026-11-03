import pytest

from copilot.index import DocumentIndex, Evidence
from copilot.resolution import named_documents, resolve_documents
from copilot.workflow import make_graph


FILES = ['Protocol_v1.pdf', 'Protocol_Amendment_01.pdf',
         'Protocol_v1_generated.pdf', 'Protocol_v2_generated.pdf']


def test_ambiguous_versions_do_not_prefer_matching_suffix():
    result = resolve_documents('difference between protocol version 1 and 2', FILES, mode='compare')
    assert result.clarification
    assert result.documents == []
    assert set(result.candidates) == {FILES[0], FILES[2], FILES[3]}


@pytest.mark.parametrize('prefix', ['Budget', 'Manual', 'StudyAB_Analysis'])
def test_unique_versions_for_arbitrary_documents(prefix):
    files = [f'{prefix}_v1.pdf', f'{prefix}_v2.pdf']
    result = resolve_documents(f'Compare {prefix} version 1 and 2', files, mode='compare')
    assert result.documents == files
    assert not result.clarification


def test_multiple_studies_missing_versions_and_unspecified_pair():
    for files, question in [(['StudyA_v1.pdf', 'StudyB_v1.pdf', 'StudyA_v2.pdf'], 'Compare v1 vs v2'),
                            (FILES, 'Compare version 1 and 3'),
                            (FILES, 'Compare the documents')]:
        assert resolve_documents(question, files, mode='compare').clarification


def test_exact_names_and_prefix_boundaries():
    assert named_documents('Use Protocol_v1_generated and Protocol_v2_generated.pdf', FILES) == FILES[2:]
    result = resolve_documents('Compare Protocol_v1.pdf and Protocol_v2_generated.pdf', FILES, mode='compare')
    assert result.documents == [FILES[0], FILES[3]]
    assert resolve_documents('Compare Protocol_v1.pdf', FILES, mode='compare').clarification


def test_remembered_selection_and_changed_reference():
    assert resolve_documents('What about eligibility?', FILES, mode='lookup', selected=FILES[2:]).documents == FILES[2:]
    assert resolve_documents('Compare version 1 and 3', FILES, mode='compare', selected=FILES[2:]).clarification
    assert resolve_documents('Compare versions', FILES[:2], mode='compare', selected=FILES[2:]).clarification
    assert resolve_documents('Summarize Protocol_v1.pdf', FILES, mode='summary', selected=FILES[2:]).documents == FILES[:1]
    assert resolve_documents('Summarize the budget', FILES + ['Budget.pdf'], mode='summary', selected=FILES[2:]).documents == ['Budget.pdf']


def test_generic_topic_query_and_ambiguous_single_reference():
    assert resolve_documents('What are the reporting requirements?', FILES, mode='lookup').documents == []
    assert resolve_documents('Summarize protocol version 1', FILES, mode='summary').clarification


def test_unrelated_families_unknown_names_and_relative_references():
    assert resolve_documents('Compare version 1 and 2', ['StudyA_v1.pdf', 'StudyB_v2.pdf'], mode='compare').clarification
    assert resolve_documents('Compare Protocol_v1.pdf and Missing.pdf', FILES, mode='compare').clarification
    assert resolve_documents('Summarize the latest version', FILES, mode='summary').clarification
    assert resolve_documents('Summarize the document', FILES, mode='summary').clarification


def test_user_confirmation_overrides_filename_hints():
    files = ['Original.pdf', 'Revised.pdf']
    result = resolve_documents('Compare version 1 and 2', files, mode='compare',
                               selected=files, confirmed=True)
    assert result.documents == files
    assert resolve_documents('Compare versions', files, mode='compare',
                             selected=files[:1], confirmed=True).clarification


class StubIndex:
    def __init__(self):
        self.calls = []

    def list_files(self):
        return [{'filename': f} for f in FILES]

    def retrieve(self, question, **kwargs):
        self.calls.append(kwargs)
        return [Evidence('source', {'filename': n}, 0.9, n) for n in kwargs['filenames']]


def test_clarification_bypasses_search_and_generation(monkeypatch):
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: pytest.fail('must not generate'))
    index = StubIndex()
    result = make_graph(index).invoke({'question': 'difference between protocol version 1 and 2'})
    assert result['clarification'] and not index.calls


def test_selected_documents_resume_original_question(monkeypatch):
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: 'supported answer')
    index = StubIndex()
    result = make_graph(index).invoke({'question': 'difference between protocol version 1 and 2',
                                      'selected_documents': FILES[2:]})
    assert result['answer'] == 'supported answer'
    assert index.calls[0]['filenames'] == FILES[2:]


def test_filtered_retrieval_never_queries_library():
    index = object.__new__(DocumentIndex)
    index.list_files = lambda: [{'filename': f} for f in FILES]
    calls = []
    def query(question, *, filename=None, limit=9):
        calls.append(filename)
        return [Evidence('text', {'filename': filename}, 0.9, f'{filename}-{i}') for i in range(limit)]
    index.query = query
    result = index.retrieve('changes', mode='compare', filenames=FILES[2:])
    assert calls == FILES[2:]
    assert [e.metadata['filename'] for e in result[:2]] == FILES[2:]
    assert len(result) == 9


def test_missing_selected_evidence_does_not_generate(monkeypatch):
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: pytest.fail('must not generate'))
    index = StubIndex()
    index.retrieve = lambda *a, **k: []
    result = make_graph(index).invoke({'question': 'Compare versions', 'selected_documents': FILES[2:]})
    assert 'Insufficient relevant evidence' in result['answer']
