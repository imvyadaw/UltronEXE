from tools.registry import ToolRegistry


def test_registry():
    r = ToolRegistry()
    r.register("x", lambda: 1)
    assert r.get("x")
