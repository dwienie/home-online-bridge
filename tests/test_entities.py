from custom_components.home_online_bridge.conversion import cover_write_args, light_write_args, switch_write_args


def test_light_write_args():
    assert light_write_args(255) == (100, True)
    assert light_write_args(128) == (54, True)
    assert light_write_args(10) == (11, True)  # about 4 percent, spread over 8-100
    assert light_write_args(10, 30, 90) == (32, True)
    assert light_write_args(0) == (0, True)


def test_cover_write_args():
    assert cover_write_args("open") == (100, True)
    assert cover_write_args("close") == (0, True)
    assert cover_write_args(30) == (30, True)


def test_switch_write_args():
    assert switch_write_args(True) == (1, False)
    assert switch_write_args(False) == (0, False)
