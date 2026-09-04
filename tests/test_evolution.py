from self_evolution.code_analyzer import CodeAnalyzer


def test_analyzer():
    assert "files" in CodeAnalyzer().analyze(".")
