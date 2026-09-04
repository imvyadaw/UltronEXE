from orchestration.goal_manager import GoalManager


def test_goal():
    assert GoalManager().create("x").text == "x"
