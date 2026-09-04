def test_public_compatibility_exports():
    from voice import get_voice, get_stt, get_wakeword_detector
    from memory.short_term import get_short_term_memory, ReferenceMemory
    from memory.long_term import get_long_term_memory
    from learning import get_learner, get_experience_store

    assert callable(get_voice)
    assert callable(get_stt)
    assert callable(get_wakeword_detector)
    assert callable(get_short_term_memory)
    assert ReferenceMemory
    assert callable(get_long_term_memory)
    assert callable(get_learner)
    assert callable(get_experience_store)
