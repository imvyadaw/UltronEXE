from security.kill_switch import KillSwitch


def test_switch(tmp_path):
    k = KillSwitch(str(tmp_path / "x"))
    assert not k.active()
    k.activate()
    assert k.active()
    k.deactivate()
    assert not k.active()
