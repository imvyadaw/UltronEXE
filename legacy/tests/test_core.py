from ULTRON_CORE.consciousness.self_awareness import SelfAwareness


def test_awareness():
    s = SelfAwareness()
    s.set_goal("x")
    assert s.snapshot()["goal"] == "x"
