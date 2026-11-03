import pytest

from copilot.routing import detect_intent


@pytest.mark.parametrize('question, mode', [
    ('whats the differenc between version 1 and 2', 'compare'),
    ('Comapre protocol version 1 and 2', 'compare'),
    ('Please compar these documents', 'compare'),
    ('What is the diffrence between v1 and v2?', 'compare'),
    ('Please sumarize the protocol', 'summary'),
    ('Give a summray of the protocol', 'summary'),
    ('Which patient saftey risks are documented?', 'safety'),
    ('List the monitoring observatinos', 'safety'),
    ('  COMPARE—version 1 & 2! ', 'compare'),
    ('Protocol v1 VS. v2', 'compare'),
    ('What dose is required?', 'lookup'),
    ('Describe the company', 'lookup'),
    ('What happened during summer?', 'lookup'),
    ('What are different dose levels?', 'lookup'),
    ('What is the safety reporting deadline?', 'lookup'),
    ('What is in Summary.pdf?', 'lookup'),
    ('What is in Protocol_Amendment_01.pdf?', 'lookup'),
    ('What is in compar.pdf?', 'lookup'),
])
def test_intent_spelling_and_boundaries(question, mode):
    result = detect_intent(question)
    assert result.mode == mode
    assert not result.clarification


def test_weaker_comparison_hint_requires_confirmation():
    result = detect_intent('What is the diferenc between version 1 and 2?')
    assert result.mode == 'compare'
    assert 'confirm' in result.clarification
    assert detect_intent('Explain diferenc').mode == 'lookup'


def test_conflicting_fuzzy_intents_require_confirmation():
    assert detect_intent('Compar and sumarize version 1 and 2').clarification
