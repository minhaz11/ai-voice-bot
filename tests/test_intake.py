from intake import IntakeMemory


def test_phone_given_before_name_is_remembered():
    memory = IntakeMemory()
    memory.append('01234')
    memory.append('56789')
    reminder = memory.finish_utterance()
    assert '0123456789' in reminder
    memory.append('Alex Morgan')
    assert memory.finish_utterance() is None
    assert memory.phone_candidates == ['0123456789']


def test_correction_retains_candidates_without_guessing():
    memory = IntakeMemory()
    memory.append('0123456789')
    memory.finish_utterance()
    memory.append('Actually +1 (202) 555-0123')
    assert '+12025550123' in memory.finish_utterance()
    assert len(memory.phone_candidates) == 2


def test_fragments_dates_and_repeated_number():
    memory = IntakeMemory()
    for text in ["It's my", 'September 24th at 10:00', '2026-09-24', '123456']:
        memory.append(text)
        assert memory.finish_utterance() is None
    memory.append('0123456789')
    assert memory.finish_utterance()
    memory.append('0123456789')
    assert memory.finish_utterance() is None
