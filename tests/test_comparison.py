from copilot.comparison import compare_parts


def part(section, text, location='Page 1'):
    return dict(section=section, text=text, location=location)


def test_sections_added_removed_renumbered_and_moved():
    before = [part('1 Eligibility', 'Adults 18 to 65'), part('2 Safety', 'Report within 24 hours'),
              part('3 Removed', 'Entirely unrelated obsolete text')]
    after = [part('2 Safety', 'Report within 24 hours'), part('4 Eligibility', 'Adults 18 to 75'),
             part('5 New', 'New visit on day 28')]
    changes = compare_parts(before, after)
    assert {c['kind'] for c in changes} == {'modified', 'moved', 'added', 'removed'}
    eligibility = next(c for c in changes if c['kind'] == 'modified')
    assert eligibility['word_changes'] == [{'kind': 'replace', 'before': '65', 'after': '75'}]


def test_page_shift_does_not_create_text_change():
    assert compare_parts([part('Safety', 'Same text', 'Page 1')],
                         [part('Safety', 'Same text', 'Page 2')]) == []


def test_small_change_after_many_chunks_is_not_missed():
    before = [part('Safety', 'unchanged ' * 1000 + 'Report within 24 hours')]
    after = [part('Safety', 'unchanged ' * 1000 + 'Report within 48 hours')]
    changes = compare_parts(before, after)
    assert changes[0]['word_changes'] == [{'kind': 'replace', 'before': '24', 'after': '48'}]

def test_body_hash_excludes_heading_and_normalizes_whitespace():
    from copilot.comparison import section_body_hash
    left = dict(section='1 Safety', text='1 Safety\nReport within 24 hours.')
    right = dict(section='8 Reporting', text='8 Reporting\r\nReport  within\t24 hours.')
    assert section_body_hash(left) == section_body_hash(right)
    changes = compare_parts([part(**left)], [part(**right)])
    assert changes[0]['match_method'] == 'body_hash'


def test_renamed_body_reserved_before_heading_match_can_steal_it():
    before = [part('Old title', 'A completely different deleted requirement.'),
              part('Safety', 'Report within 24 hours.')]
    after = [part('Old title', 'Report within 24 hours.')]
    changes = compare_parts(before, after)
    assert changes[0]['kind'] == 'removed'
    assert changes[1]['before']['section'] == 'Safety'
    assert changes[1]['match_method'] == 'body_hash'


def test_duplicate_bodies_use_heading_and_do_not_steal_surviving_copy():
    before = [part('Site A', 'Keep the record.'), part('Site B', 'Keep the record.')]
    after = [part('Site B', 'Keep the record.')]
    changes = compare_parts(before, after)
    assert len(changes) == 1
    assert changes[0]['kind'] == 'removed'
    assert changes[0]['before']['section'] == 'Site A'


def test_duplicate_bodies_use_neighbor_context():
    before = [part('Anchor A', 'Unique preceding content A.'),
              part('Old A', 'Keep the record.'),
              part('Anchor B', 'Unique preceding content B.'),
              part('Old B', 'Keep the record.')]
    after = [part('Anchor B', 'Unique preceding content B.'),
             part('New B', 'Keep the record.'),
             part('Anchor A', 'Unique preceding content A.'),
             part('New A', 'Keep the record.')]
    changes = compare_parts(before, after)
    pairs = {c['before']['section']: c['after']['section'] for c in changes}
    assert pairs['Old A'] == 'New A'
    assert pairs['Old B'] == 'New B'


def test_hashes_differ_for_small_edits_then_similarity_gives_exact_diff():
    from copilot.comparison import section_body_hash
    left = part('Old title', 'Report within 24 hours.')
    right = part('New title', 'Report within 48 hours.')
    assert section_body_hash(left) != section_body_hash(right)
    change = compare_parts([left], [right])[0]
    assert change['match_method'] == 'text_similarity'
    assert change['word_changes'] == [{'kind': 'replace', 'before': '24', 'after': '48'}]


def test_empty_bodies_do_not_match_by_hash():
    changes = compare_parts([part('Old', 'Old')], [part('New', 'New')])
    assert {c['kind'] for c in changes} == {'added', 'removed'}


def test_duplicate_hash_without_context_is_flagged():
    before = [part('Old A', 'Same body.'), part('Old B', 'Same body.')]
    after = [part('New A', 'Same body.'), part('New B', 'Same body.')]
    changes = compare_parts(before, after)
    assert any(c['ambiguous'] for c in changes)
