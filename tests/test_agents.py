from agents.coordinator import Coordinator


def test_assign():
    assert Coordinator().assign("fix bug") == "coding"
