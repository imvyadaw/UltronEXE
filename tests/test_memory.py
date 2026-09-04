from memory.short_term import ShortTermMemory


def test_memory():
    m = ShortTermMemory(2)
    m.add(1)
    m.add(2)
    m.add(3)
    assert m.recent() == [2, 3]
